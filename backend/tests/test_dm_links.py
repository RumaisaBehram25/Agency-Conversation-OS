"""Unit tests for `build_dm_link` (DM attribution query params)."""

import uuid
from urllib.parse import parse_qs, urlparse

import pytest

from app.utils.dm_links import DmSubscriberView, build_dm_link


def test_build_dm_link_all_identity_and_utm_present() -> None:
    uid = uuid.uuid4()
    sub = DmSubscriberView(manychat_subscriber_id="mc_x", id=uid)
    url = build_dm_link(
        "https://example.com/p?utm_content=legacy",
        sub,
        "my-campaign",
        "instagram",
    )
    q = parse_qs(urlparse(url).query)
    assert q["utm_medium"] == ["dm"]
    assert q["utm_source"] == ["instagram"]
    assert q["utm_campaign"] == ["my-campaign"]
    assert q["attora_sub"] == ["mc_x"]
    assert q["attora_id"] == [str(uid)]
    assert q["utm_content"] == ["legacy"]
    assert len(q["attora_ts"]) == 1
    assert int(q["attora_ts"][0]) > 0


def test_build_dm_link_omits_attora_id_when_missing() -> None:
    sub = DmSubscriberView(manychat_subscriber_id="mc_only", id=None)
    url = build_dm_link(
        "https://example.com/path",
        sub,
        "c1",
        "sms",
    )
    assert "attora_sub=" in url
    assert "attora_id" not in url


def test_build_dm_link_omits_attora_sub_when_missing() -> None:
    uid = uuid.uuid4()
    sub = DmSubscriberView(manychat_subscriber_id=None, id=uid)
    url = build_dm_link("https://e.com/", sub, "c", "fb")
    assert "attora_sub" not in url
    assert f"attora_id={uid}" in url


def test_build_dm_link_omits_both_identity_fields() -> None:
    sub = DmSubscriberView(manychat_subscriber_id=None, id=None)
    url = build_dm_link("https://e.com/page", sub, "slug", "ig")
    assert "attora_sub" not in url
    assert "attora_id" not in url
    assert "utm_medium=dm" in url


@pytest.mark.parametrize(
    ("mc", "aid", "expect_sub", "expect_id"),
    [
        ("a", None, True, False),
        (None, str(uuid.uuid4()), False, True),
        ("x", str(uuid.uuid4()), True, True),
    ],
)
def test_dm_subscriber_view_from_strings(
    mc: str | None, aid: str | None, expect_sub: bool, expect_id: bool
) -> None:
    view = DmSubscriberView.from_strings(mc, aid)
    assert bool(view.manychat_subscriber_id) is expect_sub
    assert (view.id is not None) is expect_id


def test_dm_subscriber_view_invalid_uuid_yields_no_id() -> None:
    view = DmSubscriberView.from_strings("mc", "not-a-uuid")
    assert view.manychat_subscriber_id == "mc"
    assert view.id is None
