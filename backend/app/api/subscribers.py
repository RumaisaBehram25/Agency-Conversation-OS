"""
Attora — Subscriber/Leads API Routes

GET  /api/subscribers          — Paginated list with filters
GET  /api/subscribers/{id}     — Full subscriber detail
"""

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.subscriber import Subscriber
from app.models.user import User
from app.models.base import BuyerStage, ChannelType
from app.schemas.subscriber import (
    SubscriberConversationSummary,
    SubscriberDetail,
    SubscriberListItem,
    SubscriberUpdate,
)
from app.schemas.pagination import PaginatedResponse
from app.api.deps import get_current_user, get_org_id

router = APIRouter()


@router.get("", response_model=PaginatedResponse[SubscriberListItem])
async def list_subscribers(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    buyer_stage: str | None = Query(None),
    channel: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    is_converted: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[SubscriberListItem]:
    """
    List subscribers/leads with filtering and pagination.
    """
    # Base query
    query = select(Subscriber).where(Subscriber.org_id == org_id)
    count_query = (
        select(func.count())
        .select_from(Subscriber)
        .where(Subscriber.org_id == org_id)
    )

    # Apply filters
    if buyer_stage:
        try:
            stage = BuyerStage(buyer_stage)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid buyer_stage: {buyer_stage}. Must be one of: {[s.value for s in BuyerStage]}",
            )
        query = query.where(Subscriber.buyer_stage == stage)
        count_query = count_query.where(Subscriber.buyer_stage == stage)

    if channel:
        try:
            channel_type = ChannelType(channel)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid channel: {channel}. Must be one of: {[c.value for c in ChannelType]}",
            )
        query = query.where(Subscriber.channel == channel_type)
        count_query = count_query.where(Subscriber.channel == channel_type)

    if date_from:
        dt_from = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
        query = query.where(Subscriber.created_at >= dt_from)
        count_query = count_query.where(Subscriber.created_at >= dt_from)

    if date_to:
        dt_to = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)
        query = query.where(Subscriber.created_at <= dt_to)
        count_query = count_query.where(Subscriber.created_at <= dt_to)

    if is_converted is not None:
        query = query.where(Subscriber.is_converted == is_converted)
        count_query = count_query.where(Subscriber.is_converted == is_converted)

    # Count total
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    offset = (page - 1) * page_size
    query = query.order_by(Subscriber.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    subscribers = result.scalars().all()

    items = [
        SubscriberListItem(
            id=sub.id,
            first_name=sub.first_name,
            last_name=sub.last_name,
            channel=sub.channel.value,
            buyer_stage=sub.buyer_stage.value,
            is_converted=sub.is_converted,
            conversion_value=float(sub.conversion_value) if sub.conversion_value else None,
            total_messages=sub.total_messages,
            first_message_at=sub.first_message_at,
            last_message_at=sub.last_message_at,
            created_at=sub.created_at,
        )
        for sub in subscribers
    ]

    return PaginatedResponse[SubscriberListItem](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{subscriber_id}", response_model=SubscriberDetail)
async def get_subscriber(
    subscriber_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> SubscriberDetail:
    """
    Get full subscriber detail including all conversations and conversion data.
    """
    result = await db.execute(
        select(Subscriber)
        .where(Subscriber.id == subscriber_id)
        .where(Subscriber.org_id == org_id)
        .options(selectinload(Subscriber.conversations))
    )
    subscriber = result.scalar_one_or_none()

    if subscriber is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscriber not found",
        )

    conversation_summaries = [
        SubscriberConversationSummary(
            id=conv.id,
            channel=conv.channel.value,
            status=conv.status.value,
            message_count=conv.message_count,
            started_at=conv.started_at,
            last_activity_at=conv.last_activity_at,
        )
        for conv in sorted(subscriber.conversations, key=lambda c: c.created_at, reverse=True)
    ]

    return SubscriberDetail(
        id=subscriber.id,
        manychat_subscriber_id=subscriber.manychat_subscriber_id,
        channel=subscriber.channel.value,
        first_name=subscriber.first_name,
        last_name=subscriber.last_name,
        phone=subscriber.phone,
        email=subscriber.email,
        buyer_stage=subscriber.buyer_stage.value,
        interests=subscriber.interests,
        objections_raised=subscriber.objections_raised,
        conversation_summary=subscriber.conversation_summary,
        is_converted=subscriber.is_converted,
        conversion_value=float(subscriber.conversion_value) if subscriber.conversion_value else None,
        converted_at=subscriber.converted_at,
        first_message_at=subscriber.first_message_at,
        last_message_at=subscriber.last_message_at,
        total_messages=subscriber.total_messages,
        created_at=subscriber.created_at,
        updated_at=subscriber.updated_at,
        conversations=conversation_summaries,
    )


@router.put("/{subscriber_id}", response_model=SubscriberDetail)
async def update_subscriber(
    subscriber_id: uuid.UUID,
    request: SubscriberUpdate,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> SubscriberDetail:
    """Update subscriber fields — link to campaign, mark converted, etc."""
    result = await db.execute(
        select(Subscriber)
        .where(Subscriber.id == subscriber_id)
        .where(Subscriber.org_id == org_id)
        .options(selectinload(Subscriber.conversations))
    )
    subscriber = result.scalar_one_or_none()

    if subscriber is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")

    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(subscriber, field, value)

    await db.flush()
    await db.refresh(subscriber)

    conversation_summaries = [
        SubscriberConversationSummary(
            id=conv.id,
            channel=conv.channel.value,
            status=conv.status.value,
            message_count=conv.message_count,
            started_at=conv.started_at,
            last_activity_at=conv.last_activity_at,
        )
        for conv in sorted(subscriber.conversations, key=lambda c: c.created_at, reverse=True)
    ]

    return SubscriberDetail(
        id=subscriber.id,
        manychat_subscriber_id=subscriber.manychat_subscriber_id,
        channel=subscriber.channel.value,
        first_name=subscriber.first_name,
        last_name=subscriber.last_name,
        phone=subscriber.phone,
        email=subscriber.email,
        buyer_stage=subscriber.buyer_stage.value,
        interests=subscriber.interests,
        objections_raised=subscriber.objections_raised,
        conversation_summary=subscriber.conversation_summary,
        is_converted=subscriber.is_converted,
        conversion_value=float(subscriber.conversion_value) if subscriber.conversion_value else None,
        converted_at=subscriber.converted_at,
        first_message_at=subscriber.first_message_at,
        last_message_at=subscriber.last_message_at,
        total_messages=subscriber.total_messages,
        created_at=subscriber.created_at,
        updated_at=subscriber.updated_at,
        conversations=conversation_summaries,
    )
