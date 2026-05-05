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
    attora_id: str | None = None
    attora_sub: str | None = None


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
    traffic_source: str | None = None
    creative_name: str | None = None
    purchase_link: str | None = None
    attora_id: str | None = None
    attora_sub: str | None = None


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


_ATTORA_ID_PREFIXES = ("attora_id:", "attora_id=", "attora-id:", "attora-id=")
_ATTORA_SUB_PREFIXES = ("attora_sub:", "attora_sub=", "attora-sub:", "attora-sub=")


def _normalize_identity_key(name: str) -> str | None:
    """Map Hyros field / source names to ``attora_id`` or ``attora_sub``."""
    n = " ".join(name.strip().split()).lower().replace(" ", "_").replace("-", "_")
    if n in ("attora_id", "attoraid"):
        return "attora_id"
    if n in ("attora_sub", "attorasub"):
        return "attora_sub"
    return None


def _apply_identity_name_value(
    attora_id: str | None,
    attora_sub: str | None,
    name_raw: Any,
    value_raw: Any,
) -> tuple[str | None, str | None]:
    """Set id/sub from a display name + value pair (e.g. dynamic source rows)."""
    name_key = _normalize_identity_key(str(name_raw)) if name_raw is not None else None
    val = _string_from_any(value_raw)
    if name_key == "attora_id" and attora_id is None and val:
        attora_id = val
    elif name_key == "attora_sub" and attora_sub is None and val:
        attora_sub = val
    return attora_id, attora_sub


def _extract_from_tag_line(
    attora_id: str | None, attora_sub: str | None, text: str
) -> tuple[str | None, str | None]:
    """Parse ``attora_*`` prefix conventions used in tag strings."""
    cleaned = text.strip()
    lower = cleaned.lower()
    if attora_id is None:
        for prefix in _ATTORA_ID_PREFIXES:
            if lower.startswith(prefix):
                attora_id = cleaned[len(prefix) :].strip() or None
                break
    if attora_sub is None:
        for prefix in _ATTORA_SUB_PREFIXES:
            if lower.startswith(prefix):
                attora_sub = cleaned[len(prefix) :].strip() or None
                break
    return attora_id, attora_sub


def _extract_pairs_from_mapping(
    attora_id: str | None,
    attora_sub: str | None,
    item: dict[str, Any],
) -> tuple[str | None, str | None]:
    """
    Pull identity from a Hyros-style row: name/value, key/value, field keys, etc.
    """
    for name_key, value_key in (
        ("name", "value"),
        ("key", "value"),
        ("fieldName", "value"),
        ("fieldName", "parameterValue"),
        ("name", "parameterValue"),
        ("parameterName", "parameterValue"),
        ("label", "value"),
    ):
        if name_key in item and value_key in item:
            attora_id, attora_sub = _apply_identity_name_value(
                attora_id, attora_sub, item.get(name_key), item.get(value_key)
            )
    # Flat keys sometimes present on source objects
    if attora_id is None:
        attora_id = _string_from_any(
            item.get("attora_id") or item.get("attoraId")
        )
    if attora_sub is None:
        attora_sub = _string_from_any(
            item.get("attora_sub") or item.get("attoraSub")
        )
    # Nested parameter bags (URL / dynamic attribution)
    for nested_key in ("parameters", "params", "utm", "queryParams", "query_parameters"):
        nested = item.get(nested_key)
        if isinstance(nested, dict):
            for nk, vk in nested.items():
                attora_id, attora_sub = _apply_identity_name_value(
                    attora_id, attora_sub, nk, vk
                )
    return attora_id, attora_sub


def _extract_from_object_list(
    attora_id: str | None,
    attora_sub: str | None,
    items: list[Any],
) -> tuple[str | None, str | None]:
    """Walk a list of strings (tag-like) or dicts (sources / dynamic rows)."""
    for item in items:
        if isinstance(item, str) and item.strip():
            attora_id, attora_sub = _extract_from_tag_line(attora_id, attora_sub, item)
        elif isinstance(item, dict):
            attora_id, attora_sub = _extract_pairs_from_mapping(
                attora_id, attora_sub, item
            )
    return attora_id, attora_sub


def _custom_field_like_blocks(raw: dict[str, Any]) -> list[Any]:
    """Keys Hyros may use for custom fields and dynamic source mirrors."""
    blocks: list[Any] = []
    for key in (
        "customFields",
        "custom_fields",
        "customField",
        "fields",
        "dynamicSources",
        "dynamic_sources",
    ):
        blocks.append(raw.get(key))
    return blocks


