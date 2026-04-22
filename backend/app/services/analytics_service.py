"""
Attora — Analytics Service

Computes CPQC, CCR, funnel data, trends, ROI, AI performance,
and campaign health from DailyAnalytics + raw tables.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import DailyAnalytics
from app.models.conversation import Conversation
from app.models.conversion import ConversionEvent
from app.models.message import Message
from app.models.subscriber import Subscriber
from app.models.base import BuyerStage, ChannelType, ConversationStatus
from app.schemas.analytics import (
    AIPerformanceResponse,
    AnalyticsResponse,
    DailyTrend,
    FunnelStep,
    ROIResponse,
)
from app.schemas.dashboard import CampaignHealth


async def get_analytics(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    channel: str | None = None,
) -> AnalyticsResponse:
    """Compute aggregated analytics metrics for a date range."""

    # Base filter for daily_analytics
    filters = [
        DailyAnalytics.org_id == org_id,
        DailyAnalytics.date >= date_from,
        DailyAnalytics.date <= date_to,
    ]
    if channel and channel != "all":
        try:
            channel_type = ChannelType(channel)
            filters.append(DailyAnalytics.channel == channel_type)
        except ValueError:
            pass

    # Aggregate from daily_analytics
    agg_result = await db.execute(
        select(
            func.coalesce(func.sum(DailyAnalytics.new_conversations), 0).label("total_conversations"),
            func.coalesce(func.sum(DailyAnalytics.conversions), 0).label("total_conversions"),
            func.coalesce(func.sum(DailyAnalytics.conversion_value), 0).label("total_revenue"),
            func.coalesce(func.sum(DailyAnalytics.ad_spend), 0).label("total_ad_spend"),
            func.avg(DailyAnalytics.avg_ai_response_time_ms).label("avg_response_time_ms"),
        ).where(and_(*filters))
    )
    row = agg_result.one()
    total_conversations = await _count_conversations_raw(db, org_id, date_from, date_to, channel)
    total_conversions = int(row.total_conversions)
    total_revenue = float(row.total_revenue)
    total_ad_spend = float(row.total_ad_spend)
    avg_response_time_ms = int(row.avg_response_time_ms) if row.avg_response_time_ms else None

    # Count qualified subscribers (consideration stage or above) for CPQC
    dt_from = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
    dt_to = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)

    qualified_stages = [
        BuyerStage.CONSIDERATION,
        BuyerStage.INTENT,
        BuyerStage.PURCHASE,
        BuyerStage.POST_PURCHASE,
    ]

    qualified_query = (
        select(func.count())
        .select_from(Subscriber)
        .where(
            Subscriber.org_id == org_id,
            Subscriber.buyer_stage.in_(qualified_stages),
            Subscriber.created_at >= dt_from,
            Subscriber.created_at <= dt_to,
        )
    )
    qualified_result = await db.execute(qualified_query)
    qualified_count = qualified_result.scalar() or 0

    # Compute CPQC: ad_spend / qualified_conversations
    cpqc = None
    if qualified_count > 0 and total_ad_spend > 0:
        cpqc = round(total_ad_spend / qualified_count, 2)

    # Compute CCR: conversions / total_conversations
    ccr = None
    if total_conversations > 0:
        ccr = round(total_conversions / total_conversations, 4)

    # Qualification rate
    qualification_rate = None
    if total_conversations > 0:
        qualification_rate = round(qualified_count / total_conversations, 4)

    # Build funnel (simplified from daily_analytics)
    funnel = _build_funnel(total_conversations, qualified_count, total_conversions)

    # Daily trends
    cpqc_trend = await _compute_daily_cpqc_trend(db, org_id, date_from, date_to, filters)
    ccr_trend = await _compute_daily_ccr_trend(db, org_id, date_from, date_to, filters)

    return AnalyticsResponse(
        date_from=date_from,
        date_to=date_to,
        channel=channel,
        cpqc=cpqc,
        ccr=ccr,
        avg_response_time_ms=avg_response_time_ms,
        qualification_rate=qualification_rate,
        total_conversations=total_conversations,
        total_conversions=total_conversions,
        total_revenue=total_revenue,
        funnel=funnel,
        cpqc_trend=cpqc_trend,
        ccr_trend=ccr_trend,
    )


def _build_funnel(
    total_conversations: int,
    qualified_count: int,
    total_conversions: int,
) -> list[FunnelStep]:
    """Build a simplified conversion funnel."""
    steps = []

    steps.append(FunnelStep(name="conversations", volume=total_conversations, drop_off_rate=None))

    drop_off_qualified = None
    if total_conversations > 0:
        drop_off_qualified = round(1 - (qualified_count / total_conversations), 4)
    steps.append(FunnelStep(name="qualified", volume=qualified_count, drop_off_rate=drop_off_qualified))

    drop_off_converted = None
    if qualified_count > 0:
        drop_off_converted = round(1 - (total_conversions / qualified_count), 4)
    steps.append(FunnelStep(name="converted", volume=total_conversions, drop_off_rate=drop_off_converted))

    return steps


async def _compute_daily_cpqc_trend(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    filters: list,
) -> list[DailyTrend]:
    """Compute daily CPQC trend from daily_analytics."""
    result = await db.execute(
        select(
            DailyAnalytics.date,
            func.coalesce(func.sum(DailyAnalytics.ad_spend), 0).label("ad_spend"),
            func.coalesce(func.sum(DailyAnalytics.new_conversations), 0).label("conversations"),
        )
        .where(and_(*filters))
        .group_by(DailyAnalytics.date)
        .order_by(DailyAnalytics.date)
    )
    rows = result.all()
    trends = []
    for row in rows:
        # Simplified: use cost_per_conversation as proxy when qualified data unavailable per day
        value = 0.0
        if row.conversations and row.conversations > 0 and row.ad_spend:
            value = round(float(row.ad_spend) / int(row.conversations), 2)
        trends.append(DailyTrend(date=row.date, value=value))
    return trends


async def _compute_daily_ccr_trend(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    filters: list,
) -> list[DailyTrend]:
    """Compute daily CCR trend from daily_analytics."""
    result = await db.execute(
        select(
            DailyAnalytics.date,
            func.coalesce(func.sum(DailyAnalytics.conversions), 0).label("conversions"),
            func.coalesce(func.sum(DailyAnalytics.new_conversations), 0).label("conversations"),
        )
        .where(and_(*filters))
        .group_by(DailyAnalytics.date)
        .order_by(DailyAnalytics.date)
    )
    rows = result.all()
    trends = []
    for row in rows:
        value = 0.0
        if row.conversations and row.conversations > 0:
            value = round(int(row.conversions) / int(row.conversations), 4)
        trends.append(DailyTrend(date=row.date, value=value))
    return trends


async def get_roi(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> ROIResponse:
    """Compute ROI / money metrics."""

    filters = [
        DailyAnalytics.org_id == org_id,
        DailyAnalytics.date >= date_from,
        DailyAnalytics.date <= date_to,
    ]

    agg_result = await db.execute(
        select(
            func.coalesce(func.sum(DailyAnalytics.ad_spend), 0).label("ad_spend"),
            func.coalesce(func.sum(DailyAnalytics.conversions), 0).label("converted_count"),
            func.coalesce(func.sum(DailyAnalytics.conversion_value), 0).label("revenue"),
        ).where(and_(*filters))
    )
    row = agg_result.one()

    ad_spend = float(row.ad_spend)
    conversations_count = await _count_conversations_raw(db, org_id, date_from, date_to)
    converted_count = int(row.converted_count)
    revenue = float(row.revenue)

    cost_per_conversation = round(ad_spend / conversations_count, 2) if conversations_count > 0 and ad_spend > 0 else None

    # Count qualified subscribers in the date range
    dt_from = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
    dt_to = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)
    qualified_stages = [
        BuyerStage.CONSIDERATION,
        BuyerStage.INTENT,
        BuyerStage.PURCHASE,
        BuyerStage.POST_PURCHASE,
    ]
    qualified_result = await db.execute(
        select(func.count())
        .select_from(Subscriber)
        .where(
            Subscriber.org_id == org_id,
            Subscriber.buyer_stage.in_(qualified_stages),
            Subscriber.created_at >= dt_from,
            Subscriber.created_at <= dt_to,
        )
    )
    qualified_count = qualified_result.scalar() or 0

    cost_per_qualified = round(ad_spend / qualified_count, 2) if qualified_count > 0 and ad_spend > 0 else None
    cpa = round(ad_spend / converted_count, 2) if converted_count > 0 and ad_spend > 0 else None
    roas = round(revenue / ad_spend, 2) if ad_spend > 0 else None

    # Before/after comparison: compare first half vs second half of the date range
    range_days = (date_to - date_from).days
    midpoint = date_from + timedelta(days=range_days // 2)

    baseline_result = await db.execute(
        select(
            func.coalesce(func.sum(DailyAnalytics.ad_spend), 0).label("ad_spend"),
            func.coalesce(func.sum(DailyAnalytics.conversions), 0).label("conversions"),
            func.coalesce(func.sum(DailyAnalytics.conversion_value), 0).label("revenue"),
        ).where(
            DailyAnalytics.org_id == org_id,
            DailyAnalytics.date >= date_from,
            DailyAnalytics.date < midpoint,
        )
    )
    baseline = baseline_result.one()

    current_result = await db.execute(
        select(
            func.coalesce(func.sum(DailyAnalytics.ad_spend), 0).label("ad_spend"),
            func.coalesce(func.sum(DailyAnalytics.conversions), 0).label("conversions"),
            func.coalesce(func.sum(DailyAnalytics.conversion_value), 0).label("revenue"),
        ).where(
            DailyAnalytics.org_id == org_id,
            DailyAnalytics.date >= midpoint,
            DailyAnalytics.date <= date_to,
        )
    )
    current = current_result.one()

    baseline_cpa = round(float(baseline.ad_spend) / int(baseline.conversions), 2) if baseline.conversions and int(baseline.conversions) > 0 and float(baseline.ad_spend) > 0 else None
    current_cpa = round(float(current.ad_spend) / int(current.conversions), 2) if current.conversions and int(current.conversions) > 0 and float(current.ad_spend) > 0 else None
    baseline_roas = round(float(baseline.revenue) / float(baseline.ad_spend), 2) if float(baseline.ad_spend) > 0 else None
    current_roas = round(float(current.revenue) / float(current.ad_spend), 2) if float(current.ad_spend) > 0 else None

    return ROIResponse(
        date_from=date_from,
        date_to=date_to,
        ad_spend=ad_spend,
        conversations_count=conversations_count,
        cost_per_conversation=cost_per_conversation,
        qualified_count=qualified_count,
        cost_per_qualified=cost_per_qualified,
        converted_count=converted_count,
        cpa=cpa,
        revenue=revenue,
        roas=roas,
        baseline_cpa=baseline_cpa,
        current_cpa=current_cpa,
        baseline_roas=baseline_roas,
        current_roas=current_roas,
    )


async def get_ai_performance(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> AIPerformanceResponse:
    """Compute AI performance metrics."""

    filters = [
        DailyAnalytics.org_id == org_id,
        DailyAnalytics.date >= date_from,
        DailyAnalytics.date <= date_to,
    ]

    agg_result = await db.execute(
        select(
            func.coalesce(func.sum(DailyAnalytics.ai_tokens_used), 0).label("total_ai_tokens"),
            func.coalesce(func.sum(DailyAnalytics.ai_cost), 0).label("total_ai_cost"),
            func.coalesce(func.sum(DailyAnalytics.fallback_count), 0).label("total_fallbacks"),
            func.coalesce(func.sum(DailyAnalytics.total_messages), 0).label("total_messages"),
            func.avg(DailyAnalytics.avg_ai_response_time_ms).label("avg_response_time_ms"),
        ).where(and_(*filters))
    )
    row = agg_result.one()

    total_ai_tokens = int(row.total_ai_tokens)
    total_ai_cost = float(row.total_ai_cost)
    total_fallbacks = int(row.total_fallbacks)
    total_messages = int(row.total_messages)
    avg_response_time_ms = int(row.avg_response_time_ms) if row.avg_response_time_ms else None

    fallback_rate = round(total_fallbacks / total_messages, 4) if total_messages > 0 else None

    # 7-day fallback trend
    fallback_trend_result = await db.execute(
        select(
            DailyAnalytics.date,
            func.coalesce(func.sum(DailyAnalytics.fallback_count), 0).label("fallbacks"),
            func.coalesce(func.sum(DailyAnalytics.total_messages), 0).label("messages"),
        )
        .where(and_(*filters))
        .group_by(DailyAnalytics.date)
        .order_by(DailyAnalytics.date)
    )
    fallback_rows = fallback_trend_result.all()
    fallback_trend = []
    for frow in fallback_rows:
        value = 0.0
        if frow.messages and int(frow.messages) > 0:
            value = round(int(frow.fallbacks) / int(frow.messages), 4)
        fallback_trend.append(DailyTrend(date=frow.date, value=value))

    return AIPerformanceResponse(
        fallback_rate=fallback_rate,
        fallback_trend=fallback_trend,
        avg_response_time_ms=avg_response_time_ms,
        total_ai_tokens=total_ai_tokens,
        total_ai_cost=total_ai_cost,
    )


async def _count_conversations_raw(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    channel: str | None = None,
) -> int:
    """Count conversations directly from the conversations table for consistency with /api/conversations."""
    dt_from = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
    dt_to = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)

    activity_ts = func.coalesce(Conversation.last_activity_at, Conversation.created_at)

    query = (
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.org_id == org_id,
            activity_ts >= dt_from,
            activity_ts <= dt_to,
        )
    )

    if channel and channel != "all":
        try:
            query = query.where(Conversation.channel == ChannelType(channel))
        except ValueError:
            pass

    result = await db.execute(query)
    return int(result.scalar() or 0)


async def get_dashboard_overview(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> dict:
    """
    Compute dashboard overview data: key metrics, trends, campaign health.
    """
    today = date.today()
    seven_days_ago = today - timedelta(days=7)

    # CPQC and CCR for the last 7 days
    analytics = await get_analytics(db, org_id, seven_days_ago, today)

    # Active conversations count
    active_result = await db.execute(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.org_id == org_id,
            Conversation.status == ConversationStatus.ACTIVE,
        )
    )
    active_conversations_count = active_result.scalar() or 0

    # Today's conversions and revenue
    today_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    today_end = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=timezone.utc)

    today_result = await db.execute(
        select(
            func.count().label("conversions"),
            func.coalesce(func.sum(ConversionEvent.value), 0).label("revenue"),
        )
        .select_from(ConversionEvent)
        .where(
            ConversionEvent.org_id == org_id,
            ConversionEvent.created_at >= today_start,
            ConversionEvent.created_at <= today_end,
        )
    )
    today_row = today_result.one()
    todays_conversions = int(today_row.conversions)
    todays_revenue = float(today_row.revenue)

    # Campaign health — simple threshold logic on daily CPA
    campaign_health = await _compute_campaign_health(db, org_id, today)

    return {
        "cpqc": analytics.cpqc,
        "cpqc_trend": analytics.cpqc_trend,
        "ccr": analytics.ccr,
        "ccr_trend": analytics.ccr_trend,
        "active_conversations_count": active_conversations_count,
        "todays_conversions": todays_conversions,
        "todays_revenue": todays_revenue,
        "campaign_health": campaign_health,
    }


async def _compute_campaign_health(
    db: AsyncSession,
    org_id: uuid.UUID,
    today: date,
) -> list[CampaignHealth]:
    """
    Simple campaign health based on CPA thresholds over the last 7 days.

    Green: CPA < $50 or no spend
    Yellow: CPA $50-$100
    Red: CPA > $100 or zero conversions with spend
    """
    seven_days_ago = today - timedelta(days=7)

    # Get per-channel stats
    result = await db.execute(
        select(
            DailyAnalytics.channel,
            func.coalesce(func.sum(DailyAnalytics.ad_spend), 0).label("ad_spend"),
            func.coalesce(func.sum(DailyAnalytics.conversions), 0).label("conversions"),
            func.coalesce(func.sum(DailyAnalytics.new_conversations), 0).label("conversations"),
        )
        .where(
            DailyAnalytics.org_id == org_id,
            DailyAnalytics.date >= seven_days_ago,
            DailyAnalytics.date <= today,
        )
        .group_by(DailyAnalytics.channel)
    )
    rows = result.all()

    health_items = []
    for row in rows:
        channel_name = row.channel.value if row.channel else "all"
        ad_spend = float(row.ad_spend)
        conversions = int(row.conversions)
        conversations = int(row.conversations)

        if ad_spend <= 0:
            health_status = "green"
            reason = "No ad spend"
        elif conversions == 0:
            health_status = "red"
            reason = f"No conversions with ${ad_spend:.0f} spend"
        else:
            cpa = ad_spend / conversions
            if cpa < 50:
                health_status = "green"
                reason = f"CPA ${cpa:.2f}"
            elif cpa < 100:
                health_status = "yellow"
                reason = f"CPA ${cpa:.2f} — consider optimization"
            else:
                health_status = "red"
                reason = f"CPA ${cpa:.2f} — needs attention"

        health_items.append(
            CampaignHealth(
                name=channel_name,
                status=health_status,
                reason=reason,
            )
        )

    return health_items


async def get_analytics_export_data(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    channel: str | None = None,
) -> list[dict]:
    """Get daily analytics data for CSV export."""

    filters = [
        DailyAnalytics.org_id == org_id,
        DailyAnalytics.date >= date_from,
        DailyAnalytics.date <= date_to,
    ]
    if channel and channel != "all":
        try:
            channel_type = ChannelType(channel)
            filters.append(DailyAnalytics.channel == channel_type)
        except ValueError:
            pass

    result = await db.execute(
        select(DailyAnalytics)
        .where(and_(*filters))
        .order_by(DailyAnalytics.date)
    )
    rows = result.scalars().all()

    export_data = []
    for row in rows:
        export_data.append({
            "date": row.date.isoformat(),
            "channel": row.channel.value if row.channel else "all",
            "new_conversations": row.new_conversations,
            "active_conversations": row.active_conversations,
            "total_messages": row.total_messages,
            "avg_messages_per_conversation": float(row.avg_messages_per_conversation) if row.avg_messages_per_conversation else None,
            "avg_ai_response_time_ms": row.avg_ai_response_time_ms,
            "conversions": row.conversions,
            "conversion_value": float(row.conversion_value),
            "conversion_rate": float(row.conversion_rate) if row.conversion_rate else None,
            "ad_spend": float(row.ad_spend) if row.ad_spend else None,
            "cpa": float(row.cpa) if row.cpa else None,
            "roas": float(row.roas) if row.roas else None,
            "ai_tokens_used": row.ai_tokens_used,
            "ai_cost": float(row.ai_cost),
            "fallback_count": row.fallback_count,
        })

    return export_data
