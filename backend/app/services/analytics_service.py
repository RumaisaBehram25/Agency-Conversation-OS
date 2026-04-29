"""
Attora — Analytics Service

Computes CPQC, CCR, funnel data, trends, ROI, AI performance,
and campaign health from DailyAnalytics + raw tables.
"""

import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import DailyAnalytics
from app.models.campaign_metrics import CampaignMetric
from app.models.conversation import Conversation
from app.models.conversion import ConversionEvent
from app.models.message import Message
from app.models.organization import Organization
from app.models.subscriber import Subscriber
from app.models.manychat_event import ManyChatEvent
from app.models.base import BuyerStage, ChannelType, ConversationStatus
from app.security.encryption import decrypt_value
from app.schemas.analytics import (
    AIPerformanceResponse,
    AnalyticsResponse,
    DailyTrend,
    FunnelStep,
    ManyChatFlowStat,
    ManyChatFlowStatsResponse,
    ManyChatMetricCard,
    ManyChatMetricSubscriber,
    OrganicPostBreakdown,
    ROIResponse,
)
from app.schemas.dashboard import CampaignHealth

_MANYCHAT_API_BASE = "https://api.manychat.com"
_MANYCHAT_TARGET_PAGE_ID = "967183323615679"
logger = logging.getLogger(__name__)


def _coerce_int(value) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        if s.isdigit():
            return int(s)
    return 0


def _extract_metric_count(flow_obj: dict, metric: str) -> int:
    """Try several common key patterns used in stats payloads."""
    candidates = [
        metric,
        f"{metric}_count",
        f"{metric}Count",
        f"{metric}_total",
        f"total_{metric}",
        f"{metric}ed" if metric == "open" else "",
    ]
    stats = flow_obj.get("stats")
    if isinstance(stats, dict):
        for key in candidates:
            if not key:
                continue
            v = stats.get(key)
            if isinstance(v, dict):
                count_val = v.get("count") if "count" in v else v.get("total")
                c = _coerce_int(count_val)
                if c:
                    return c
            c = _coerce_int(v)
            if c:
                return c
    for key in candidates:
        if not key:
            continue
        v = flow_obj.get(key)
        if isinstance(v, dict):
            count_val = v.get("count") if "count" in v else v.get("total")
            c = _coerce_int(count_val)
            if c:
                return c
        c = _coerce_int(v)
        if c:
            return c
    return 0


def _extract_metric_subscriber_ids(flow_obj: dict, metric: str) -> list[str]:
    """Extract subscriber IDs for a metric when ManyChat provides drill-down arrays."""
    out: list[str] = []
    candidate_keys = [
        f"{metric}_subscriber_ids",
        f"{metric}SubscriberIds",
        f"{metric}_subscribers",
        f"{metric}Subscribers",
        f"{metric}_users",
        f"{metric}Users",
    ]
    pools: list = [flow_obj]
    if isinstance(flow_obj.get("stats"), dict):
        pools.append(flow_obj["stats"])
    for pool in pools:
        if not isinstance(pool, dict):
            continue
        for key in candidate_keys:
            raw = pool.get(key)
            if not isinstance(raw, list):
                continue
            for item in raw:
                if isinstance(item, (str, int)):
                    out.append(str(item))
                elif isinstance(item, dict):
                    sid = item.get("subscriber_id") or item.get("id") or item.get("user_id")
                    if sid is not None:
                        out.append(str(sid))
    # Preserve order, unique
    seen: set[str] = set()
    deduped: list[str] = []
    for sid in out:
        if sid in seen:
            continue
        seen.add(sid)
        deduped.append(sid)
    return deduped


def _parse_json_or_text(resp: httpx.Response) -> dict:
    if not resp.content:
        return {}
    try:
        parsed = resp.json()
        if isinstance(parsed, dict):
            return parsed
        return {"raw_json": parsed}
    except ValueError:
        return {"raw_text": resp.text[:2000] if resp.text else ""}


