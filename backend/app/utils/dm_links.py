"""
Attora — DM / outbound link stamping

Consistent query params for links sent to subscribers (Instagram DM, SMS,
ManyChat, AI replies): identity + UTM, with `utm_medium=dm`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.schemas.campaign import build_utm_url


@dataclass(frozen=True)
class DmSubscriberView:
    """Minimal subscriber shape for `build_dm_link`."""

    manychat_subscriber_id: str | None
    id: uuid.UUID | None = None

    @classmethod
    def from_strings(
        cls,
        manychat_subscriber_id: str | None,
        attora_id: str | None,
    ) -> DmSubscriberView:
        aid: uuid.UUID | None = None
        if attora_id:
            raw = str(attora_id).strip()
            if raw:
                try:
                    aid = uuid.UUID(raw)
                except ValueError:
                    aid = None
        ms_raw = manychat_subscriber_id
        ms = (
            str(ms_raw).strip()
            if ms_raw is not None and str(ms_raw).strip()
            else None
        )
        return cls(manychat_subscriber_id=ms, id=aid)


def _resolve_attora_uuid(subscriber: Any) -> uuid.UUID | None:
    raw = getattr(subscriber, "id", None)
    if isinstance(raw, uuid.UUID):
        return raw
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw).strip())
    except ValueError:
        return None


def _resolve_manychat_id(subscriber: Any) -> str | None:
    mc = getattr(subscriber, "manychat_subscriber_id", None)
    if mc is None:
        return None
    s = str(mc).strip()
    return s or None


def build_dm_link(
    base_url: str,
    subscriber: Any,
    campaign_id: str,
    source: str,
) -> str:
    """
    Append DM attribution query params, merging with any existing query string.

    Identity and UTM params are omitted when their values are missing;
    ``utm_medium`` (always ``dm``) and ``attora_ts`` (unix seconds at stamp time)
    are always set so each outbound link is unique for attribution tools.

    Optional params (stripped; blank omitted):
      - attora_sub, attora_id — subscriber identity for conversion tracking
      - utm_source ← ``source``, utm_campaign ← ``campaign_id``
    """
    params: dict[str, str] = {
        "utm_medium": "dm",
        "attora_ts": str(int(datetime.now().timestamp())),
    }

    src = str(source).strip() if source else ""
    if src:
        params["utm_source"] = src

    camp = str(campaign_id).strip() if campaign_id else ""
    if camp:
        params["utm_campaign"] = camp

    attora_sub = _resolve_manychat_id(subscriber)
    if attora_sub:
        params["attora_sub"] = attora_sub

    att_uuid = _resolve_attora_uuid(subscriber)
    if att_uuid is not None:
        params["attora_id"] = str(att_uuid)

    return build_utm_url(base_url, params)
