"""
Simulate landing URL (DM-stamped) → checkout click with param carry-over.

The storefront bridge (`docs/storefront-attribution.js`) merges tracked query
keys onto outbound checkout links. We model that with `build_utm_url` using
flattened landing params — same merge primitive the backend uses.
"""

from urllib.parse import parse_qs, urlparse

import uuid

from app.schemas.campaign import build_utm_url
from app.utils.dm_links import DmSubscriberView, build_dm_link


def _flatten_query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def _simulate_storefront_stamp_checkout(dm_landing_url: str, checkout_base: str) -> str:
    return build_utm_url(checkout_base, _flatten_query(dm_landing_url))


def test_attribution_survives_landing_to_checkout_via_merge() -> None:
    uid = uuid.uuid4()
    sub = DmSubscriberView(manychat_subscriber_id="subscriber_abc", id=uid)
    landing = build_dm_link(
        "https://shop.example.com/products/item",
        sub,
        "spring-sale",
        "instagram",
    )
    checkout = _simulate_storefront_stamp_checkout(
        landing,
        "https://shop.example.com/cart/checkout",
    )
    qs = parse_qs(urlparse(checkout).query)
    assert qs["attora_sub"] == ["subscriber_abc"]
    assert qs["attora_id"] == [str(uid)]
    assert qs["utm_medium"] == ["dm"]
    assert qs["utm_campaign"] == ["spring-sale"]
    assert qs["utm_source"] == ["instagram"]
    assert len(qs["attora_ts"]) == 1 and int(qs["attora_ts"][0]) > 0