async def get_analytics(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    channel: str | None = None,
    campaign_id: str | None = None,
    organic: bool = False,
) -> AnalyticsResponse:
    """Compute aggregated analytics metrics for a date range."""

    if organic:
        return await _get_analytics_for_organic(db, org_id, date_from, date_to, channel)

    # Base filter for daily_analytics.
    #
    # daily_digest writes one row per (date, channel) PLUS a separate combined
    # row with channel=NULL that already aggregates across channels. Summing
    # across both groups double-counts every metric. Without an explicit
    # channel filter, restrict to the combined (channel=NULL) row so totals
    # reflect reality.
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
            filters.append(DailyAnalytics.channel.is_(None))
    else:
        filters.append(DailyAnalytics.channel.is_(None))

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
    avg_response_time_ms = int(row.avg_response_time_ms) if row.avg_response_time_ms else None

    # CPQC numerator: org-wide ad_spend by default; campaign-scoped when
    # campaign_id is provided. Organic flows have no spend, so the per-campaign
    # numerator is exactly that campaign's spend (organic contributes $0).
    if campaign_id:
        spend_result = await db.execute(
            select(func.coalesce(func.sum(CampaignMetric.spend), 0))
            .where(
                CampaignMetric.org_id == org_id,
                CampaignMetric.level == "campaign",
                CampaignMetric.meta_campaign_id == campaign_id,
                CampaignMetric.date >= date_from,
                CampaignMetric.date <= date_to,
            )
        )
        total_ad_spend = float(spend_result.scalar() or 0)
    else:
        total_ad_spend = float(row.total_ad_spend)

    # Count qualified subscribers — INTENT stage or above — for CPQC.
    #
    # CONSIDERATION is intentionally excluded: the buyer-stage classifier
    # auto-promotes any conversation with >= 4 messages from awareness to
    # consideration without an explicit intent signal, which made the
    # qualification rate trivially 100%. Restricting to INTENT or higher
    # means a subscriber must have shown an actual buying signal (keyword,
    # intent classification, or AI assessment) to count.
    dt_from = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
    dt_to = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)

    qualified_stages = [
        BuyerStage.INTENT,
        BuyerStage.PURCHASE,
        BuyerStage.POST_PURCHASE,
    ]

    qualified_filters = [
        Subscriber.org_id == org_id,
        Subscriber.buyer_stage.in_(qualified_stages),
        Subscriber.created_at >= dt_from,
        Subscriber.created_at <= dt_to,
    ]
    # When scoped to a campaign, include that campaign's qualified subscribers
    # plus organic (campaign_id IS NULL). Organic enters with $0 spend, which
    # is the intended client-facing semantic: every campaign gets credit for
    # organic-driven qualifications.
    if campaign_id:
        qualified_filters.append(
            or_(Subscriber.campaign_id == campaign_id, Subscriber.campaign_id.is_(None))
        )

    qualified_result = await db.execute(
        select(func.count()).select_from(Subscriber).where(*qualified_filters)
    )
    qualified_count = qualified_result.scalar() or 0

    hyros_purchases_result = await db.execute(
        select(func.count())
        .select_from(Subscriber)
        .where(
            Subscriber.org_id == org_id,
            Subscriber.hyros_purchased.is_(True),
            Subscriber.created_at >= dt_from,
            Subscriber.created_at <= dt_to,
        )
    )
    hyros_confirmed_purchases = hyros_purchases_result.scalar() or 0

    # Compute CPQC: ad_spend / qualified_conversations.
    # When a campaign is explicitly selected, $0 spend with qualified > 0 is a
    # meaningful answer (organic-only window for that campaign), so render it
    # as $0.00 rather than "—". Org-wide view keeps the "—" for $0 spend so
    # we don't mislead with a falsely-cheap headline number.
    cpqc = None
    if qualified_count > 0:
        if total_ad_spend > 0:
            cpqc = round(total_ad_spend / qualified_count, 2)
        elif campaign_id:
            cpqc = 0.0

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
    cpqc_trend = await _compute_daily_cpqc_trend(
        db, org_id, date_from, date_to, filters, campaign_id
    )
    ccr_trend = await _compute_daily_ccr_trend(
        db, org_id, date_from, date_to, filters, campaign_id
    )

    return AnalyticsResponse(
        date_from=date_from,
        date_to=date_to,
        channel=channel,
        cpqc=cpqc,
        ccr=ccr,
        avg_response_time_ms=avg_response_time_ms,
        qualification_rate=qualification_rate,
        hyros_confirmed_purchases=hyros_confirmed_purchases,
        total_conversations=total_conversations,
        total_conversions=total_conversions,
        total_revenue=total_revenue,
        funnel=funnel,
        cpqc_trend=cpqc_trend,
        ccr_trend=ccr_trend,
    )


