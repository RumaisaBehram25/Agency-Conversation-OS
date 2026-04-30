"""
POST /api/ai-test/chat
POST /api/ai-test/reset

Admin playground for running the real AI pipeline without needing ManyChat
to be wired up. Uses the same process_message() the webhook uses, so it
exercises product knowledge, UTM injection, buyer-stage classification,
fallbacks, and compliance — everything except the outbound ManyChat send.

Messages are persisted in the normal conversations/messages tables. Use
the /reset endpoint between test runs to start fresh.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_org_id
from app.database import get_db
from app.models.base import UserRole
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.subscriber import Subscriber
from app.models.user import OrgUser, User
from app.redis import get_redis_pool
from app.schemas.ai_test import (
    AITestChatRequest,
    AITestChatResponse,
    AITestResetRequest,
    AITestResetResponse,
)
from app.services.ai_engine import _load_subscriber_tagged_urls, process_message

logger = logging.getLogger(__name__)

router = APIRouter()


async def _require_admin(
    db: AsyncSession,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    result = await db.execute(
        select(OrgUser)
        .where(OrgUser.user_id == user_id)
        .where(OrgUser.org_id == org_id)
    )
    membership = result.scalar_one_or_none()
    if membership is None or membership.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Requires owner or admin role.",
        )


@router.post("/chat", response_model=AITestChatResponse)
async def ai_test_chat(
    body: AITestChatRequest,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> AITestChatResponse:
    """
    Run one message through the real AI pipeline for the current org.

    Auto-creates the test subscriber if it doesn't exist. Persists to the
    normal conversations/messages tables so you can review history.
    """
    await _require_admin(db, current_user.id, org_id)

    # Enforce the attora_test_ prefix so playground subscribers always land
    # in the Playground section (filtered by manychat_subscriber_id LIKE 'attora_test%').
    subscriber_id = body.subscriber_id
    if not subscriber_id.startswith("attora_test"):
        subscriber_id = f"attora_test_{subscriber_id}"

    redis_client = None
    try:
        redis_client = get_redis_pool()
    except Exception:
        pass  # Redis is optional for context caching

    try:
        ai_response = await process_message(
            org_id=org_id,
            subscriber_id=subscriber_id,
            message=body.message,
            channel=body.channel,
            custom_fields=body.custom_fields or {},
            db=db,
            redis_client=redis_client,
        )
    except Exception as e:
        logger.exception("ai-test/chat pipeline failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI pipeline failed: {e}",
        )

    # Look up the subscriber's campaign attribution + the tagged URLs that
    # the pipeline just computed. This is surfaced in the response so the
    # playground can show what the AI saw in its prompt.
    sub_result = await db.execute(
        select(Subscriber).where(
            Subscriber.org_id == org_id,
            Subscriber.manychat_subscriber_id == subscriber_id,
        )
    )
    subscriber = sub_result.scalar_one_or_none()

    tagged_urls: dict[str, str] = {}
    attora_campaign_id: str | None = None
    if subscriber and subscriber.attora_campaign_id:
        attora_campaign_id = str(subscriber.attora_campaign_id)
        tagged_urls = await _load_subscriber_tagged_urls(
            db=db,
            org_id=org_id,
            attora_campaign_id=attora_campaign_id,
            subscriber_id=body.subscriber_id,
            attora_id=str(subscriber.id),
        )

    return AITestChatResponse(
        response_text=ai_response.response_text,
        buyer_stage=ai_response.buyer_stage,
        model_used=getattr(ai_response, "model_used", None),
        response_time_ms=getattr(ai_response, "response_time_ms", None),
        quick_replies=getattr(ai_response, "suggested_quick_replies", []) or [],
        conversion_ready=getattr(ai_response, "conversion_ready", False),
        needs_human_handoff=getattr(ai_response, "needs_human_handoff", False),
        handoff_reason=getattr(ai_response, "handoff_reason", None),
        compliance_flags=getattr(ai_response, "compliance_flags", []) or [],
        attora_campaign_id=attora_campaign_id,
        subscriber_tagged_urls=tagged_urls,
    )


@router.post("/reset", response_model=AITestResetResponse)
async def ai_test_reset(
    body: AITestResetRequest,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> AITestResetResponse:
    """
    Wipe the test subscriber's conversation history so the next /chat call
    starts fresh. Leaves the subscriber row in place (preserves campaign
    attribution) but resets their buyer_stage + summary.
    """
    await _require_admin(db, current_user.id, org_id)

    # Apply the same prefix normalization as the chat endpoint.
    subscriber_id = body.subscriber_id
    if not subscriber_id.startswith("attora_test"):
        subscriber_id = f"attora_test_{subscriber_id}"

    sub_result = await db.execute(
        select(Subscriber).where(
            Subscriber.org_id == org_id,
            Subscriber.manychat_subscriber_id == subscriber_id,
        )
    )
    subscriber = sub_result.scalar_one_or_none()

    if subscriber is None:
        return AITestResetResponse(
            deleted_conversations=0,
            deleted_messages=0,
            subscriber_reset=False,
        )

    convo_rows = await db.execute(
        select(Conversation.id).where(Conversation.subscriber_id == subscriber.id)
    )
    convo_ids = [row for row, in convo_rows.all()]

    deleted_messages = 0
    if convo_ids:
        msg_result = await db.execute(
            delete(Message).where(Message.conversation_id.in_(convo_ids))
        )
        deleted_messages = msg_result.rowcount or 0

    convo_result = await db.execute(
        delete(Conversation).where(Conversation.subscriber_id == subscriber.id)
    )
    deleted_conversations = convo_result.rowcount or 0

    # Reset subscriber state so the next message starts from a clean slate
    from app.models.base import BuyerStage

    subscriber.buyer_stage = BuyerStage.AWARENESS
    subscriber.interests = []
    subscriber.objections_raised = []
    subscriber.conversation_summary = None
    subscriber.history = []
    subscriber.total_messages = 0

    await db.commit()

    return AITestResetResponse(
        deleted_conversations=deleted_conversations,
        deleted_messages=deleted_messages,
        subscriber_reset=True,
    )
