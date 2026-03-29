"""
Attora — Conversation Context Manager

Handles loading and storing conversation context:
- Load last 10 messages from DB (with Redis cache)
- Load subscriber profile
- After response: async store message, update subscriber, update conversation
- Every 4 turns: trigger summarization via Haiku (async, fire-and-forget)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

import anthropic
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.models.base import BuyerStage, ChannelType, ConversationStatus, MessageSender
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.subscriber import Subscriber
from app.schemas.ai_engine import (
    AIResponse,
    ConversationContext,
    MessageContext,
    SubscriberContext,
)

logger = logging.getLogger(__name__)

# Redis cache config
_CONTEXT_CACHE_PREFIX = "convctx:"
_CONTEXT_CACHE_TTL = 600  # 10 minutes

# Summarization config
_SUMMARIZE_EVERY_N_TURNS = 4  # Summarize every 4 user turns
_HAIKU_MODEL = "claude-haiku-4-5-20251001"


async def load_conversation_context(
    org_id: uuid.UUID,
    subscriber_id: str,
    current_message: str,
    channel: str,
    custom_fields: dict | None = None,
    db: AsyncSession | None = None,
    redis_client=None,
) -> ConversationContext:
    """
    Load full conversation context for the AI engine.

    Steps:
    1. Find or create subscriber
    2. Find or create active conversation
    3. Load last 10 messages (Redis cache or DB)
    4. Build ConversationContext

    Args:
        org_id: Organization UUID.
        subscriber_id: ManyChat subscriber ID.
        current_message: The current user message.
        channel: Messaging channel.
        custom_fields: ManyChat custom fields.
        db: Database session.
        redis_client: Optional Redis client for caching.

    Returns:
        ConversationContext with full context for prompt building.
    """
    if db is None:
        raise ValueError("Database session is required")

    custom_fields = custom_fields or {}

    # ── Step 1: Find or create subscriber ──────────────────────
    subscriber = await _get_or_create_subscriber(
        db, org_id, subscriber_id, channel, custom_fields
    )

    # ── Step 2: Find or create active conversation ─────────────
    conversation = await _get_or_create_conversation(
        db, org_id, subscriber.id, channel
    )

    # ── Step 3: Load message history ───────────────────────────
    history = await _load_message_history(
        db, conversation.id, redis_client
    )

    # ── Step 4: Build context ──────────────────────────────────
    sub_context = SubscriberContext(
        subscriber_id=subscriber_id,
        first_name=subscriber.first_name,
        last_name=subscriber.last_name,
        buyer_stage=subscriber.buyer_stage.value if subscriber.buyer_stage else "awareness",
        interests=subscriber.interests or [],
        objections_raised=subscriber.objections_raised or [],
        conversation_summary=subscriber.conversation_summary,
        total_messages=subscriber.total_messages,
        channel=channel,
        ctwa_clid=custom_fields.get("ctwa_clid") or subscriber.ctwa_clid,
        ad_id=custom_fields.get("ad_id") or subscriber.ad_id,
    )

    return ConversationContext(
        org_id=str(org_id),
        conversation_id=str(conversation.id),
        subscriber=sub_context,
        history=history,
        current_message=current_message,
        message_count=conversation.message_count,
    )


async def store_message_and_update_context(
    context: ConversationContext,
    user_message: str,
    ai_response: AIResponse,
    db: AsyncSession | None = None,
    redis_client=None,
) -> None:
    """
    Store the message exchange and update subscriber/conversation.

    This runs as a fire-and-forget task — errors are logged but don't
    affect the response to the user.

    Args:
        context: The conversation context.
        user_message: The user's original message.
        ai_response: The AI's response.
        db: Database session (creates own if None).
        redis_client: Optional Redis client for cache invalidation.
    """
    try:
        async with async_session_factory() as session:
            conversation_id = uuid.UUID(context.conversation_id) if context.conversation_id else None
            if not conversation_id:
                logger.warning("No conversation_id in context, skipping storage")
                return

            now = datetime.now(timezone.utc)

            # ── Store user message ─────────────────────────────
            user_msg = Message(
                conversation_id=conversation_id,
                sender=MessageSender.USER,
                content=user_message,
            )
            session.add(user_msg)

            # ── Store AI message ───────────────────────────────
            ai_msg = Message(
                conversation_id=conversation_id,
                sender=MessageSender.AI,
                content=ai_response.response_text,
                intent_signals=ai_response.intent_signals or None,
                buyer_stage_at_time=BuyerStage(ai_response.buyer_stage) if ai_response.buyer_stage in [s.value for s in BuyerStage] else None,
                compliance_flags=ai_response.compliance_flags or None,
                ai_model=ai_response.model_used,
                ai_response_time_ms=ai_response.response_time_ms,
                ai_tokens_used=ai_response.tokens_used,
                quick_replies=ai_response.suggested_quick_replies or None,
            )
            session.add(ai_msg)

            # ── Update conversation ────────────────────────────
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(
                    message_count=Conversation.message_count + 2,
                    last_activity_at=now,
                    ai_response_time_avg_ms=ai_response.response_time_ms,
                )
            )

            # ── Update subscriber ──────────────────────────────
            sub_updates: dict = {
                "last_message_at": now,
                "total_messages": Subscriber.total_messages + 2,
            }

            # Update buyer stage if changed
            if ai_response.buyer_stage and ai_response.buyer_stage in [s.value for s in BuyerStage]:
                sub_updates["buyer_stage"] = BuyerStage(ai_response.buyer_stage)

            # Append new intent signals to interests
            if ai_response.intent_signals:
                # We can't easily append to ARRAY in SQLAlchemy, so we'll
                # handle this separately if needed
                pass

            # Find subscriber by manychat ID
            sub_result = await session.execute(
                select(Subscriber).where(
                    Subscriber.org_id == uuid.UUID(context.org_id),
                    Subscriber.manychat_subscriber_id == context.subscriber.subscriber_id,
                )
            )
            subscriber = sub_result.scalar_one_or_none()
            if subscriber:
                for key, value in sub_updates.items():
                    setattr(subscriber, key, value)

            await session.commit()

            # ── Invalidate context cache ───────────────────────
            if redis_client and conversation_id:
                cache_key = f"{_CONTEXT_CACHE_PREFIX}{conversation_id}"
                try:
                    await redis_client.delete(cache_key)
                except Exception:
                    pass

            # ── Trigger summarization every N turns ────────────
            new_count = context.message_count + 2
            if new_count > 0 and new_count % (_SUMMARIZE_EVERY_N_TURNS * 2) == 0:
                asyncio.create_task(
                    _trigger_summarization(
                        conversation_id=conversation_id,
                        org_id=uuid.UUID(context.org_id),
                        subscriber_manychat_id=context.subscriber.subscriber_id,
                    )
                )

            logger.debug(
                f"Stored messages for conversation {conversation_id} "
                f"(total: {new_count})"
            )

    except Exception as e:
        logger.error(f"Failed to store message/update context: {e}", exc_info=True)


async def _get_or_create_subscriber(
    db: AsyncSession,
    org_id: uuid.UUID,
    manychat_subscriber_id: str,
    channel: str,
    custom_fields: dict,
) -> Subscriber:
    """Find existing subscriber or create a new one."""
    result = await db.execute(
        select(Subscriber).where(
            Subscriber.org_id == org_id,
            Subscriber.manychat_subscriber_id == manychat_subscriber_id,
        )
    )
    subscriber = result.scalar_one_or_none()

    if subscriber:
        # Update name if available and not already set
        if custom_fields.get("first_name") and not subscriber.first_name:
            subscriber.first_name = custom_fields["first_name"]
        if custom_fields.get("last_name") and not subscriber.last_name:
            subscriber.last_name = custom_fields["last_name"]
        # Update contact info if available
        if custom_fields.get("email") and not subscriber.email:
            subscriber.email = custom_fields["email"]
        if custom_fields.get("phone") and not subscriber.phone:
            subscriber.phone = custom_fields["phone"]
        # Update attribution if available
        if custom_fields.get("ctwa_clid") and not subscriber.ctwa_clid:
            subscriber.ctwa_clid = custom_fields["ctwa_clid"]
        if custom_fields.get("ad_id") and not subscriber.ad_id:
            subscriber.ad_id = custom_fields["ad_id"]
        if custom_fields.get("ad_set_id") and not subscriber.ad_set_id:
            subscriber.ad_set_id = custom_fields["ad_set_id"]
        if custom_fields.get("campaign_id") and not subscriber.campaign_id:
            subscriber.campaign_id = custom_fields["campaign_id"]
        return subscriber

    # Parse channel
    try:
        channel_enum = ChannelType(channel.lower())
    except ValueError:
        channel_enum = ChannelType.MESSENGER

    subscriber = Subscriber(
        org_id=org_id,
        manychat_subscriber_id=manychat_subscriber_id,
        channel=channel_enum,
        first_name=custom_fields.get("first_name"),
        last_name=custom_fields.get("last_name"),
        email=custom_fields.get("email"),
        phone=custom_fields.get("phone"),
        buyer_stage=BuyerStage.AWARENESS,
        first_message_at=datetime.now(timezone.utc),
        ctwa_clid=custom_fields.get("ctwa_clid"),
        ad_id=custom_fields.get("ad_id"),
        ad_set_id=custom_fields.get("ad_set_id"),
        campaign_id=custom_fields.get("campaign_id"),
    )
    db.add(subscriber)
    await db.flush()  # Get the ID assigned
    return subscriber


async def _get_or_create_conversation(
    db: AsyncSession,
    org_id: uuid.UUID,
    subscriber_id: uuid.UUID,
    channel: str,
) -> Conversation:
    """Find an active conversation or create a new one."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.org_id == org_id,
            Conversation.subscriber_id == subscriber_id,
            Conversation.status == ConversationStatus.ACTIVE,
        ).order_by(Conversation.last_activity_at.desc().nullslast())
        .limit(1)
    )
    conversation = result.scalar_one_or_none()

    if conversation:
        return conversation

    try:
        channel_enum = ChannelType(channel.lower())
    except ValueError:
        channel_enum = ChannelType.MESSENGER

    now = datetime.now(timezone.utc)
    conversation = Conversation(
        org_id=org_id,
        subscriber_id=subscriber_id,
        channel=channel_enum,
        status=ConversationStatus.ACTIVE,
        started_at=now,
        last_activity_at=now,
        message_count=0,
    )
    db.add(conversation)
    await db.flush()
    return conversation


