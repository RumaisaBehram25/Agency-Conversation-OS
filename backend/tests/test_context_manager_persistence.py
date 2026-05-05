"""Regression tests for background message persistence."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.models.base import BuyerStage, ChannelType, ConversationStatus, MessageSender
from app.models.conversation import Conversation
from app.models.subscriber import Subscriber
from app.schemas.ai_engine import AIResponse, ConversationContext, SubscriberContext


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, conversation, subscriber):
        self.conversation = conversation
        self.subscriber = subscriber
        self.executed = []
        self.added = []
        self.flush_calls = 0
        self.commit_calls = 0

    async def execute(self, statement):
        self.executed.append(statement)
        # First execute: Conversation bulk update → no ORM scalar row.
        if len(self.executed) == 1:
            return _FakeResult(None)
        # Second: load Subscriber for attribution updates.
        return _FakeResult(self.subscriber)

    def add(self, obj):
        self.added.append(obj)

    def add_all(self, objects):
        self.added.extend(objects)

    async def flush(self):
        self.flush_calls += 1

    async def commit(self):
        self.commit_calls += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_store_message_and_update_context_persists_both_messages(monkeypatch):
    from app.services import context_manager

    org_id = uuid.uuid4()
    conversation_id = uuid.uuid4()

    conversation = Conversation(
        id=conversation_id,
        org_id=org_id,
        subscriber_id=uuid.uuid4(),
        channel=ChannelType.MESSENGER,
        status=ConversationStatus.ACTIVE,
        message_count=0,
    )
    subscriber = Subscriber(
        id=uuid.uuid4(),
        org_id=org_id,
        manychat_subscriber_id="manychat-123",
        channel=ChannelType.MESSENGER,
        buyer_stage=BuyerStage.AWARENESS,
        total_messages=0,
    )

    fake_session = _FakeSession(conversation, subscriber)

    @asynccontextmanager
    async def fake_session_factory():
        yield fake_session

    monkeypatch.setattr(context_manager, "async_session_factory", fake_session_factory)

    context = ConversationContext(
        org_id=str(org_id),
        conversation_id=str(conversation_id),
        subscriber=SubscriberContext(
            subscriber_id="manychat-123",
            buyer_stage="awareness",
            channel="messenger",
        ),
        history=[],
        current_message="Hello",
        message_count=0,
    )
    ai_response = AIResponse(
        response_text="Hi there, how can I help?",
        buyer_stage="awareness",
        model_used="claude-sonnet-4-6",
    )

    await context_manager.store_message_and_update_context(
        context=context,
        user_message="Hello",
        ai_response=ai_response,
        redis_client=None,
    )

    assert fake_session.commit_calls == 1
    assert len(fake_session.added) == 2
    assert fake_session.added[0].sender == MessageSender.USER
    assert fake_session.added[0].content == "Hello"
    assert fake_session.added[1].sender == MessageSender.AI
    assert fake_session.added[1].content == "Hi there, how can I help?"
    # total_messages receives a SQLAlchemy incremental expression before flush — not materialized here.
    assert subscriber.last_message_at is not None