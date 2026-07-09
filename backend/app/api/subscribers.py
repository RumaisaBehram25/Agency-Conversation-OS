"""
Attora — Subscriber/Leads API Routes

GET  /api/subscribers          — Paginated list with filters
GET  /api/subscribers/{id}     — Full subscriber detail
"""

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select

from app.models.conversation import Conversation
from app.models.message import Message
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
    date_from: date | None = Query(
        None,
        description="Inclusive start (UTC): latest message across lead's conversations.",
    ),
    date_to: date | None = Query(
        None,
        description="Inclusive end (UTC): latest message across lead's conversations.",
    ),
    is_converted: bool | None = Query(None),
    hyros_status: str | None = Query(None),
    is_test: bool | None = Query(None, description="True=playground (attora_test* subscribers), False=real clients only, None=all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[SubscriberListItem]:
    """
    List subscribers/leads with filtering and pagination.

    ``date_from`` / ``date_to`` filter by latest message time across all of the
    subscriber's conversations (max ``messages.created_at``), falling back to
    ``subscriber.created_at`` when they have no messages.
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

    subscriber_last_msg_ts = (
        select(func.max(Message.created_at))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.subscriber_id == Subscriber.id)
        .scalar_subquery()
    )
    subscriber_activity_ts = func.coalesce(subscriber_last_msg_ts, Subscriber.created_at)

    if date_from:
        dt_from = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
        query = query.where(subscriber_activity_ts >= dt_from)
        count_query = count_query.where(subscriber_activity_ts >= dt_from)

    if date_to:
        dt_to = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)
        query = query.where(subscriber_activity_ts <= dt_to)
        count_query = count_query.where(subscriber_activity_ts <= dt_to)

    if is_converted is not None:
        query = query.where(Subscriber.is_converted == is_converted)
        count_query = count_query.where(Subscriber.is_converted == is_converted)

    if hyros_status:
        if hyros_status == "purchased":
            query = query.where(Subscriber.hyros_purchased.is_(True))
            count_query = count_query.where(Subscriber.hyros_purchased.is_(True))
        elif hyros_status == "lead":
            query = query.where(Subscriber.hyros_synced_at.is_not(None), Subscriber.hyros_purchased.is_(False))
            count_query = count_query.where(Subscriber.hyros_synced_at.is_not(None), Subscriber.hyros_purchased.is_(False))
        elif hyros_status == "unknown":
            query = query.where(Subscriber.hyros_synced_at.is_(None))
            count_query = count_query.where(Subscriber.hyros_synced_at.is_(None))
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid hyros_status. Must be one of: purchased, lead, unknown",
            )

    if is_test is not None:
        if is_test:
            query = query.where(Subscriber.manychat_subscriber_id.like("attora_test%"))
            count_query = count_query.where(Subscriber.manychat_subscriber_id.like("attora_test%"))
        else:
            query = query.where(~Subscriber.manychat_subscriber_id.like("attora_test%"))
            count_query = count_query.where(~Subscriber.manychat_subscriber_id.like("attora_test%"))

    # Count total
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering.
    # Sort by latest message activity (max(message.created_at) coalesced to
    # subscriber.created_at) so the Leads list mirrors the Conversations list
    # ordering — recent inbound/outbound traffic floats to the top instead of
    # ranking purely by when the subscriber row was first created.
    offset = (page - 1) * page_size
    query = (
        query.order_by(
            subscriber_activity_ts.desc().nullslast(),
            Subscriber.created_at.desc(),
        )
        .offset(offset)
        .limit(page_size)
    )

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
            utm_source=sub.utm_source,
            utm_medium=sub.utm_medium,
            utm_campaign=sub.utm_campaign,
            utm_content=sub.utm_content,
            hyros_purchased=sub.hyros_purchased,
            hyros_product=sub.hyros_product,
            hyros_synced_at=sub.hyros_synced_at,
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
            summary=conv.summary,
            closed_at=conv.closed_at,
            follow_up_attempts=conv.follow_up_attempts,
            last_follow_up_at=conv.last_follow_up_at,
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
        hyros_purchased=subscriber.hyros_purchased,
        hyros_product=subscriber.hyros_product,
        hyros_purchase_date=subscriber.hyros_purchase_date,
        hyros_lead_id=subscriber.hyros_lead_id,
        hyros_email=subscriber.hyros_email,
        hyros_origin_source=subscriber.hyros_origin_source,
        hyros_origin_tag=subscriber.hyros_origin_tag,
        hyros_traffic_source=subscriber.hyros_traffic_source,
        hyros_creative_name=subscriber.hyros_creative_name,
        hyros_synced_at=subscriber.hyros_synced_at,
        first_message_at=subscriber.first_message_at,
        last_message_at=subscriber.last_message_at,
        total_messages=subscriber.total_messages,
        utm_source=subscriber.utm_source,
        utm_medium=subscriber.utm_medium,
        utm_campaign=subscriber.utm_campaign,
        utm_content=subscriber.utm_content,
        ctwa_clid=subscriber.ctwa_clid,
        ad_id=subscriber.ad_id,
        post_id=subscriber.post_id,
        ad_set_id=subscriber.ad_set_id,
        campaign_id=subscriber.campaign_id,
        attora_campaign_id=subscriber.attora_campaign_id,
        last_user_message_at=subscriber.last_user_message_at,
        history=subscriber.history,
        created_at=subscriber.created_at,
        updated_at=subscriber.updated_at,
        conversations=conversation_summaries,
    )


@router.delete(
    "/{subscriber_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_subscriber(
    subscriber_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Delete a subscriber and all their related data.

    Cascades via FK constraints to: conversations → messages,
    and conversion_events tied to this subscriber.
    """
    result = await db.execute(
        select(Subscriber)
        .where(Subscriber.id == subscriber_id)
        .where(Subscriber.org_id == org_id)
    )
    subscriber = result.scalar_one_or_none()

    if subscriber is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscriber not found",
        )

    await db.delete(subscriber)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