def _extract_attora_identity(
    raw: dict[str, Any], tags: list[str]
) -> tuple[str | None, str | None]:
    """
    Pull attora_id / attora_sub off a Hyros lead or sale payload.

    Hyros may surface these as:
      1. Tag strings like ``attora_id:<uuid>`` / ``attora_sub=<id>``.
      2. ``customFields`` / ``dynamicSources`` — dict or list of ``{name, value}``.
      3. ``sources`` — Hyros \"dynamic source\" rows (URL/query params) as dicts
         with name/value or nested ``parameters``.
      4. Top-level ``attoraId`` / ``attoraSub`` on the lead object.

    First non-null value wins per field (same precedence as sync matching).
    """
    attora_id: str | None = None
    attora_sub: str | None = None

    for tag in tags:
        if not isinstance(tag, str):
            continue
        attora_id, attora_sub = _extract_from_tag_line(attora_id, attora_sub, tag)

    for candidate in _custom_field_like_blocks(raw):
        if candidate is None:
            continue
        if isinstance(candidate, dict):
            if attora_id is None:
                attora_id = _string_from_any(
                    candidate.get("attora_id") or candidate.get("attoraId")
                )
            if attora_sub is None:
                attora_sub = _string_from_any(
                    candidate.get("attora_sub") or candidate.get("attoraSub")
                )
            for dict_key, dict_val in candidate.items():
                attora_id, attora_sub = _apply_identity_name_value(
                    attora_id, attora_sub, dict_key, dict_val
                )
        elif isinstance(candidate, list):
            for item in candidate:
                if not isinstance(item, dict):
                    continue
                value = _string_from_any(
                    item.get("value") or item.get("parameterValue")
                )
                attora_id, attora_sub = _apply_identity_name_value(
                    attora_id,
                    attora_sub,
                    item.get("name") or item.get("key") or item.get("fieldName"),
                    value,
                )

    for sources_key in ("sources", "Sources"):
        src_list = raw.get(sources_key)
        if isinstance(src_list, list):
            attora_id, attora_sub = _extract_from_object_list(
                attora_id, attora_sub, src_list
            )

    if attora_id is None:
        attora_id = _string_from_any(raw.get("attora_id") or raw.get("attoraId"))
    if attora_sub is None:
        attora_sub = _string_from_any(raw.get("attora_sub") or raw.get("attoraSub"))

    return attora_id, attora_sub


def _parse_lead(raw: dict[str, Any]) -> HyrosLead:
    tags_raw = raw.get("tags")
    tags = [str(tag).strip() for tag in tags_raw if str(tag).strip()] if isinstance(tags_raw, list) else []
    purchases = [_parse_purchase(purchase) for purchase in _extract_rows(raw.get("purchases"))]
    attora_id, attora_sub = _extract_attora_identity(raw, tags)
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
        attora_id=attora_id,
        attora_sub=attora_sub,
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
                tags_raw = lead_data.get("tags") or []
                tags = [
                    str(tag).strip()
                    for tag in tags_raw
                    if isinstance(tag, str) and str(tag).strip()
                ]

                # Extract product: find tag starting with $ and strip it
                product = None
                for tag in tags:
                    if tag.startswith("$"):
                        product = tag[1:]
                        break

                first_source = row.get("firstSource") or {}
                fs = _extract_source(first_source) if isinstance(first_source, dict) else None

                purchase_link = (
                    _string_from_any(row.get("link"))
                    or _string_from_any(row.get("url"))
                    or _string_from_any(row.get("landingPage"))
                    or _string_from_any(row.get("landing_page"))
                    or _string_from_any(row.get("purchaseLink"))
                    or _string_from_any(row.get("pageUrl"))
                )

                # Identity lives on the lead sub-object for sales, with the
                # row itself as a fallback in case Hyros denormalises it.
                attora_id, attora_sub = _extract_attora_identity(lead_data, tags)
                if attora_id is None and attora_sub is None:
                    attora_id, attora_sub = _extract_attora_identity(row, tags)

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
                        traffic_source=fs.traffic_source if fs else None,
                        creative_name=fs.creative_name if fs else None,
                        purchase_link=purchase_link,
                        raw=row,
                        attora_id=attora_id,
                        attora_sub=attora_sub,
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
    subscriber_attora_id: str | None = None,
    subscriber_manychat_id: str | None = None,
) -> HyrosLeadMatch | None:
    """
    Match subscriber against Hyros leads using strict priority:
    0. attora_id match (URL-stamped Attora UUID — most reliable when Hyros is
       configured to capture the param onto the lead).
    0.5. attora_sub match (URL-stamped ManyChat subscriber id).
    1. Email match.
    2. Name fallback (case-insensitive).
    3. originLead email match.
    """
    target_attora_id = _normalize(subscriber_attora_id)
    target_attora_sub = _normalize(subscriber_manychat_id)
    target_email = _normalize(subscriber_email)
    target_name = _normalize(subscriber_name)

    # Priority 0 — attora_id (Attora's internal subscriber UUID)
    if target_attora_id:
        for lead in leads:
            if _normalize(lead.attora_id) == target_attora_id:
                return HyrosLeadMatch(lead=lead, matched_by="attora_id")

    # Priority 0.5 — attora_sub (ManyChat subscriber id)
    if target_attora_sub:
        for lead in leads:
            if _normalize(lead.attora_sub) == target_attora_sub:
                return HyrosLeadMatch(lead=lead, matched_by="attora_sub")

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

    leads = await service.fetch_leads(api_key, org=org)
    match = match_lead(
        leads,
        subscriber_email=subscriber.email,
        subscriber_name=_subscriber_full_name(subscriber),
        subscriber_attora_id=str(subscriber.id),
        subscriber_manychat_id=subscriber.manychat_subscriber_id,
    )
    subscriber.hyros_synced_at = now
    if match:
        _apply_lead_to_subscriber(subscriber, match.lead, now=now)
        return True

    # No match by any path. If we had nothing but a name to go on, log it so
    # ops can spot subscribers with no email/identity capture.
    if not subscriber.email:
        logger.warning(
            "Hyros sync found no match for subscriber=%s (org=%s): no email and "
            "no attora_id/attora_sub captured on the Hyros side",
            subscriber.manychat_subscriber_id,
            org_id,
        )
    return False
