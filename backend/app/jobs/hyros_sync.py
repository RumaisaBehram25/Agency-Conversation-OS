"""Hyros purchase + lead sync job (cron or manual)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hyros_sync_log import HyrosSyncLog
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


def _sale_stable_id(sale: HyrosSale) -> str:
    """Idempotent key for a Hyros sale row within an org (for unmatched logging)."""
    if sale.id:
        return f"sale_id:{sale.id}"
    if sale.order_id:
        return f"order:{sale.order_id}"
    if sale.lead_id and sale.created_at:
        return f"lead:{sale.lead_id}:{sale.created_at.isoformat()}"
    return (
        f"fallback:{sale.lead_email}:{sale.product}:"
        f"{sale.created_at.isoformat() if sale.created_at else 'none'}"
    )


# Sync-log retention window. The Hyros scheduler runs every ~3 hours, so a
# 3-day window keeps roughly 24 audit rows per org — enough to render a
# 3-hour-step health table on the Settings page without unbounded growth.
HYROS_SYNC_LOG_RETENTION_DAYS = 3


async def _prune_old_hyros_sync_logs(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    retention_days: int = HYROS_SYNC_LOG_RETENTION_DAYS,
) -> None:
    """
    Delete HyrosSyncLog rows older than ``retention_days`` for this org.

    Time-based pruning (instead of count-based) lets the Settings UI render a
    "last N days, every 3 hours" view directly without truncating recent
    history when the scheduler runs more often than expected.
    """
    await db.flush()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(retention_days)))
    await db.execute(
        delete(HyrosSyncLog).where(
            HyrosSyncLog.org_id == org_id,
            HyrosSyncLog.synced_at < cutoff,
        )
    )


async def _persist_hyros_sync_log(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    synced_at: datetime,
    sales_scanned: int,
    purchases_matched: int,
    unmatched_sales: int,
    matched_by_attora_id: int,
    matched_by_attora_sub: int,
    matched_by_email: int,
) -> None:
    """Append one audit row for a completed org sync (caller commits)."""
    db.add(
        HyrosSyncLog(
            org_id=org_id,
            synced_at=synced_at,
            sales_scanned=sales_scanned,
            purchases_matched=purchases_matched,
            unmatched_sales=unmatched_sales,
            matched_by_attora_id=matched_by_attora_id,
            matched_by_attora_sub=matched_by_attora_sub,
            matched_by_email=matched_by_email,
        )
    )
    await _prune_old_hyros_sync_logs(db, org_id)


def _resolve_org_hyros_api_key(org: Organization) -> tuple[str | None, str | None]:
    """
    Return (decrypted_api_key, skip_reason) for Hyros sync.
    Only the org-level key is used (no shared env fallback — multi-tenant safe).
    """
    if org.hyros_api_key is None or not str(org.hyros_api_key).strip():
        return None, "no_api_key"
    try:
        key = decrypt_value(org.hyros_api_key).strip()
    except Exception:
        logger.warning("Failed to decrypt hyros_api_key for org=%s", org.id)
        return None, "decrypt_failed"
    if not key:
        return None, "empty_api_key"
    return key, None


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

    Returns per-org counts.     Caller is responsible for db.commit().
    """
    api_key, skip_reason = _resolve_org_hyros_api_key(org)
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
            "unmatched_sales": 0,
            "skipped": True,
            "skip_reason": skip_reason or "no_api_key",
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
    matched_by_attora_id = 0
    matched_by_attora_sub = 0
    matched_by_email = 0
    matched_by_name = 0
    matched_by_origin_lead = 0
    purchases_found = 0
    total_matched = 0
    matched_sale_ids: set[str] = set()

    subs_result = await db.execute(
        select(Subscriber).where(Subscriber.org_id == org.id)
    )
    subscribers = subs_result.scalars().all()
    for subscriber in subscribers:
        subscribers_scanned += 1

        # 1. Match against Sales for purchase confirmation
        sale_match = None
        sub_attora_id = _normalize(str(subscriber.id))
        sub_attora_sub = _normalize(subscriber.manychat_subscriber_id)
        sub_email = _normalize(subscriber.email)
        sub_full_name = _normalize(_subscriber_full_name(subscriber))

        # Priority 0 — attora_id stamped onto the sale by Hyros
        if sub_attora_id:
            sale_match = next(
                (s for s in sales if _normalize(s.attora_id) == sub_attora_id),
                None,
            )

        # Priority 0.5 — attora_sub
        if not sale_match and sub_attora_sub:
            sale_match = next(
                (s for s in sales if _normalize(s.attora_sub) == sub_attora_sub),
                None,
            )

        if not sale_match and sub_email:
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
            subscriber.hyros_traffic_source = (
                sale_match.traffic_source
                or sale_match.first_source_name
                or subscriber.hyros_traffic_source
            )
            subscriber.hyros_creative_name = (
                sale_match.creative_name
                or sale_match.first_source_tag
                or subscriber.hyros_creative_name
            )
            subscriber.hyros_synced_at = now
            matched_sale_ids.add(_sale_stable_id(sale_match))
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
                subscriber_attora_id=str(subscriber.id),
                subscriber_manychat_id=subscriber.manychat_subscriber_id,
            )
            if match:
                if match.matched_by == "attora_id":
                    matched_by_attora_id += 1
                elif match.matched_by == "attora_sub":
                    matched_by_attora_sub += 1
                elif match.matched_by == "email":
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

    unmatched_sales = 0
    for sale in sales:
        sid = _sale_stable_id(sale)
        if sid in matched_sale_ids:
            continue
        unmatched_sales += 1
        link_preview = (sale.purchase_link or "")[:240]
        attora_id_log = sale.attora_id if sale.attora_id else None
        logger.warning(
            "[hyros] unmatched purchase org_id=%s sale_key=%s email=%s attora_id_on_sale=%s attora_sub=%s "
            "product=%s link=%s",
            org.id,
            sid,
            sale.lead_email,
            attora_id_log,
            sale.attora_sub,
            sale.product,
            link_preview or None,
        )

    await _persist_hyros_sync_log(
        db,
        org_id=org.id,
        synced_at=now,
        sales_scanned=len(sales),
        purchases_matched=purchases_found,
        unmatched_sales=unmatched_sales,
        matched_by_attora_id=matched_by_attora_id,
        matched_by_attora_sub=matched_by_attora_sub,
        matched_by_email=matched_by_email,
    )

    return {
        "subscribers_scanned": subscribers_scanned,
        "sales_scanned": len(sales),
        "matched_by_attora_id": matched_by_attora_id,
        "matched_by_attora_sub": matched_by_attora_sub,
        "matched_by_email": matched_by_email,
        "matched_by_name": matched_by_name,
        "matched_by_origin_lead": matched_by_origin_lead,
        "total_matched": total_matched,
        "purchases_found": purchases_found,
        "unmatched_hyros_leads": unmatched_hyros_leads,
        "unmatched_sales": unmatched_sales,
        "skipped": False,
    }


