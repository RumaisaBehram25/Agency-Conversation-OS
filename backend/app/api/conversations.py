"""
Attora — Conversation API Routes

GET  /api/conversations          — Paginated list with filters
GET  /api/conversations/{id}     — Full conversation detail with messages
"""

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.subscriber import Subscriber
from app.models.user import User
from app.models.base import ChannelType, ConversationStatus
from app.schemas.conversation import (
    ConversationDetail,
    ConversationListItem,
    ConversationSubscriberInfo,
    MessageResponse,
)
from app.schemas.pagination import PaginatedResponse
from app.api.deps import get_current_user, get_org_id

router = APIRouter()


@router.get("", response_model=PaginatedResponse[ConversationListItem])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
    channel: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[ConversationListItem]:
    """
    List conversations with filtering and pagination.

    Includes subscriber name, last message preview, buyer stage, and message count.
    """
    # Base query
    query = (
        select(Conversation)
        .where(Conversation.org_id == org_id)
        .options(selectinload(Conversation.subscriber))
    )

    # Apply filters
    if status_filter:
        try:
            conv_status = ConversationStatus(status_filter)
            query = query.where(Conversation.status == conv_status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. Must be one of: {[s.value for s in ConversationStatus]}",
            )

    if channel:
        try:
            channel_type = ChannelType(channel)
            query = query.where(Conversation.channel == channel_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid channel: {channel}. Must be one of: {[c.value for c in ChannelType]}",
            )

    if date_from:
        query = query.where(
            Conversation.created_at >= datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
        )

    if date_to:
        query = query.where(
            Conversation.created_at < datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)
        )

    # Count total
    count_query = (
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.org_id == org_id)
    )
    # Re-apply filters to count query
    if status_filter:
        count_query = count_query.where(Conversation.status == ConversationStatus(status_filter))
    if channel:
        count_query = count_query.where(Conversation.channel == ChannelType(channel))
    if date_from:
        count_query = count_query.where(
            Conversation.created_at >= datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
        )
    if date_to:
        count_query = count_query.where(
            Conversation.created_at < datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    offset = (page - 1) * page_size
    query = query.order_by(Conversation.last_activity_at.desc().nullslast()).offset(offset).limit(page_size)

    result = await db.execute(query)
    conversations = result.scalars().all()

    # Build response items with last message preview
    items = []
    for conv in conversations:
        # Prefer the persisted preview, but fall back to the latest message.
        last_message_preview = conv.last_message_preview
        if last_message_preview is None:
            last_msg_result = await db.execute(
                select(Message.content)
                .where(Message.conversation_id == conv.id)
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            last_message = last_msg_result.scalar_one_or_none()
            last_message_preview = last_message[:100] if last_message else None

        subscriber = conv.subscriber
        subscriber_name = None
        buyer_stage = None
        if subscriber:
            parts = [subscriber.first_name, subscriber.last_name]
            subscriber_name = " ".join(p for p in parts if p) or None
            buyer_stage = subscriber.buyer_stage.value if subscriber.buyer_stage else None

        items.append(
            ConversationListItem(
                id=conv.id,
                subscriber_id=conv.subscriber_id,
                subscriber_name=subscriber_name,
                channel=conv.channel.value,
                status=conv.status.value,
                buyer_stage=buyer_stage,
                message_count=conv.message_count,
                last_message_preview=last_message_preview,
                started_at=conv.started_at,
                last_activity_at=conv.last_activity_at,
                created_at=conv.created_at,
            )
        )

    return PaginatedResponse[ConversationListItem](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetail:
    """
    Get full conversation detail including all messages and subscriber info.
    """
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .where(Conversation.org_id == org_id)
        .options(
            selectinload(Conversation.subscriber),
            selectinload(Conversation.messages),
        )
    )
    conv = result.scalar_one_or_none()

    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Build subscriber info
    subscriber_info = None
    if conv.subscriber:
        subscriber_info = ConversationSubscriberInfo(
            id=conv.subscriber.id,
            first_name=conv.subscriber.first_name,
            last_name=conv.subscriber.last_name,
            channel=conv.subscriber.channel.value,
            buyer_stage=conv.subscriber.buyer_stage.value,
        )

    # Build messages list, ordered by created_at
    messages = sorted(conv.messages, key=lambda m: m.created_at)
    message_responses = [
        MessageResponse(
            id=msg.id,
            sender=msg.sender.value,
            content=msg.content,
            intent_signals=msg.intent_signals,
            buyer_stage_at_time=msg.buyer_stage_at_time.value if msg.buyer_stage_at_time else None,
            compliance_flags=msg.compliance_flags,
            ai_model=msg.ai_model,
            ai_response_time_ms=msg.ai_response_time_ms,
            ai_tokens_used=msg.ai_tokens_used,
            quick_replies=msg.quick_replies,
            created_at=msg.created_at,
        )
        for msg in messages
    ]

    return ConversationDetail(
        id=conv.id,
        subscriber_id=conv.subscriber_id,
        channel=conv.channel.value,
        status=conv.status.value,
        summary=conv.summary,
        message_count=conv.message_count,
        ai_response_time_avg_ms=conv.ai_response_time_avg_ms,
        started_at=conv.started_at,
        last_activity_at=conv.last_activity_at,
        closed_at=conv.closed_at,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        subscriber=subscriber_info,
        messages=message_responses,
    )