async def _get_analytics_for_organic(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    organic_channel: str | None = None,
) -> AnalyticsResponse:
    """Compute analytics metrics scoped to organic traffic — ALL-TIME.

    Organic = subscribers whose post_id is populated AND ad_id is NULL.
    Date-range filters are intentionally omitted: organic metrics always
    reflect the full historical dataset so they are unaffected by the date
    picker selected on the Analytics page.

    ``organic_channel`` optionally restricts to a single channel
    (``instagram``, ``messenger``).  Defaults to all channels.

    NOTE: "total conversations" is deliberately counted from the Subscriber
    table, not from the Conversation table.  Subscribers imported via DB
    migration may not have a corresponding Conversation row yet, but they
    are still valid organic leads and must appear in the counts.
    """
    # Organic = post_id is populated AND ad_id is unset. ManyChat sometimes
    # writes empty strings instead of NULLs for missing custom fields, so
    # treat "" as null on both sides.
    organic_subscriber_filter = and_(
        Subscriber.post_id.is_not(None),
        func.coalesce(Subscriber.post_id, "") != "",
        Subscriber.post_id.not_like("legacy_%"),
        Subscriber.post_id.not_like("seed_%"),
        or_(Subscriber.ad_id.is_(None), Subscriber.ad_id == ""),
    )

    # Optional per-channel restriction.
    channel_filter = []
    resolved_channel: ChannelType | None = None
    if organic_channel and organic_channel not in ("all", ""):
        try:
            resolved_channel = ChannelType(organic_channel.lower())
            channel_filter = [Subscriber.channel == resolved_channel]
        except ValueError:
            pass  # Unknown channel value — treat as "all"

    # --- Total organic subscribers (used as "conversations" proxy) ----------
    # We count Subscribers directly so that migrated rows without a
    # Conversation record are included.
    total_conversations_result = await db.execute(
        select(func.count())
        .select_from(Subscriber)
        .where(
            Subscriber.org_id == org_id,
            organic_subscriber_filter,
            *channel_filter,
        )
    )
    total_conversations = int(total_conversations_result.scalar() or 0)

    # Conversions for organic — no date filter, all-time.
    conversion_result = await db.execute(
        select(
            func.count().label("converted"),
            func.coalesce(func.sum(ConversionEvent.value), 0).label("revenue"),
        )
        .select_from(ConversionEvent)
        .join(Subscriber, Subscriber.id == ConversionEvent.subscriber_id)
        .where(
            ConversionEvent.org_id == org_id,
            organic_subscriber_filter,
            *channel_filter,
        )
    )
    conversion_row = conversion_result.one()
    total_conversions = int(conversion_row.converted)
    total_revenue = float(conversion_row.revenue)

    qualified_stages = [
        BuyerStage.INTENT,
        BuyerStage.PURCHASE,
        BuyerStage.POST_PURCHASE,
    ]

    # Qualified leads — no date filter, all-time.
    qualified_result = await db.execute(
        select(func.count())
        .select_from(Subscriber)
        .where(
            Subscriber.org_id == org_id,
            Subscriber.buyer_stage.in_(qualified_stages),
            organic_subscriber_filter,
            *channel_filter,
        )
    )
    qualified_count = int(qualified_result.scalar() or 0)

    # Hyros-confirmed purchases — no date filter, all-time.
    hyros_result = await db.execute(
        select(func.count())
        .select_from(Subscriber)
        .where(
            Subscriber.org_id == org_id,
            Subscriber.hyros_purchased.is_(True),
            organic_subscriber_filter,
            *channel_filter,
        )
    )
    hyros_confirmed_purchases = int(hyros_result.scalar() or 0)

    # Avg AI response time — pulled through Conversation to reach Messages.
    # Falls back to None gracefully when no messages exist yet.
    avg_response_result = await db.execute(
        select(func.avg(Message.ai_response_time_ms))
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .join(Subscriber, Subscriber.id == Conversation.subscriber_id)
        .where(
            Conversation.org_id == org_id,
            Message.ai_response_time_ms.is_not(None),
            organic_subscriber_filter,
            *channel_filter,
        )
    )
    avg_response_time_ms = avg_response_result.scalar()
    avg_response_time_ms = int(avg_response_time_ms) if avg_response_time_ms else None

    cpqc = 0.0 if qualified_count > 0 else None

    ccr = None
    if total_conversations > 0:
        ccr = round(total_conversions / total_conversations, 4)

    qualification_rate = None
    if total_conversations > 0:
        qualification_rate = round(qualified_count / total_conversations, 4)

    funnel = _build_funnel(total_conversations, qualified_count, total_conversions)

    organic_posts = await _build_organic_posts_breakdown(
        db, org_id, organic_subscriber_filter, qualified_stages, channel_filter
    )

    return AnalyticsResponse(
        date_from=date_from,
        date_to=date_to,
        channel=resolved_channel.value if resolved_channel else None,
        cpqc=cpqc,
        ccr=ccr,
        avg_response_time_ms=avg_response_time_ms,
        qualification_rate=qualification_rate,
        hyros_confirmed_purchases=hyros_confirmed_purchases,
        total_conversations=total_conversations,
        total_conversions=total_conversions,
        total_revenue=total_revenue,
        funnel=funnel,
        cpqc_trend=[],
        ccr_trend=[],
        organic_posts=organic_posts,
    )


