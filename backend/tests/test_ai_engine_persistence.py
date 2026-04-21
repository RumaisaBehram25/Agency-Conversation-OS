"""
Regression tests for ManyChat message persistence in the AI pipeline.

These tests focus on the transaction boundary between request-scoped
subscriber/conversation creation and the background message storage task.
"""

from __future__ import annotations

import asyncio
import types
import uuid
from unittest.mock import AsyncMock

import pytest

from app.models.base import BuyerStage
from app.schemas.ai_engine import (
    AIConfigData,
    AIResponse,
    ConversationContext,
    OrgConfig,
    SubscriberContext,
)


@pytest.mark.asyncio
async def test_process_message_commits_context_before_background_storage(monkeypatch):
    from app.services import ai_engine

    org_id = uuid.uuid4()
    db = AsyncMock()

    context = ConversationContext(
        org_id=str(org_id),
        conversation_id=str(uuid.uuid4()),
        subscriber=SubscriberContext(
            subscriber_id="manychat-123",
            buyer_stage="awareness",
            channel="messenger",
            total_messages=0,
        ),
        history=[],
        current_message="Hello",
        message_count=0,
    )

    org_config = OrgConfig(
        org_id=str(org_id),
        org_name="Test Org",
        org_slug="test-org",
        ai_config=AIConfigData(greeting_message="Hi there"),
        products=[],
    )

    ai_response = AIResponse(
        response_text="Hi there",
        buyer_stage=BuyerStage.AWARENESS.value,
        model_used="test-model",
    )

    monkeypatch.setattr(ai_engine, "load_org_config", AsyncMock(return_value=org_config))
    monkeypatch.setattr(ai_engine, "load_conversation_context", AsyncMock(return_value=context))
    monkeypatch.setattr(
        ai_engine,
        "classify_message",
        AsyncMock(
            return_value=types.SimpleNamespace(
                intent=ai_engine.IntentType.GREETING,
                is_simple=True,
                confidence=1.0,
            )
        ),
    )
    monkeypatch.setattr(ai_engine, "_route_simple_intent", lambda *args, **kwargs: ai_response)
    monkeypatch.setattr(ai_engine, "store_message_and_update_context", AsyncMock(return_value=None))
    monkeypatch.setattr(ai_engine.asyncio, "create_task", lambda coro: asyncio.get_running_loop().create_task(coro))

    result = await ai_engine.process_message(
        org_id=org_id,
        subscriber_id="manychat-123",
        message="Hello",
        channel="messenger",
        custom_fields={},
        db=db,
        redis_client=None,
    )

    assert result.response_text == "Hi there"
    db.commit.assert_awaited()
    assert db.commit.await_count >= 1