async def _load_message_history(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    redis_client=None,
) -> list[MessageContext]:
    """Load last 10 messages from Redis cache or DB."""
    cache_key = f"{_CONTEXT_CACHE_PREFIX}{conversation_id}"

    # Try Redis cache first
    if redis_client:
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                data = json.loads(cached)
                return [MessageContext(**m) for m in data]
        except Exception as e:
            logger.debug(f"Context cache miss/error for {conversation_id}: {e}")

    # Load from database
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    messages = result.scalars().all()

    # Reverse to chronological order
    messages = list(reversed(messages))

    history = [
        MessageContext(
            sender=msg.sender.value,
            content=msg.content,
            timestamp=msg.created_at,
        )
        for msg in messages
    ]

    # Cache in Redis
    if redis_client and history:
        try:
            cache_data = json.dumps(
                [m.model_dump(mode="json") for m in history]
            )
            await redis_client.setex(cache_key, _CONTEXT_CACHE_TTL, cache_data)
        except Exception as e:
            logger.debug(f"Failed to cache context for {conversation_id}: {e}")

    return history


async def _trigger_summarization(
    conversation_id: uuid.UUID,
    org_id: uuid.UUID,
    subscriber_manychat_id: str,
) -> None:
    """
    Summarize conversation history via Haiku (fire-and-forget).

    Called every 4 user turns to keep the conversation summary current.
    """
    try:
        async with async_session_factory() as session:
            # Load all messages
            result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            )
            messages = result.scalars().all()

            if len(messages) < 4:
                return

            # Build conversation text for summarization
            convo_text = "\n".join(
                f"[{msg.sender.value.upper()}]: {msg.content}"
                for msg in messages
            )

            # Call Haiku for summarization
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            response = await client.messages.create(
                model=_HAIKU_MODEL,
                max_tokens=256,
                system=(
                    "Summarize this sales conversation in 2-3 sentences. "
                    "Focus on: customer's needs/interests, objections raised, "
                    "current stage in buying journey, and key topics discussed."
                ),
                messages=[
                    {"role": "user", "content": f"Conversation:\n{convo_text}"}
                ],
            )

            summary = response.content[0].text.strip()

            # Update subscriber conversation_summary
            await session.execute(
                update(Subscriber)
                .where(
                    Subscriber.org_id == org_id,
                    Subscriber.manychat_subscriber_id == subscriber_manychat_id,
                )
                .values(conversation_summary=summary)
            )

            # Update conversation summary
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(summary=summary)
            )

            await session.commit()
            logger.info(
                f"Summarized conversation {conversation_id}: {summary[:100]}..."
            )

    except Exception as e:
        logger.error(
            f"Summarization failed for conversation {conversation_id}: {e}",
            exc_info=True,
        )