async def _build_organic_posts_breakdown(
    db: AsyncSession,
    org_id: uuid.UUID,
    organic_subscriber_filter,
    qualified_stages: list[BuyerStage],
    channel_filter: list | None = None,
) -> list[OrganicPostBreakdown]:
    """Group organic conversation/qualified/converted volumes by post_id and channel.

    All-time counts — no date window applied.
    Conversations = distinct organic Subscriber rows per post_id (not
    Conversation rows), so migrated subscribers without a Conversation
    record are still counted.
    """
    cf = channel_filter or []

    # Subscribers per (channel, post) — all-time (our proxy for "conversations").
    conv_rows = await db.execute(
        select(
            Subscriber.channel.label("channel"),
            Subscriber.post_id.label("post_id"),
            func.count().label("conversations"),
        )
        .select_from(Subscriber)
        .where(
            Subscriber.org_id == org_id,
            organic_subscriber_filter,
            *cf,
        )
        .group_by(Subscriber.channel, Subscriber.post_id)
    )
    conversations_by_post = {
        (r.channel.value if r.channel else None, r.post_id): int(r.conversations)
        for r in conv_rows.all()
    }

    # Qualified leads per (channel, post) — all-time.
    qual_rows = await db.execute(
        select(
            Subscriber.channel.label("channel"),
            Subscriber.post_id.label("post_id"),
            func.count().label("qualified"),
        )
        .where(
            Subscriber.org_id == org_id,
            Subscriber.buyer_stage.in_(qualified_stages),
            organic_subscriber_filter,
            *cf,
        )
        .group_by(Subscriber.channel, Subscriber.post_id)
    )
    qualified_by_post = {
        (r.channel.value if r.channel else None, r.post_id): int(r.qualified)
        for r in qual_rows.all()
    }

    # Conversions per (channel, post) — all-time.
    conv_event_rows = await db.execute(
        select(
            Subscriber.channel.label("channel"),
            Subscriber.post_id.label("post_id"),
            func.count().label("converted"),
        )
        .select_from(ConversionEvent)
        .join(Subscriber, Subscriber.id == ConversionEvent.subscriber_id)
        .where(
            ConversionEvent.org_id == org_id,
            organic_subscriber_filter,
            *cf,
        )
        .group_by(Subscriber.channel, Subscriber.post_id)
    )
    converted_by_post = {
        (r.channel.value if r.channel else None, r.post_id): int(r.converted)
        for r in conv_event_rows.all()
    }

    all_post_keys = set(conversations_by_post) | set(qualified_by_post) | set(converted_by_post)

    rows: list[OrganicPostBreakdown] = []
    for channel, pid in all_post_keys:
        conversations = conversations_by_post.get((channel, pid), 0)
        qualified = qualified_by_post.get((channel, pid), 0)
        converted = converted_by_post.get((channel, pid), 0)
        qualification_rate = round(qualified / conversations, 4) if conversations > 0 else None
        conversion_rate = round(converted / conversations, 4) if conversations > 0 else None
        rows.append(
            OrganicPostBreakdown(
                post_id=pid,
                channel=channel,
                conversations=conversations,
                qualified=qualified,
                converted=converted,
                qualification_rate=qualification_rate,
                conversion_rate=conversion_rate,
            )
        )

    rows.sort(key=lambda r: (r.conversations, r.converted), reverse=True)
    return rows


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
    campaign_id: str | None = None,
) -> list[DailyTrend]:
    """Compute daily CPQC trend.

    Always uses qualified subscribers as the denominator (same as the
    headline CPQC card), so the chart agrees with the metric label.

    Org-wide: daily ad_spend from daily_analytics (channel=NULL row) ÷
    daily qualified subscribers (INTENT+).

    Campaign-scoped: daily spend from CampaignMetric for the selected
    campaign ÷ daily qualified subscribers (selected campaign OR organic).

    Days where qualified == 0 OR spend == 0 emit value=None so the
    frontend renders a gap instead of a misleading $0.
    """
    qualified_stages = [
        BuyerStage.INTENT,
        BuyerStage.PURCHASE,
        BuyerStage.POST_PURCHASE,
    ]
    dt_from = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
    dt_to = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)

    if campaign_id:
        spend_rows = await db.execute(
            select(
                CampaignMetric.date,
                func.coalesce(func.sum(CampaignMetric.spend), 0).label("ad_spend"),
            )
            .where(
                CampaignMetric.org_id == org_id,
                CampaignMetric.level == "campaign",
                CampaignMetric.meta_campaign_id == campaign_id,
                CampaignMetric.date >= date_from,
                CampaignMetric.date <= date_to,
            )
            .group_by(CampaignMetric.date)
        )
        spend_by_date = {r.date: float(r.ad_spend) for r in spend_rows.all()}

        qualified_rows = await db.execute(
            select(
                func.date(Subscriber.created_at).label("d"),
                func.count().label("qualified"),
            )
            .where(
                Subscriber.org_id == org_id,
                Subscriber.buyer_stage.in_(qualified_stages),
                Subscriber.created_at >= dt_from,
                Subscriber.created_at <= dt_to,
                or_(Subscriber.campaign_id == campaign_id, Subscriber.campaign_id.is_(None)),
            )
            .group_by(func.date(Subscriber.created_at))
        )
    else:
        spend_rows = await db.execute(
            select(
                DailyAnalytics.date,
                func.coalesce(func.sum(DailyAnalytics.ad_spend), 0).label("ad_spend"),
            )
            .where(and_(*filters))
            .group_by(DailyAnalytics.date)
        )
        spend_by_date = {r.date: float(r.ad_spend) for r in spend_rows.all()}

        qualified_rows = await db.execute(
            select(
                func.date(Subscriber.created_at).label("d"),
                func.count().label("qualified"),
            )
            .where(
                Subscriber.org_id == org_id,
                Subscriber.buyer_stage.in_(qualified_stages),
                Subscriber.created_at >= dt_from,
                Subscriber.created_at <= dt_to,
            )
            .group_by(func.date(Subscriber.created_at))
        )

    qualified_by_date = {r.d: int(r.qualified) for r in qualified_rows.all()}

    trends: list[DailyTrend] = []
    for d in sorted(set(spend_by_date) | set(qualified_by_date)):
        spend = spend_by_date.get(d, 0.0)
        q = qualified_by_date.get(d, 0)
        if q > 0 and spend > 0:
            trends.append(DailyTrend(date=d, value=round(spend / q, 2)))
        else:
            trends.append(DailyTrend(date=d, value=None))
    return trends


