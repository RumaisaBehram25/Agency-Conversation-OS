"""Hyros service helpers for lead matching and purchase syncing."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.organization import Organization
from app.models.subscriber import Subscriber
from app.security.encryption import decrypt_value

logger = logging.getLogger(__name__)

_HYROS_BASE_URL = "https://api.hyros.com"
_HYROS_LEADS_PATH = "/v1/api/v1.0/leads"


@dataclass
class HyrosPurchase:
    product: str | None = None
    purchased_at: datetime | None = None
    raw: dict[str, Any] | None = None
    name: str | None = None
    origin_source: str | None = None


@dataclass
class HyrosLeadSource:
    name: str | None = None
    tag: str | None = None
    traffic_source: str | None = None
    creative_name: str | None = None
    email: str | None = None
    raw: dict[str, Any] | None = None


@dataclass
class HyrosLead:
    id: str | None
    email: str | None
    first_name: str | None
    last_name: str | None
    tags: list[str]
    first_source: HyrosLeadSource | None
    last_source: HyrosLeadSource | None
    origin_lead: HyrosLeadSource | None
    purchases: list[HyrosPurchase]
    raw: dict[str, Any]


@dataclass
class HyrosLeadMatch:
    lead: HyrosLead
    matched_by: str


@dataclass
class HyrosSale:
    id: str | None
    order_id: str | None
    created_at: datetime | None
    lead_email: str | None
    lead_first_name: str | None
    lead_last_name: str | None
    lead_id: str | None
    lead_tags: list[str]
    product: str | None
    first_source_name: str | None
    first_source_tag: str | None
    raw: dict


def _normalize(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _subscriber_full_name(subscriber: Subscriber) -> str | None:
    parts = [part for part in (subscriber.first_name, subscriber.last_name) if part]
    if not parts:
        return None
    return " ".join(parts)


def _lead_full_name(lead: HyrosLead) -> str | None:
    parts = [part for part in (lead.first_name, lead.last_name) if part]
    if not parts:
        return None
    return " ".join(parts)


def _string_from_any(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _extract_rows(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [row for row in body if isinstance(row, dict)]
    if isinstance(body, dict):
        for key in ("result", "data", "results", "items", "purchases", "leads"):
            value = body.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        if any(key in body for key in ("email", "firstName", "lastName", "id")):
            return [body]
    return []


def _extract_source(raw: Any) -> HyrosLeadSource | None:
    if not isinstance(raw, dict):
        return None
    
    # Nested field extraction based on actual Hyros response
    traffic_source_raw = raw.get("trafficSource")
    traffic_source_name = None
    if isinstance(traffic_source_raw, dict):
        traffic_source_name = traffic_source_raw.get("name")
    elif isinstance(traffic_source_raw, str):
        traffic_source_name = traffic_source_raw

    source_link_ad_raw = raw.get("sourceLinkAd")
    creative_name = None
    if isinstance(source_link_ad_raw, dict):
        creative_name = source_link_ad_raw.get("name")
    
    return HyrosLeadSource(
        name=_string_from_any(raw.get("name") or raw.get("source") or raw.get("origin")),
        tag=_string_from_any(raw.get("tag") or raw.get("utmCampaign") or raw.get("campaign")),
        traffic_source=_string_from_any(traffic_source_name or raw.get("traffic_source")),
        creative_name=_string_from_any(creative_name or raw.get("creative_name") or raw.get("adName")),
        email=_string_from_any(raw.get("email")),
        raw=raw,
    )


def _parse_purchase(raw: dict[str, Any]) -> HyrosPurchase:
    product = (
        raw.get("product")
        or raw.get("productName")
        or raw.get("product_name")
        or raw.get("name")
        or raw.get("lead")
        or raw.get("offer")
    )
    purchased_at = _parse_datetime(
        raw.get("purchaseDate")
        or raw.get("purchase_date")
        or raw.get("createdAt")
        or raw.get("created_at")
        or raw.get("date")
    )
    return HyrosPurchase(
        product=_string_from_any(product),
        purchased_at=purchased_at,
        raw=raw,
        name=_string_from_any(raw.get("name") or raw.get("full_name") or raw.get("customer_name")),
        origin_source=_string_from_any(raw.get("origin_source") or raw.get("origin") or raw.get("utm_campaign")),
    )


def _parse_lead(raw: dict[str, Any]) -> HyrosLead:
    tags_raw = raw.get("tags")
    tags = [str(tag).strip() for tag in tags_raw if str(tag).strip()] if isinstance(tags_raw, list) else []
    purchases = [_parse_purchase(purchase) for purchase in _extract_rows(raw.get("purchases"))]
    return HyrosLead(
        id=_string_from_any(raw.get("id")),
        email=_string_from_any(raw.get("email")),
        first_name=_string_from_any(raw.get("firstName") or raw.get("first_name")),
        last_name=_string_from_any(raw.get("lastName") or raw.get("last_name")),
        tags=tags,
        first_source=_extract_source(raw.get("firstSource") or raw.get("first_source")),
        last_source=_extract_source(raw.get("lastSource") or raw.get("last_source")),
        origin_lead=_extract_source(raw.get("originLead") or raw.get("origin_lead")),
        purchases=purchases,
        raw=raw,
    )


def _best_purchase(lead: HyrosLead) -> HyrosPurchase | None:
    if not lead.purchases:
        return None
    return sorted(
        lead.purchases,
        key=lambda purchase: purchase.purchased_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )[0]


def _resolve_api_key(api_key: str | None = None, org: Organization | None = None) -> str | None:
    if api_key:
        return api_key
    if settings.hyros_api_key:
        return settings.hyros_api_key
    if org and org.hyros_api_key:
        try:
            return decrypt_value(org.hyros_api_key)
        except Exception:
            logger.warning("Failed to decrypt hyros_api_key for org=%s", org.id)
            return None
    return None


class HyrosService:
    """Thin Hyros API wrapper used by conversion and cron workflows."""

    def __init__(self, base_url: str = _HYROS_BASE_URL, timeout_seconds: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def fetch_leads(self, api_key: str | None = None, *, org: Organization | None = None) -> list[HyrosLead]:
        resolved_api_key = _resolve_api_key(api_key, org)
        if not resolved_api_key:
            return []

        body = await self._get_json(_HYROS_LEADS_PATH, resolved_api_key)
        return [_parse_lead(row) for row in _extract_rows(body)]

    async def get_lead(self, lead_id: str, api_key: str | None = None, *, org: Organization | None = None) -> HyrosLead | None:
        resolved_api_key = _resolve_api_key(api_key, org)
        if not resolved_api_key or not lead_id:
            return None

        body = await self._get_json(f"{_HYROS_LEADS_PATH}/{lead_id}", resolved_api_key)
        rows = _extract_rows(body)
        if rows:
            return _parse_lead(rows[0])
        if isinstance(body, dict):
            return _parse_lead(body)
        return None

    async def get_purchases(self, lead_id: str, api_key: str | None = None, *, org: Organization | None = None) -> list[HyrosPurchase]:
        lead = await self.get_lead(lead_id, api_key, org=org)
        return lead.purchases if lead else []

    async def fetch_sales(self, api_key: str | None = None, *, org: Organization | None = None) -> list[HyrosSale]:
        resolved_api_key = _resolve_api_key(api_key, org)
        if not resolved_api_key:
            return []

        try:
            body = await self._get_json("/v1/api/v1.0/sales", resolved_api_key)
            rows = _extract_rows(body)
            sales = []
            for row in rows:
                lead_data = row.get("lead") or {}
                tags = lead_data.get("tags") or []
                
                # Extract product: find tag starting with $ and strip it
                product = None
                for tag in tags:
                    if isinstance(tag, str) and tag.startswith("$"):
                        product = tag[1:]
                        break
                
                first_source = row.get("firstSource") or {}
                
                sales.append(
                    HyrosSale(
                        id=_string_from_any(row.get("id")),
                        order_id=_string_from_any(row.get("orderId")),
                        created_at=_parse_datetime(row.get("creationDate")),
                        lead_email=_string_from_any(lead_data.get("email")),
                        lead_first_name=_string_from_any(lead_data.get("firstName")),
                        lead_last_name=_string_from_any(lead_data.get("lastName")),
                        lead_id=_string_from_any(lead_data.get("id")),
                        lead_tags=tags,
                        product=product,
                        first_source_name=_string_from_any(first_source.get("name")),
                        first_source_tag=_string_from_any(first_source.get("tag")),
                        raw=row,
                    )
                )
            return sales
        except Exception as exc:
            logger.warning("Hyros fetch_sales failed: %s", exc)
            return []

    async def _get_json(self, path: str, api_key: str) -> Any:
        url = f"{self.base_url}{path}"
        logger.debug("Hyros key prefix: %s", api_key[:15] if api_key else "NONE")
        headers = {
            "API-Key": api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            logger.warning("Hyros request failed: %s", exc)
            return []
        except Exception as exc:
            logger.warning("Hyros unexpected error: %s", exc)
            return []


def match_lead(
    leads: list[HyrosLead],
    *,
    subscriber_email: str | None,
    subscriber_name: str | None,
) -> HyrosLeadMatch | None:
    """
    Match subscriber against Hyros leads using strict priority:
    1. Email match (most reliable)
    2. Name fallback (case-insensitive)
    3. originLead email match
    """
    target_email = _normalize(subscriber_email)
    target_name = _normalize(subscriber_name)

    # Priority 1 — Email match
    if target_email:
        for lead in leads:
            if _normalize(lead.email) == target_email:
                return HyrosLeadMatch(lead=lead, matched_by="email")

    # Priority 2 — Name fallback (firstName + lastName)
    if target_name:
        for lead in leads:
            if _normalize(_lead_full_name(lead)) == target_name:
                return HyrosLeadMatch(lead=lead, matched_by="name")

    # Priority 3 — originLead email
    if target_email:
        for lead in leads:
            origin_email = lead.origin_lead.email if lead.origin_lead else None
            if _normalize(origin_email) == target_email:
                return HyrosLeadMatch(lead=lead, matched_by="origin_lead")

    return None


def match_purchase(
    purchases: list[HyrosPurchase],
    *,
    subscriber_name: str,
    subscriber_utm_campaign: str,
) -> HyrosPurchase | None:
    target_name = _normalize(subscriber_name)
    target_origin = _normalize(subscriber_utm_campaign)
    for purchase in purchases:
        if _normalize(purchase.name) == target_name and _normalize(purchase.origin_source) == target_origin:
            return purchase
    return None


def _apply_lead_to_subscriber(subscriber: Subscriber, lead: HyrosLead, *, now: datetime) -> None:
    subscriber.hyros_lead_id = lead.id or subscriber.hyros_lead_id
    subscriber.hyros_email = lead.email or subscriber.hyros_email
    if lead.first_source:
        subscriber.hyros_origin_source = lead.first_source.name or subscriber.hyros_origin_source
        subscriber.hyros_origin_tag = lead.first_source.tag or subscriber.hyros_origin_tag
        subscriber.hyros_traffic_source = lead.first_source.traffic_source or subscriber.hyros_traffic_source
        subscriber.hyros_creative_name = lead.first_source.creative_name or subscriber.hyros_creative_name

    purchase = _best_purchase(lead)
    if purchase:
        subscriber.hyros_purchased = True
        subscriber.hyros_product = purchase.product or subscriber.hyros_product
        subscriber.hyros_purchase_date = purchase.purchased_at or subscriber.hyros_purchase_date
    subscriber.hyros_synced_at = now


async def sync_single_subscriber_hyros_purchase(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    subscriber_id: uuid.UUID,
) -> bool:
    """Best-effort check for one subscriber using Hyros lead matching."""
    org_result = await db.execute(
        select(Organization).where(
            Organization.id == org_id,
        )
    )
    org = org_result.scalar_one_or_none()
    if org is None:
        return False

    sub_result = await db.execute(
        select(Subscriber).where(
            Subscriber.id == subscriber_id,
            Subscriber.org_id == org_id,
        )
    )
    subscriber = sub_result.scalar_one_or_none()
    if subscriber is None:
        return False

    api_key = _resolve_api_key(org=org)
    if not api_key:
        return False

    now = datetime.now(timezone.utc)
    service = HyrosService()

    if subscriber.hyros_lead_id:
        lead = await service.get_lead(subscriber.hyros_lead_id, api_key, org=org)
        if lead:
            _apply_lead_to_subscriber(subscriber, lead, now=now)
            return True
        subscriber.hyros_synced_at = now
        return False

    # Email is required for reliable Hyros matching.  Without it we can only
    # fall back to name matching which is unreliable and frequently wrong.
    # Log a clear warning so ops can investigate missing email capture.
    if not subscriber.email:
        logger.warning(
            "Hyros sync skipped for subscriber=%s (org=%s): no email on record — "
            "Hyros cannot match this lead without an email address",
            subscriber.manychat_subscriber_id,
            org_id,
        )
        subscriber.hyros_synced_at = now
        await db.commit()
        return False

    leads = await service.fetch_leads(api_key, org=org)
    match = match_lead(
        leads,
        subscriber_email=subscriber.email,
        subscriber_name=_subscriber_full_name(subscriber),
    )
    subscriber.hyros_synced_at = now
    if match:
        _apply_lead_to_subscriber(subscriber, match.lead, now=now)
        return True
    return False
