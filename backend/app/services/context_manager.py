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
from app.models.campaign import AdCampaign
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
    conversation_id = uuid.UUID(context.conversation_id) if context.conversation_id else None
    logger.info(
        "BACKGROUND MESSAGE WRITER TRIGGERED conversation_id=%s payload.last_input_text=%s",
        conversation_id,
        user_message,
    )

    if not conversation_id:
        logger.warning("No conversation_id in context, skipping storage")
        return

    try:
        async with async_session_factory() as session:
            logger.info("MESSAGE INSERT START conversation_id=%s", conversation_id)
            now = datetime.now(timezone.utc)

            result = await session.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.org_id == uuid.UUID(context.org_id),
                )
            )
            conversation = result.scalar_one_or_none()
            if conversation is None:
                logger.warning(
                    "Conversation not found for background writer conversation_id=%s org_id=%s",
                    conversation_id,
                    context.org_id,
                )
                return

            subscriber_result = await session.execute(
                select(Subscriber).where(
                    Subscriber.org_id == uuid.UUID(context.org_id),
                    Subscriber.manychat_subscriber_id == context.subscriber.subscriber_id,
                )
            )
            subscriber = subscriber_result.scalar_one_or_none()
            if subscriber is None:
                logger.warning(
                    "Subscriber not found for background writer conversation_id=%s manychat_subscriber_id=%s",
                    conversation_id,
                    context.subscriber.subscriber_id,
                )
                return

            user_msg = Message(
                conversation_id=conversation.id,
                sender=MessageSender.USER,
                content=user_message,
            )
            ai_msg = Message(
                conversation_id=conversation.id,
                sender=MessageSender.AI,
                content=ai_response.response_text,
                intent_signals=ai_response.intent_signals or None,
                buyer_stage_at_time=(
                    BuyerStage(ai_response.buyer_stage)
                    if ai_response.buyer_stage in [stage.value for stage in BuyerStage]
                    else None
                ),
                compliance_flags=ai_response.compliance_flags or None,
                ai_model=ai_response.model_used,
                ai_response_time_ms=ai_response.response_time_ms,
                ai_tokens_used=ai_response.tokens_used,
                quick_replies=ai_response.suggested_quick_replies or None,
            )
            session.add_all([user_msg, ai_msg])

            conversation.message_count = (conversation.message_count or 0) + 2
            conversation.last_activity_at = now
            conversation.last_message_preview = ai_response.response_text[:250]
            if ai_response.response_time_ms is not None:
                conversation.ai_response_time_avg_ms = ai_response.response_time_ms

            subscriber.last_message_at = now
            subscriber.total_messages = (subscriber.total_messages or 0) + 2

            if ai_response.buyer_stage in [stage.value for stage in BuyerStage]:
                subscriber.buyer_stage = BuyerStage(ai_response.buyer_stage)

            await session.flush()
            await session.commit()
            logger.info(
                "MESSAGE COMMITTED SUCCESSFULLY conversation_id=%s user_message_length=%s ai_message_length=%s",
                conversation_id,
                len(user_message),
                len(ai_response.response_text),
            )

            if redis_client:
                cache_key = f"{_CONTEXT_CACHE_PREFIX}{conversation_id}"
                try:
                    await redis_client.delete(cache_key)
                except Exception:
                    logger.debug(
                        "Failed to invalidate context cache for conversation_id=%s",
                        conversation_id,
                        exc_info=True,
                    )

            new_count = conversation.message_count
            if new_count > 0 and new_count % (_SUMMARIZE_EVERY_N_TURNS * 2) == 0:
                asyncio.create_task(
                    _trigger_summarization(
                        conversation_id=conversation_id,
                        org_id=uuid.UUID(context.org_id),
                        subscriber_manychat_id=context.subscriber.subscriber_id,
                    )
                )

            logger.debug(
                "Stored messages for conversation %s (total: %s)",
                conversation_id,
                new_count,
            )

    except Exception:
        logger.exception(
            "Failed to store messages/update context conversation_id=%s org_id=%s",
            conversation_id,
            context.org_id,
        )


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
        # Update attribution if available
        if custom_fields.get("ctwa_clid") and not subscriber.ctwa_clid:
            subscriber.ctwa_clid = custom_fields["ctwa_clid"]
        if custom_fields.get("ad_id") and not subscriber.ad_id:
            subscriber.ad_id = custom_fields["ad_id"]
        if custom_fields.get("ad_set_id") and not subscriber.ad_set_id:
            subscriber.ad_set_id = custom_fields["ad_set_id"]
        if custom_fields.get("campaign_id") and not subscriber.campaign_id:
            subscriber.campaign_id = custom_fields["campaign_id"]
        # Auto-link to Attora-managed AdCampaign if not already linked
        if not subscriber.attora_campaign_id:
            await _link_subscriber_to_campaign(db, org_id, subscriber, custom_fields.get("campaign_id") or subscriber.campaign_id)
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
        buyer_stage=BuyerStage.AWARENESS,
        first_message_at=datetime.now(timezone.utc),
        ctwa_clid=custom_fields.get("ctwa_clid"),
        ad_id=custom_fields.get("ad_id"),
        ad_set_id=custom_fields.get("ad_set_id"),
        campaign_id=custom_fields.get("campaign_id"),
    )
    db.add(subscriber)
    await db.flush()
    await _link_subscriber_to_campaign(db, org_id, subscriber, custom_fields.get("campaign_id"))
    return subscriber


async def _link_subscriber_to_campaign(
    db: AsyncSession,
    org_id: uuid.UUID,
    subscriber: Subscriber,
    meta_campaign_id: str | None,
) -> None:
    """
    Look up the Attora-managed AdCampaign matching the subscriber's Meta campaign ID
    and set attora_campaign_id on the subscriber. Logs a compliance warning if
    the campaign_id is present but not registered as an Attora-managed campaign.
    """
    if not meta_campaign_id:
        return

    result = await db.execute(
        select(AdCampaign).where(
            AdCampaign.org_id == org_id,
            AdCampaign.meta_campaign_id == meta_campaign_id,
            AdCampaign.is_attora_managed == True,  # noqa: E712
        )
    )
    campaign = result.scalar_one_or_none()

    if campaign:
        subscriber.attora_campaign_id = campaign.id
        logger.info(
            "Linked subscriber %s to Attora campaign '%s' (%s)",
            subscriber.manychat_subscriber_id,
            campaign.name,
            campaign.id,
        )
    else:
        # Compliance: lead came from a campaign Attora doesn't manage
        logger.warning(
            "COMPLIANCE: subscriber %s has Meta campaign_id=%s but no matching "
            "Attora-managed campaign found for org %s — verify this lead should be contacted",
            subscriber.manychat_subscriber_id,
            meta_campaign_id,
            org_id,
        )


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
