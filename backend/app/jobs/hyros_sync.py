"""Daily Hyros lead sync job."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.organization import Organization
from app.models.subscriber import Subscriber
from app.security.encryption import decrypt_value
from app.services.hyros_service import HyrosLead, HyrosService, match_lead, HyrosSale, _normalize

logger = logging.getLogger(__name__)


def _subscriber_full_name(subscriber: Subscriber) -> str | None:
    parts = [part for part in (subscriber.first_name, subscriber.last_name) if part]
    if not parts:
        return None
    return " ".join(parts)


def _apply_lead_to_subscriber(subscriber: Subscriber, lead: HyrosLead, *, now: datetime) -> bool:
    subscriber.hyros_lead_id = lead.id or subscriber.hyros_lead_id
    subscriber.hyros_email = lead.email or subscriber.hyros_email
    if lead.first_source:
        subscriber.hyros_origin_source = lead.first_source.name or subscriber.hyros_origin_source
        subscriber.hyros_origin_tag = lead.first_source.tag or subscriber.hyros_origin_tag
        subscriber.hyros_traffic_source = lead.first_source.traffic_source or subscriber.hyros_traffic_source
        subscriber.hyros_creative_name = lead.first_source.creative_name or subscriber.hyros_creative_name

    has_purchase = bool(lead.purchases)
    if has_purchase:
        # Use first purchase as requested (earliest date)
        first_purchase = sorted(
            lead.purchases,
            key=lambda purchase: purchase.purchased_at or datetime.max.replace(tzinfo=timezone.utc),
            reverse=False,
        )[0]
        subscriber.hyros_purchased = True
        subscriber.hyros_product = first_purchase.product or subscriber.hyros_product
        subscriber.hyros_purchase_date = first_purchase.purchased_at or subscriber.hyros_purchase_date

    subscriber.hyros_synced_at = now
    return has_purchase


async def _sync_hyros_for_org(
    db: AsyncSession,
    org: Organization,
    *,
    service: HyrosService,
    now: datetime,
    lead_cache: dict[str, list[HyrosLead]] | None = None,
    sale_cache: dict[str, list[HyrosSale]] | None = None,
    matched_lead_ids: dict[str, set[str]] | None = None,
) -> dict:
    """
    Sync Hyros leads + sales for a single org. Used by both the bulk cron
    sweep (which shares caches across orgs to avoid refetching when multiple
    orgs share an API key) and the user-facing manual sync (which calls this
    standalone for one org).

    Returns per-org counts. Caller is responsible for db.commit().
    """
    api_key = settings.hyros_api_key or None
    if not api_key and org.hyros_api_key:
        try:
            api_key = decrypt_value(org.hyros_api_key)
        except Exception:
            logger.warning("Failed to decrypt hyros_api_key for org=%s", org.id)
            return {
                "subscribers_scanned": 0,
                "sales_scanned": 0,
                "matched_by_email": 0,
                "matched_by_name": 0,
                "matched_by_origin_lead": 0,
                "total_matched": 0,
                "purchases_found": 0,
                "unmatched_hyros_leads": 0,
                "skipped": True,
                "skip_reason": "decrypt_failed",
            }

    if not api_key:
        return {
            "subscribers_scanned": 0,
            "sales_scanned": 0,
            "matched_by_email": 0,
            "matched_by_name": 0,
            "matched_by_origin_lead": 0,
            "total_matched": 0,
            "purchases_found": 0,
            "unmatched_hyros_leads": 0,
            "skipped": True,
            "skip_reason": "no_api_key",
        }

    # Use shared caches when present (bulk cron path), otherwise fetch fresh.
    if lead_cache is not None and api_key in lead_cache:
        leads = lead_cache[api_key]
        sales = sale_cache[api_key] if sale_cache is not None else []
    else:
        leads = await service.fetch_leads(api_key, org=org)
        sales = await service.fetch_sales(api_key, org=org)
        if lead_cache is not None:
            lead_cache[api_key] = leads
        if sale_cache is not None:
            sale_cache[api_key] = sales

    if matched_lead_ids is not None and api_key not in matched_lead_ids:
        matched_lead_ids[api_key] = set()
    local_matched: set[str] = (
        matched_lead_ids[api_key] if matched_lead_ids is not None else set()
    )

    subscribers_scanned = 0
    matched_by_email = 0
    matched_by_name = 0
    matched_by_origin_lead = 0
    purchases_found = 0
    total_matched = 0

    subs_result = await db.execute(
        select(Subscriber).where(Subscriber.org_id == org.id)
    )
    subscribers = subs_result.scalars().all()
    for subscriber in subscribers:
        subscribers_scanned += 1

        # 1. Match against Sales for purchase confirmation
        sale_match = None
        sub_email = _normalize(subscriber.email)
        sub_full_name = _normalize(_subscriber_full_name(subscriber))

        if sub_email:
            sale_match = next(
                (s for s in sales if _normalize(s.lead_email) == sub_email), None
            )

        if not sale_match and sub_full_name:
            sale_match = next(
                (
                    s
                    for s in sales
                    if _normalize(f"{s.lead_first_name} {s.lead_last_name}")
                    == sub_full_name
                ),
                None,
            )

        if sale_match:
            subscriber.hyros_purchased = True
            subscriber.hyros_product = sale_match.product or subscriber.hyros_product
            subscriber.hyros_purchase_date = (
                sale_match.created_at or subscriber.hyros_purchase_date
            )
            subscriber.hyros_lead_id = sale_match.lead_id or subscriber.hyros_lead_id
            subscriber.hyros_email = sale_match.lead_email or subscriber.hyros_email
            subscriber.hyros_origin_source = (
                sale_match.first_source_name or subscriber.hyros_origin_source
            )
            subscriber.hyros_origin_tag = (
                sale_match.first_source_tag or subscriber.hyros_origin_tag
            )
            subscriber.hyros_synced_at = now
            purchases_found += 1
            total_matched += 1
            if sale_match.lead_id:
                local_matched.add(sale_match.lead_id)

        # 2. Match against Leads for enrichment (attribution info)
        if leads:
            match = match_lead(
                leads,
                subscriber_email=subscriber.email,
                subscriber_name=_subscriber_full_name(subscriber),
            )
            if match:
                if match.matched_by == "email":
                    matched_by_email += 1
                elif match.matched_by == "name":
                    matched_by_name += 1
                elif match.matched_by == "origin_lead":
                    matched_by_origin_lead += 1

                if match.lead.id:
                    local_matched.add(match.lead.id)

                if not sale_match:
                    total_matched += 1

                _apply_lead_to_subscriber(subscriber, match.lead, now=now)

    unmatched_hyros_leads = max(0, len(leads) - len(local_matched))

    return {
        "subscribers_scanned": subscribers_scanned,
        "sales_scanned": len(sales),
        "matched_by_email": matched_by_email,
        "matched_by_name": matched_by_name,
        "matched_by_origin_lead": matched_by_origin_lead,
        "total_matched": total_matched,
        "purchases_found": purchases_found,
        "unmatched_hyros_leads": unmatched_hyros_leads,
        "skipped": False,
    }


async def sync_hyros_purchases(db: AsyncSession) -> dict:
    """Pull Hyros sales and leads for every org, then update subscribers."""
    orgs_result = await db.execute(select(Organization))
    orgs = orgs_result.scalars().all()

    now = datetime.now(timezone.utc)
    service = HyrosService()
    lead_cache: dict[str, list[HyrosLead]] = {}
    sale_cache: dict[str, list[HyrosSale]] = {}
    matched_lead_ids: dict[str, set[str]] = {}

    subscribers_scanned = 0
    sales_scanned = 0
    matched_by_email = 0
    matched_by_name = 0
    matched_by_origin_lead = 0
    purchases_found = 0
    total_matched = 0

    for org in orgs:
        org_summary = await _sync_hyros_for_org(
            db,
            org,
            service=service,
            now=now,
            lead_cache=lead_cache,
            sale_cache=sale_cache,
            matched_lead_ids=matched_lead_ids,
        )
        if org_summary.get("skipped"):
            continue
        subscribers_scanned += org_summary["subscribers_scanned"]
        sales_scanned += org_summary["sales_scanned"]
        matched_by_email += org_summary["matched_by_email"]
        matched_by_name += org_summary["matched_by_name"]
        matched_by_origin_lead += org_summary["matched_by_origin_lead"]
        purchases_found += org_summary["purchases_found"]
        total_matched += org_summary["total_matched"]

    unmatched_hyros_leads = sum(
        max(0, len(leads) - len(matched_lead_ids.get(api_key, set())))
        for api_key, leads in lead_cache.items()
    )

    return {
        "orgs_scanned": len(orgs),
        "subscribers_scanned": subscribers_scanned,
        "sales_scanned": sales_scanned,
        "matched_by_email": matched_by_email,
        "matched_by_name": matched_by_name,
        "matched_by_origin_lead": matched_by_origin_lead,
        "total_matched": total_matched,
        "purchases_found": purchases_found,
        "unmatched_hyros_leads": unmatched_hyros_leads,
    }


async def sync_hyros_for_org_id(db: AsyncSession, org_id) -> dict:
    """
    User-facing manual sync for a single org. Wraps `_sync_hyros_for_org` with
    fresh caches (no cross-org sharing). Caller commits.
    """
    org_result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_result.scalar_one_or_none()
    if org is None:
        return {"skipped": True, "skip_reason": "org_not_found"}

    return await _sync_hyros_for_org(
        db,
        org,
        service=HyrosService(),
        now=datetime.now(timezone.utc),
    )
