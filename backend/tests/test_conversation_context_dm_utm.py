"""DM UTM hints on ConversationContext align with ``build_dm_link`` output."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.ai_engine import ConversationContext, SubscriberContext
from app.services import context_manager
from app.utils.dm_links import DmSubscriberView, build_dm_link


def test_build_dm_link_uses_populated_dm_utm_context_fields() -> None:
    """When ``dm_utm_campaign`` / ``dm_utm_source`` are set, catalog URLs stamp identically."""
    uid = uuid.uuid4()
    sub = SubscriberContext(
        subscriber_id="mc_lead",
        attora_id=str(uid),
        buyer_stage="awareness",
        channel="instagram",
    )
    ctx = ConversationContext(
        org_id=str(uuid.uuid4()),
        subscriber=sub,
        history=[],
        current_message="hi",
        message_count=0,
        dm_utm_campaign="summer-bundle",
        dm_utm_source="instagram",
    )
    base = "https://merchant.example/p"
    stamped = build_dm_link(
        base,
        DmSubscriberView.from_strings(ctx.subscriber.subscriber_id, ctx.subscriber.attora_id),
        ctx.dm_utm_campaign or "",
        ctx.dm_utm_source or "",
    )
    assert "attora_sub=mc_lead" in stamped
    assert f"attora_id={uid}" in stamped
    assert "utm_campaign=summer-bundle" in stamped
    assert "utm_source=instagram" in stamped
    assert "utm_medium=dm" in stamped


@pytest.mark.asyncio
async def test_load_conversation_context_sets_dm_utm_from_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        context_manager,
        "_get_or_create_subscriber",
        AsyncMock(return_value=_fake_subscriber()),
    )
    monkeypatch.setattr(
        context_manager,
        "_get_or_create_conversation",
        AsyncMock(return_value=_fake_conversation()),
    )
    monkeypatch.setattr(
        context_manager,
        "_load_message_history",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.context_manager.resolve_dm_utm_hints",
        AsyncMock(return_value=("resolved-campaign", "resolved-src")),
    )

    db = MagicMock()
    ctx = await context_manager.load_conversation_context(
        org_id=uuid.uuid4(),
        subscriber_id="mc-xyz",
        current_message="yo",
        channel="messenger",
        db=db,
    )
    assert ctx.dm_utm_campaign == "resolved-campaign"
    assert ctx.dm_utm_source == "resolved-src"


def _fake_subscriber():
    """Minimal subscriber row for ``load_conversation_context``."""
    oid = uuid.uuid4()
    return SimpleNamespace(
        id=uuid.uuid4(),
        org_id=oid,
        manychat_subscriber_id="mc-xyz",
        first_name=None,
        last_name=None,
        buyer_stage=MagicMock(value="awareness"),
        interests=[],
        objections_raised=[],
        conversation_summary=None,
        total_messages=0,
        ctwa_clid=None,
        ad_id=None,
        post_id=None,
        attora_campaign_id=None,
        hyros_lead_id=None,
        hyros_email=None,
        hyros_origin_source=None,
        hyros_origin_tag=None,
        hyros_traffic_source=None,
        hyros_creative_name=None,
        hyros_purchased=False,
        hyros_product=None,
        hyros_purchase_date=None,
        hyros_synced_at=None,
    )


def _fake_conversation():
    return SimpleNamespace(
        id=uuid.uuid4(),
        message_count=0,
    )