async def _compute_daily_ccr_trend(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    filters: list,
    campaign_id: str | None = None,
) -> list[DailyTrend]:
    """Compute daily CCR trend.

    Org-wide: from daily_analytics (channel=NULL combined row).
    Campaign-scoped: counts conversions from ConversionEvent and
    conversations from Conversation routed via Subscriber.campaign_id —
    matches the per-campaign semantic used elsewhere (campaign + organic).

    Days with no conversations emit value=None so the chart shows gaps
    instead of misleading flat zeros.
    """
    if not campaign_id:
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
        trends: list[DailyTrend] = []
        for row in rows:
            convs = int(row.conversations) if row.conversations else 0
            cnv = int(row.conversions) if row.conversions else 0
            if convs > 0:
                trends.append(DailyTrend(date=row.date, value=round(cnv / convs, 4)))
            else:
                trends.append(DailyTrend(date=row.date, value=None))
        return trends

    dt_from = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
    dt_to = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)
    activity_ts = func.coalesce(Conversation.last_activity_at, Conversation.created_at)

    conv_rows = await db.execute(
        select(
            func.date(activity_ts).label("d"),
            func.count().label("conversations"),
        )
        .select_from(Conversation)
        .join(Subscriber, Subscriber.id == Conversation.subscriber_id)
        .where(
            Conversation.org_id == org_id,
            activity_ts >= dt_from,
            activity_ts <= dt_to,
            or_(Subscriber.campaign_id == campaign_id, Subscriber.campaign_id.is_(None)),
        )
        .group_by(func.date(activity_ts))
    )
    conversations_by_date = {r.d: int(r.conversations) for r in conv_rows.all()}

    conversion_rows = await db.execute(
        select(
            func.date(ConversionEvent.created_at).label("d"),
            func.count().label("converted"),
        )
        .where(
            ConversionEvent.org_id == org_id,
            ConversionEvent.created_at >= dt_from,
            ConversionEvent.created_at <= dt_to,
            or_(
                ConversionEvent.meta_campaign_id == campaign_id,
                ConversionEvent.meta_campaign_id.is_(None),
            ),
        )
        .group_by(func.date(ConversionEvent.created_at))
    )
    converted_by_date = {r.d: int(r.converted) for r in conversion_rows.all()}

    trends = []
    for d in sorted(set(conversations_by_date) | set(converted_by_date)):
        convs = conversations_by_date.get(d, 0)
        cnv = converted_by_date.get(d, 0)
        if convs > 0:
            trends.append(DailyTrend(date=d, value=round(cnv / convs, 4)))
        else:
            trends.append(DailyTrend(date=d, value=None))
    return trends