async def sync_hyros_purchases(db: AsyncSession) -> dict:
    """Pull Hyros sales and leads for every org with a Hyros key, then update subscribers."""
    orgs_result = await db.execute(select(Organization))
    orgs = orgs_result.scalars().all()

    now = datetime.now(timezone.utc)
    service = HyrosService()
    lead_cache: dict[str, list[HyrosLead]] = {}
    sale_cache: dict[str, list[HyrosSale]] = {}
    matched_lead_ids: dict[str, set[str]] = {}

    subscribers_scanned = 0
    sales_scanned = 0
    matched_by_attora_id = 0
    matched_by_attora_sub = 0
    matched_by_email = 0
    matched_by_name = 0
    matched_by_origin_lead = 0
    purchases_found = 0
    total_matched = 0
    unmatched_sales_total = 0
    orgs_skipped_no_api_key = 0
    orgs_decrypt_failed = 0
    orgs_synced = 0

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
            reason = org_summary.get("skip_reason") or ""
            if reason == "decrypt_failed":
                orgs_decrypt_failed += 1
            elif reason in ("no_api_key", "empty_api_key"):
                orgs_skipped_no_api_key += 1
            else:
                logger.warning("Unexpected hyros skip_reason=%s org=%s", reason, org.id)
                orgs_skipped_no_api_key += 1
            continue
        orgs_synced += 1
        subscribers_scanned += org_summary["subscribers_scanned"]
        sales_scanned += org_summary["sales_scanned"]
        matched_by_attora_id += org_summary.get("matched_by_attora_id", 0)
        matched_by_attora_sub += org_summary.get("matched_by_attora_sub", 0)
        matched_by_email += org_summary["matched_by_email"]
        matched_by_name += org_summary["matched_by_name"]
        matched_by_origin_lead += org_summary["matched_by_origin_lead"]
        purchases_found += org_summary["purchases_found"]
        total_matched += org_summary["total_matched"]
        unmatched_sales_total += org_summary.get("unmatched_sales", 0)

    unmatched_hyros_leads = sum(
        max(0, len(leads) - len(matched_lead_ids.get(api_key, set())))
        for api_key, leads in lead_cache.items()
    )

    return {
        "orgs_total": len(orgs),
        "orgs_scanned": len(orgs),
        "orgs_synced": orgs_synced,
        # Alias for dashboards / cron checklists (`orgs_skipped_no_api_key` is the canonical name).
        "orgs_skipped": orgs_skipped_no_api_key,
        "orgs_skipped_no_api_key": orgs_skipped_no_api_key,
        "orgs_decrypt_failed": orgs_decrypt_failed,
        "subscribers_scanned": subscribers_scanned,
        "sales_scanned": sales_scanned,
        "matched_by_attora_id": matched_by_attora_id,
        "matched_by_attora_sub": matched_by_attora_sub,
        "matched_by_email": matched_by_email,
        "matched_by_name": matched_by_name,
        "matched_by_origin_lead": matched_by_origin_lead,
        "total_matched": total_matched,
        "purchases_found": purchases_found,
        "purchases_matched_to_subscribers": purchases_found,
        "unmatched_sales": unmatched_sales_total,
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
