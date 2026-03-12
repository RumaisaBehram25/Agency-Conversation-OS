"""
Attora — Daily Digest Job

Aggregates raw conversation/message/conversion data into the daily_analytics table.
Runs once per day to pre-compute metrics for fast dashboard queries.
"""

import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import DailyAnalytics
from app.models.conversation import Conversation
from app.models.conversion import ConversionEvent
from app.models.message import Message
from app.models.organization import Organization
from app.models.base import ChannelType, ConversationStatus, MessageSender

logger = logging.getLogger("attora.jobs.daily_digest")


async def aggregate_daily_analytics(
    db: AsyncSession,
    target_date: date | None = None,
) -> dict:
    """
    Aggregate raw data into daily_analytics rows for the given date.

    If no target_date is provided, defaults to yesterday.
    Processes all organizations and all channels.
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    day_end = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, tzinfo=timezone.utc)

    # Get all org IDs
    org_result = await db.execute(select(Organization.id))
    org_ids = [row[0] for row in org_result.all()]

    total_rows_created = 0
    total_rows_updated = 0

    for org_id in org_ids:
        # Process each channel + a combined "all" row (channel=None)
        channels_to_process: list[ChannelType | None] = [None] + list(ChannelType)

        for channel in channels_to_process:
            stats = await _compute_org_channel_stats(
                db, org_id, target_date, day_start, day_end, channel
            )

            # Check if a row already exists (upsert)
            existing_result = await db.execute(
                select(DailyAnalytics)
                .where(
                    DailyAnalytics.org_id == org_id,
                    DailyAnalytics.date == target_date,
                    DailyAnalytics.channel == channel if channel else DailyAnalytics.channel.is_(None),
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing:
                # Update existing row
                for key, value in stats.items():
                    setattr(existing, key, value)
                total_rows_updated += 1
            else:
                # Create new row
                analytics_row = DailyAnalytics(
                    org_id=org_id,
                    date=target_date,
                    channel=channel,
                    **stats,
                )
                db.add(analytics_row)
                total_rows_created += 1

    await db.flush()

    logger.info(
        f"Daily digest for {target_date}: {total_rows_created} created, "
        f"{total_rows_updated} updated across {len(org_ids)} orgs"
    )

    return {
        "target_date": target_date.isoformat(),
        "orgs_processed": len(org_ids),
        "rows_created": total_rows_created,
        "rows_updated": total_rows_updated,
        "message": f"Daily digest complete for {target_date}",
    }


async def _compute_org_channel_stats(
    db: AsyncSession,
    org_id: uuid.UUID,
    target_date: date,
    day_start: datetime,
    day_end: datetime,
    channel: ChannelType | None,
) -> dict:
    """Compute analytics stats for a specific org + channel + date."""

    # Conversation filters
    conv_filters = [
        Conversation.org_id == org_id,
        Conversation.created_at >= day_start,
        Conversation.created_at <= day_end,
    ]
    if channel:
        conv_filters.append(Conversation.channel == channel)

    # New conversations started on this day
    new_conv_result = await db.execute(
        select(func.count()).select_from(Conversation).where(and_(*conv_filters))
    )
    new_conversations = new_conv_result.scalar() or 0

    # Active conversations that had activity on this day
    active_filters = [
        Conversation.org_id == org_id,
        Conversation.last_activity_at >= day_start,
        Conversation.last_activity_at <= day_end,
    ]
    if channel:
        active_filters.append(Conversation.channel == channel)

    active_conv_result = await db.execute(
        select(func.count()).select_from(Conversation).where(and_(*active_filters))
    )
    active_conversations = active_conv_result.scalar() or 0

    # Get conversation IDs for message queries
    conv_ids_query = (
        select(Conversation.id)
        .where(
            Conversation.org_id == org_id,
            Conversation.last_activity_at >= day_start,
            Conversation.last_activity_at <= day_end,
        )
    )
    if channel:
        conv_ids_query = conv_ids_query.where(Conversation.channel == channel)
    conv_ids_result = await db.execute(conv_ids_query)
    conv_ids = [row[0] for row in conv_ids_result.all()]

    # Message metrics
    total_messages = 0
    avg_messages_per_conversation = None
    avg_ai_response_time_ms = None
    ai_tokens_used = 0
    fallback_count = 0

    if conv_ids:
        msg_filters = [
            Message.conversation_id.in_(conv_ids),
            Message.created_at >= day_start,
            Message.created_at <= day_end,
        ]

        msg_result = await db.execute(
            select(
                func.count().label("total"),
                func.avg(Message.ai_response_time_ms).label("avg_response_time"),
                func.coalesce(func.sum(Message.ai_tokens_used), 0).label("tokens"),
            ).where(and_(*msg_filters))
        )
        msg_row = msg_result.one()
        total_messages = int(msg_row.total)
        avg_ai_response_time_ms = int(msg_row.avg_response_time) if msg_row.avg_response_time else None
        ai_tokens_used = int(msg_row.tokens)

        if active_conversations > 0 and total_messages > 0:
            avg_messages_per_conversation = round(total_messages / active_conversations, 2)

        # Count fallbacks (AI messages with "fallback" in content — simplified heuristic)
        # In production this would check a dedicated fallback flag
        fallback_result = await db.execute(
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id.in_(conv_ids),
                Message.sender == MessageSender.AI,
                Message.created_at >= day_start,
                Message.created_at <= day_end,
                Message.ai_model.is_(None),  # No model = fallback response
            )
        )
        fallback_count = fallback_result.scalar() or 0

    # Conversion metrics
    conversion_filters = [
        ConversionEvent.org_id == org_id,
        ConversionEvent.created_at >= day_start,
        ConversionEvent.created_at <= day_end,
    ]

    conv_event_result = await db.execute(
        select(
            func.count().label("conversions"),
            func.coalesce(func.sum(ConversionEvent.value), 0).label("conversion_value"),
        ).where(and_(*conversion_filters))
    )
    conv_event_row = conv_event_result.one()
    conversions = int(conv_event_row.conversions)
    conversion_value = float(conv_event_row.conversion_value)

    conversion_rate = None
    if new_conversations > 0:
        conversion_rate = round(conversions / new_conversations, 4)

    # AI cost estimate (simplified: $0.002 per 1K tokens for GPT-4o-mini)
    ai_cost = round(ai_tokens_used * 0.000002, 4)

    return {
        "new_conversations": new_conversations,
        "active_conversations": active_conversations,
        "total_messages": total_messages,
        "avg_messages_per_conversation": avg_messages_per_conversation,
        "avg_ai_response_time_ms": avg_ai_response_time_ms,
        "conversions": conversions,
        "conversion_value": conversion_value,
        "conversion_rate": conversion_rate,
        "ai_tokens_used": ai_tokens_used,
        "ai_cost": ai_cost,
        "fallback_count": fallback_count,
    }