async def get_roi(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    campaign_id: str | None = None,
) -> ROIResponse:
    """Compute ROI / money metrics.

    When campaign_id is supplied, spend is taken from CampaignMetric for that
    campaign (matching the dropdown label and the CPQC card), and conversions
    /revenue/qualified are counted for that campaign plus organic
    (campaign_id IS NULL) — the same "incl. organic at $0" semantic CPQC uses.
    Without campaign_id, ROI is org-wide and reads from daily_analytics.
    """

    dt_from = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
    dt_to = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)

    if campaign_id:
        # ── Spend from campaign_metrics (same source as the dropdown) ────
        spend_result = await db.execute(
            select(func.coalesce(func.sum(CampaignMetric.spend), 0))
            .where(
                CampaignMetric.org_id == org_id,
                CampaignMetric.level == "campaign",
                CampaignMetric.meta_campaign_id == campaign_id,
                CampaignMetric.date >= date_from,
                CampaignMetric.date <= date_to,
            )
        )
        ad_spend = float(spend_result.scalar() or 0)

        # ── Conversions + revenue from ConversionEvent (campaign + organic) ──
        conv_result = await db.execute(
            select(
                func.count().label("converted_count"),
                func.coalesce(func.sum(ConversionEvent.value), 0).label("revenue"),
            )
            .where(
                ConversionEvent.org_id == org_id,
                ConversionEvent.created_at >= dt_from,
                ConversionEvent.created_at <= dt_to,
                or_(
                    ConversionEvent.meta_campaign_id == campaign_id,
                    ConversionEvent.meta_campaign_id.is_(None),
                ),
            )
        )
        conv_row = conv_result.one()
        converted_count = int(conv_row.converted_count)
        revenue = float(conv_row.revenue)

        # ── Conversations: count via subscribers attributed to the campaign ──
        conversations_count = await _count_conversations_for_campaign(
            db, org_id, dt_from, dt_to, campaign_id
        )
    else:
        # Org-wide: read from daily_analytics on the channel=NULL combined row.
        filters = [
            DailyAnalytics.org_id == org_id,
            DailyAnalytics.date >= date_from,
            DailyAnalytics.date <= date_to,
            DailyAnalytics.channel.is_(None),
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
        converted_count = int(row.converted_count)
        revenue = float(row.revenue)
        conversations_count = await _count_conversations_raw(db, org_id, date_from, date_to)

    cost_per_conversation = round(ad_spend / conversations_count, 2) if conversations_count > 0 and ad_spend > 0 else None

    qualified_stages = [
        BuyerStage.INTENT,
        BuyerStage.PURCHASE,
        BuyerStage.POST_PURCHASE,
    ]
    qualified_filters = [
        Subscriber.org_id == org_id,
        Subscriber.buyer_stage.in_(qualified_stages),
        Subscriber.created_at >= dt_from,
        Subscriber.created_at <= dt_to,
    ]
    if campaign_id:
        qualified_filters.append(
            or_(Subscriber.campaign_id == campaign_id, Subscriber.campaign_id.is_(None))
        )
    qualified_result = await db.execute(
        select(func.count())
        .select_from(Subscriber)
        .where(*qualified_filters)
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
            DailyAnalytics.channel.is_(None),
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
            DailyAnalytics.channel.is_(None),
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

    # Combined channel=NULL row only — see get_analytics for double-counting context.
    filters = [
        DailyAnalytics.org_id == org_id,
        DailyAnalytics.date >= date_from,
        DailyAnalytics.date <= date_to,
        DailyAnalytics.channel.is_(None),
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


async def get_manychat_flow_stats(
    db: AsyncSession,
    org_id: uuid.UUID,
    channel: str = "all",
) -> ManyChatFlowStatsResponse:
    """Fetch engagement metrics for two specific ManyChat workflows."""
    normalized_channel = (channel or "all").lower()
    if normalized_channel not in {"all", "instagram", "messenger"}:
        normalized_channel = "all"

    org_result = await db.execute(
        select(
            Organization.manychat_api_key,
            Organization.manychat_page_id,
        ).where(Organization.id == org_id)
    )
    org_row = org_result.one_or_none()
    if org_row is None:
        return ManyChatFlowStatsResponse(
            channel=normalized_channel,
            available=False,
            message="Organization not found.",
        )

    encrypted_key = org_row.manychat_api_key
    configured_page_id = org_row.manychat_page_id
    if not encrypted_key:
        return ManyChatFlowStatsResponse(
            page_id=configured_page_id,
            channel=normalized_channel,
            available=False,
            message="ManyChat API key is not configured in Settings.",
        )

    try:
        manychat_api_key = decrypt_value(encrypted_key)
    except Exception:
        return ManyChatFlowStatsResponse(
            page_id=configured_page_id,
            channel=normalized_channel,
            available=False,
            message="ManyChat API key could not be decrypted.",
        )

    page_id = configured_page_id or _MANYCHAT_TARGET_PAGE_ID
    headers = {
        "Authorization": f"Bearer {manychat_api_key}",
        "Accept": "application/json",
    }
    url = f"{_MANYCHAT_API_BASE}/fb/page/getFlows"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
        payload = resp.json() if resp.content else {}
    except Exception:
        return ManyChatFlowStatsResponse(
            page_id=page_id,
            channel=normalized_channel,
            available=False,
            message="ManyChat API request failed while fetching flows.",
        )

    logger.info(
        "ManyChat getFlows raw response: status=%s body=%s",
        resp.status_code,
        payload if isinstance(payload, dict) else str(payload)[:2000],
    )

    if resp.status_code >= 400:
        message = payload.get("message") if isinstance(payload, dict) else None
        return ManyChatFlowStatsResponse(
            page_id=page_id,
            channel=normalized_channel,
            available=False,
            message=message or f"ManyChat API returned HTTP {resp.status_code}.",
        )

    raw_flows = []
    if isinstance(payload, dict):
        maybe_data = payload.get("data")
        if isinstance(maybe_data, list):
            raw_flows = maybe_data
        elif isinstance(maybe_data, dict) and isinstance(maybe_data.get("flows"), list):
            raw_flows = maybe_data["flows"]
        elif isinstance(payload.get("flows"), list):
            raw_flows = payload["flows"]

    flow_ids = []
    for item in raw_flows:
        if not isinstance(item, dict):
            continue
        flow_ids.append(
            str(item.get("id") or item.get("flow_ns") or item.get("ns") or "")
        )
    logger.info("ManyChat getFlows discovered flow IDs: %s", [f for f in flow_ids if f])

    flow_rows: list[ManyChatFlowStat] = []
    metric_subscriber_ids: dict[str, list[str]] = {
        "sent": [],
        "clicked": [],
    }
    metric_source_by_key: dict[str, str] = {
        "sent": "attora_events",
        "clicked": "attora_events",
    }

    requested_channels = ["instagram", "messenger"] if normalized_channel == "all" else [normalized_channel]
    preferred_flow_ids_by_channel = {
        "instagram": "content20260318143714_718544",
        "messenger": "content20260427224734_091419",
    }

    async def _probe_manychat_endpoints(flow_id: str, channel_name: str) -> dict[str, dict]:
        """
        Probe potential ManyChat endpoints and return parsed payloads.
        Raw responses are always logged to aid endpoint discovery.
        """
        endpoints = [
            ("GET", f"{_MANYCHAT_API_BASE}/fb/subscriber/getList", {"flow_id": flow_id, "flow_ns": flow_id, "page_id": page_id}),
            ("GET", f"{_MANYCHAT_API_BASE}/fb/sending/getLogs", {"flow_id": flow_id, "flow_ns": flow_id, "page_id": page_id}),
            ("POST", f"{_MANYCHAT_API_BASE}/fb/sending/getLogs", {"flow_id": flow_id, "flow_ns": flow_id, "page_id": page_id}),
            ("GET", f"{_MANYCHAT_API_BASE}/fb/broadcasting/getLogs", {"flow_id": flow_id, "flow_ns": flow_id, "page_id": page_id}),
            ("POST", f"{_MANYCHAT_API_BASE}/fb/broadcasting/getLogs", {"flow_id": flow_id, "flow_ns": flow_id, "page_id": page_id}),
            ("GET", f"{_MANYCHAT_API_BASE}/fb/sending/getFlowStats", {"flow_id": flow_id, "flow_ns": flow_id, "id": flow_id, "page_id": page_id}),
            ("POST", f"{_MANYCHAT_API_BASE}/fb/sending/getFlowStats", {"flow_id": flow_id, "flow_ns": flow_id, "id": flow_id, "page_id": page_id}),
        ]
        out: dict[str, dict] = {}
        async with httpx.AsyncClient(timeout=20.0) as client:
            for method, endpoint, payload_data in endpoints:
                try:
                    if method == "GET":
                        resp_probe = await client.get(endpoint, headers=headers, params=payload_data)
                    else:
                        resp_probe = await client.post(endpoint, headers=headers, json=payload_data)
                    parsed = _parse_json_or_text(resp_probe)
                    out[f"{method} {endpoint}"] = {
                        "status": resp_probe.status_code,
                        "body": parsed,
                    }
                    logger.info(
                        "ManyChat probe raw: channel=%s flow_id=%s method=%s endpoint=%s status=%s body=%s",
                        channel_name,
                        flow_id,
                        method,
                        endpoint,
                        resp_probe.status_code,
                        parsed,
                    )
                except Exception:
                    logger.exception(
                        "ManyChat probe failed: channel=%s flow_id=%s method=%s endpoint=%s",
                        channel_name,
                        flow_id,
                        method,
                        endpoint,
                    )
        return out

    async def _compute_db_counts_for_flow(
        flow_id: str, channel_name: str
    ) -> tuple[dict[str, int], dict[str, list[str]]]:
        """Real webhook counts from manychat_events for one flow/channel."""
        sent_events_result = await db.execute(
            select(
                ManyChatEvent.manychat_subscriber_id,
                func.count(ManyChatEvent.id).label("sent_count"),
            )
            .where(
                ManyChatEvent.org_id == org_id,
                ManyChatEvent.flow_id == flow_id,
                ManyChatEvent.event_type == "sent",
                ManyChatEvent.channel == channel_name,
            )
            .group_by(ManyChatEvent.manychat_subscriber_id)
        )
        sent_event_rows = sent_events_result.all()
        sent_subscriber_ids = [
            str(r.manychat_subscriber_id) for r in sent_event_rows if r.manychat_subscriber_id
        ]
        sent = int(sum(int(r.sent_count or 0) for r in sent_event_rows))

        clicked_events_result = await db.execute(
            select(
                ManyChatEvent.manychat_subscriber_id,
                func.count(ManyChatEvent.id).label("clicked_count"),
            )
            .where(
                ManyChatEvent.org_id == org_id,
                ManyChatEvent.flow_id == flow_id,
                ManyChatEvent.event_type == "clicked",
                ManyChatEvent.channel == channel_name,
            )
            .group_by(ManyChatEvent.manychat_subscriber_id)
        )
        clicked_event_rows = clicked_events_result.all()
        clicked_subscriber_ids = [
            str(r.manychat_subscriber_id) for r in clicked_event_rows if r.manychat_subscriber_id
        ]
        clicked = int(sum(int(r.clicked_count or 0) for r in clicked_event_rows))
        counts = {
            "sent": sent,
            "clicked": clicked,
        }
        logger.info(
            "ManyChat webhook counts: flow_id=%s channel=%s counts=%s",
            flow_id,
            channel_name,
            counts,
        )
        return counts, {"sent": sent_subscriber_ids, "clicked": clicked_subscriber_ids}

    async def _fetch_flow_stats(flow_id: str, channel_name: str) -> dict | None:
        stats_url = f"{_MANYCHAT_API_BASE}/fb/sending/getFlowStats"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                get_resp = await client.get(
                    stats_url,
                    headers=headers,
                    params={"flow_id": flow_id, "flow_ns": flow_id, "id": flow_id, "page_id": page_id},
                )
                get_payload = _parse_json_or_text(get_resp)
                logger.info(
                    "ManyChat getFlowStats GET raw: channel=%s flow_id=%s status=%s body=%s",
                    channel_name,
                    flow_id,
                    get_resp.status_code,
                    get_payload if isinstance(get_payload, dict) else str(get_payload)[:2000],
                )
                post_resp = await client.post(
                    stats_url,
                    headers=headers,
                    json={"flow_id": flow_id, "flow_ns": flow_id, "id": flow_id, "page_id": page_id},
                )
                post_payload = _parse_json_or_text(post_resp)
                logger.info(
                    "ManyChat getFlowStats POST raw: channel=%s flow_id=%s status=%s body=%s",
                    channel_name,
                    flow_id,
                    post_resp.status_code,
                    post_payload if isinstance(post_payload, dict) else str(post_payload)[:2000],
                )
        except Exception:
            logger.exception("ManyChat getFlowStats request failed for channel=%s flow_id=%s", channel_name, flow_id)
            return None

        if get_resp.status_code < 400 and isinstance(get_payload, dict):
            return get_payload
        if post_resp.status_code < 400 and isinstance(post_payload, dict):
            return post_payload
        return None

    for ch in requested_channels:
        target_flow_id = preferred_flow_ids_by_channel.get(ch)
        if not target_flow_id:
            continue
        flow_obj = next(
            (
                item
                for item in raw_flows
                if isinstance(item, dict)
                and (
                    item.get("id") == target_flow_id
                    or item.get("flow_ns") == target_flow_id
                    or item.get("ns") == target_flow_id
                )
            ),
            None,
        )
        db_counts, db_subscriber_ids = await _compute_db_counts_for_flow(
            target_flow_id, ch
        )
        sent = db_counts["sent"]
        clicked = db_counts["clicked"]
        metric_subscriber_ids["sent"].extend(db_subscriber_ids["sent"])
        metric_subscriber_ids["clicked"].extend(db_subscriber_ids["clicked"])

        flow_rows.append(
            ManyChatFlowStat(
                flow_id=target_flow_id,
                flow_name=flow_obj.get("name") if isinstance(flow_obj, dict) else None,
                channel=ch,
                sent=sent,
                clicked=clicked,
            )
        )

    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for v in values:
            if v in seen:
                continue
            seen.add(v)
            out.append(v)
        return out

    for key in metric_subscriber_ids:
        metric_subscriber_ids[key] = _dedupe(metric_subscriber_ids[key])

    all_ids = set()
    for ids in metric_subscriber_ids.values():
        all_ids.update(ids)

    subscriber_name_by_id: dict[str, ManyChatMetricSubscriber] = {}
    if all_ids:
        sub_query = select(
            Subscriber.manychat_subscriber_id,
            Subscriber.first_name,
            Subscriber.last_name,
            Subscriber.channel,
        ).where(
            Subscriber.org_id == org_id,
            Subscriber.manychat_subscriber_id.in_(all_ids),
        )
        if normalized_channel in {"instagram", "messenger"}:
            sub_query = sub_query.where(Subscriber.channel == ChannelType(normalized_channel))
        sub_result = await db.execute(sub_query)
        for row in sub_result.all():
            full_name = " ".join(
                [p for p in [row.first_name, row.last_name] if p and str(p).strip()]
            ).strip()
            if not full_name:
                full_name = f"Subscriber {row.manychat_subscriber_id}"
            subscriber_name_by_id[row.manychat_subscriber_id] = ManyChatMetricSubscriber(
                manychat_subscriber_id=row.manychat_subscriber_id,
                name=full_name,
                channel=row.channel.value if row.channel else None,
            )

    def _metric_card(metric_key: str, count: int) -> ManyChatMetricCard:
        subscribers: list[ManyChatMetricSubscriber] = []
        for sid in metric_subscriber_ids[metric_key]:
            existing = subscriber_name_by_id.get(sid)
            if existing:
                subscribers.append(existing)
            else:
                subscribers.append(
                    ManyChatMetricSubscriber(
                        manychat_subscriber_id=sid,
                        name=f"Subscriber {sid}",
                        channel=normalized_channel if normalized_channel != "all" else None,
                    )
                )
        return ManyChatMetricCard(
            count=count,
            source=metric_source_by_key[metric_key],
            subscribers=subscribers,
        )

    total_sent = sum(r.sent for r in flow_rows)
    total_clicked = sum(r.clicked for r in flow_rows)

    message = None
    if not raw_flows:
        message = "ManyChat returned no flows for this API key/page."
    elif total_sent == total_clicked == 0:
        message = "No webhook events recorded yet for these workflows."
    elif all(
        r.flow_name is not None and r.sent >= 0 and r.clicked >= 0
        for r in flow_rows
    ):
        message = "Metrics are based on webhook events (sent and clicked) captured by Attora."

    return ManyChatFlowStatsResponse(
        page_id=page_id,
        channel=normalized_channel,
        available=True,
        message=message,
        sent=_metric_card("sent", total_sent),
        clicked=_metric_card("clicked", total_clicked),
        flows=flow_rows,
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


async def _count_conversations_for_campaign(
    db: AsyncSession,
    org_id: uuid.UUID,
    dt_from: datetime,
    dt_to: datetime,
    campaign_id: str,
) -> int:
    """Count conversations whose subscriber is attributed to this campaign or organic.

    Conversations don't carry a direct campaign attribution, so we route through
    Subscriber.campaign_id (which holds the meta_campaign_id string). Organic
    conversations (campaign_id IS NULL) are included to match the CPQC and
    qualified-count semantics used elsewhere in the per-campaign view.
    """
    activity_ts = func.coalesce(Conversation.last_activity_at, Conversation.created_at)
    result = await db.execute(
        select(func.count())
        .select_from(Conversation)
        .join(Subscriber, Subscriber.id == Conversation.subscriber_id)
        .where(
            Conversation.org_id == org_id,
            activity_ts >= dt_from,
            activity_ts <= dt_to,
            or_(Subscriber.campaign_id == campaign_id, Subscriber.campaign_id.is_(None)),
        )
    )
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
