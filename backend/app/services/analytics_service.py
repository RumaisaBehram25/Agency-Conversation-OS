"""
Attora — Analytics Service

Computes CPQC, CCR, funnel data, trends, ROI, AI performance,
and campaign health from DailyAnalytics + raw tables.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import DailyAnalytics
from app.models.campaign import AdCampaign
from app.models.campaign_metrics import CampaignMetric
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


def _campaigns_of_source_type_subquery(org_id: uuid.UUID, source_type: str):
    """Subquery returning ad_campaigns.id for the given source_type in an org."""
    return (
        select(AdCampaign.id)
        .where(
            AdCampaign.org_id == org_id,
            AdCampaign.source_type == source_type,
        )
        .scalar_subquery()
    )


def _subscriber_campaign_clause(
    campaign_id: str | None,
    attora_campaign_id: uuid.UUID | None,
    *,
    org_id: uuid.UUID | None = None,
    source_type: str | None = None,
):
    """Build the per-campaign Subscriber filter clause.

    Priority:
    - attora_campaign_id (specific organic) → strict match on that one campaign
    - campaign_id (specific paid) → that meta_campaign_id + organic NULL
      (legacy semantic that credits organic-driven qualifications to the
      running paid campaign)
    - source_type aggregate (paid/organic) → IN (campaigns of that type).
      For organic this is "any organic campaign in the org"; for paid it
      excludes purely organic-attributed subscribers from the count.
    """
    if attora_campaign_id is not None:
        return Subscriber.attora_campaign_id == attora_campaign_id
    if campaign_id is not None:
        return or_(Subscriber.campaign_id == campaign_id, Subscriber.campaign_id.is_(None))
    if source_type is not None and org_id is not None:
        return Subscriber.attora_campaign_id.in_(
            _campaigns_of_source_type_subquery(org_id, source_type)
        )
    return None


def _conversion_event_campaign_clause(
    campaign_id: str | None,
    attora_campaign_id: uuid.UUID | None,
    *,
    org_id: uuid.UUID | None = None,
    source_type: str | None = None,
):
    """Build the per-campaign ConversionEvent filter clause.

    Mirrors _subscriber_campaign_clause but for ConversionEvent rows.
    """
    if attora_campaign_id is not None:
        return ConversionEvent.attora_campaign_id == attora_campaign_id
    if campaign_id is not None:
        return or_(
            ConversionEvent.meta_campaign_id == campaign_id,
            ConversionEvent.meta_campaign_id.is_(None),
        )
    if source_type is not None and org_id is not None:
        return ConversionEvent.attora_campaign_id.in_(
            _campaigns_of_source_type_subquery(org_id, source_type)
        )
    return None


async def get_analytics(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    channel: str | None = None,
    campaign_id: str | None = None,
    attora_campaign_id: uuid.UUID | None = None,
    source_type: str | None = None,
) -> AnalyticsResponse:
    """Compute aggregated analytics metrics for a date range."""
    # source_type is ignored when a specific campaign is selected — the more
    # specific scope wins.
    if campaign_id or attora_campaign_id is not None:
        source_type = None

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
    # Headline counts should always reflect the active scope filter. The
    # ORG-wide path falls through to DailyAnalytics aggregates; any specific
    # campaign or source-type filter routes through subscriber/conversion
    # tables so the numbers actually scope.
    if campaign_id or attora_campaign_id is not None or source_type is not None:
        dt_from_for_count = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
        dt_to_for_count = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)
        total_conversations = await _count_conversations_for_campaign(
            db, org_id, dt_from_for_count, dt_to_for_count,
            campaign_id=campaign_id,
            attora_campaign_id=attora_campaign_id,
            source_type=source_type,
        )

        # Conversions + revenue from ConversionEvent scoped to the same filter.
        cev_clause = _conversion_event_campaign_clause(
            campaign_id, attora_campaign_id, org_id=org_id, source_type=source_type
        )
        cev_filters = [
            ConversionEvent.org_id == org_id,
            ConversionEvent.created_at >= dt_from_for_count,
            ConversionEvent.created_at <= dt_to_for_count,
        ]
        if cev_clause is not None:
            cev_filters.append(cev_clause)
        conv_result = await db.execute(
            select(
                func.count().label("converted_count"),
                func.coalesce(func.sum(ConversionEvent.value), 0).label("revenue"),
            ).where(*cev_filters)
        )
        conv_row = conv_result.one()
        total_conversions = int(conv_row.converted_count)
        total_revenue = float(conv_row.revenue)
    else:
        total_conversations = await _count_conversations_raw(db, org_id, date_from, date_to, channel)
        total_conversions = int(row.total_conversions)
        total_revenue = float(row.total_revenue)
    avg_response_time_ms = int(row.avg_response_time_ms) if row.avg_response_time_ms else None

    # CPQC numerator: org-wide ad_spend by default; campaign-scoped when
    # campaign_id is provided. Organic flows have no spend, so an
    # attora_campaign_id-scoped view (or a source_type='organic' aggregate)
    # forces the numerator to $0 — that's the intended client-facing semantic.
    if attora_campaign_id is not None or source_type == "organic":
        total_ad_spend = 0.0
    elif campaign_id:
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
        # source_type='paid' or no source filter — use the org-wide ad_spend
        # already aggregated in DailyAnalytics. (Paid is the only thing that
        # produces spend, so this is effectively the same number for both.)
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
    # When scoped to a campaign or source aggregate, apply the per-campaign
    # Subscriber clause:
    #   - paid (campaign_id):     campaign + organic NULL  (legacy semantic)
    #   - organic (attora_campaign_id): only that one Attora campaign
    #   - source_type aggregate: any campaign of that source_type in the org
    sub_clause = _subscriber_campaign_clause(
        campaign_id, attora_campaign_id, org_id=org_id, source_type=source_type
    )
    if sub_clause is not None:
        qualified_filters.append(sub_clause)

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
        elif campaign_id or attora_campaign_id or source_type == "organic":
            # Explicit campaign scope (or organic aggregate) with $0 spend →
            # meaningful "free leads" answer rather than the org-wide "—"
            # we use for unattributed views.
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
        db, org_id, date_from, date_to, filters, campaign_id, attora_campaign_id, source_type
    )
    ccr_trend = await _compute_daily_ccr_trend(
        db, org_id, date_from, date_to, filters, campaign_id, attora_campaign_id, source_type
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
    attora_campaign_id: uuid.UUID | None = None,
    source_type: str | None = None,
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

    if campaign_id or attora_campaign_id is not None or source_type is not None:
        # Spend: only paid campaigns produce CampaignMetric rows. Organic
        # (attora_campaign_id-only or source_type='organic') trends always
        # show $0 spend → null CPQC, which renders as a gap rather than a
        # misleading flat zero.
        if attora_campaign_id is not None or source_type == "organic":
            spend_by_date = {}
        elif source_type == "paid":
            # Org-wide paid spend by day from DailyAnalytics.
            spend_rows = await db.execute(
                select(
                    DailyAnalytics.date,
                    func.coalesce(func.sum(DailyAnalytics.ad_spend), 0).label("ad_spend"),
                )
                .where(and_(*filters))
                .group_by(DailyAnalytics.date)
            )
            spend_by_date = {r.date: float(r.ad_spend) for r in spend_rows.all()}
        else:
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

        sub_clause = _subscriber_campaign_clause(
            campaign_id, attora_campaign_id, org_id=org_id, source_type=source_type
        )
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
                sub_clause,
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
    attora_campaign_id: uuid.UUID | None = None,
    source_type: str | None = None,
) -> list[DailyTrend]:
    """Compute daily CCR trend.

    Org-wide: from daily_analytics (channel=NULL combined row).
    Campaign-scoped: counts conversions from ConversionEvent and
    conversations from Conversation routed via Subscriber.campaign_id —
    matches the per-campaign semantic used elsewhere (campaign + organic).

    Days with no conversations emit value=None so the chart shows gaps
    instead of misleading flat zeros.
    """
    if not campaign_id and attora_campaign_id is None and source_type is None:
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

    sub_clause = _subscriber_campaign_clause(
        campaign_id, attora_campaign_id, org_id=org_id, source_type=source_type
    )
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
            sub_clause,
        )
        .group_by(func.date(activity_ts))
    )
    conversations_by_date = {r.d: int(r.conversations) for r in conv_rows.all()}

    cev_clause = _conversion_event_campaign_clause(
        campaign_id, attora_campaign_id, org_id=org_id, source_type=source_type
    )
    conversion_rows = await db.execute(
        select(
            func.date(ConversionEvent.created_at).label("d"),
            func.count().label("converted"),
        )
        .where(
            ConversionEvent.org_id == org_id,
            ConversionEvent.created_at >= dt_from,
            ConversionEvent.created_at <= dt_to,
            cev_clause,
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
    attora_campaign_id: uuid.UUID | None = None,
    source_type: str | None = None,
) -> ROIResponse:
    """Compute ROI / money metrics.

    When campaign_id is supplied, spend is taken from CampaignMetric for that
    campaign (matching the dropdown label and the CPQC card), and conversions
    /revenue/qualified are counted for that campaign plus organic
    (campaign_id IS NULL) — the same "incl. organic at $0" semantic CPQC uses.
    Without campaign_id, ROI is org-wide and reads from daily_analytics.
    """

    # source_type is ignored when a specific campaign is selected.
    if campaign_id or attora_campaign_id is not None:
        source_type = None

    dt_from = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
    dt_to = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)

    if campaign_id or attora_campaign_id is not None or source_type is not None:
        # ── Spend: paid via CampaignMetric, organic forced to $0 ────────
        if attora_campaign_id is not None or source_type == "organic":
            ad_spend = 0.0
        elif source_type == "paid":
            # All paid spend in the org — same as the org-wide DailyAnalytics
            # aggregate, since paid is the only thing that produces ad_spend.
            spend_result = await db.execute(
                select(func.coalesce(func.sum(DailyAnalytics.ad_spend), 0))
                .where(
                    DailyAnalytics.org_id == org_id,
                    DailyAnalytics.date >= date_from,
                    DailyAnalytics.date <= date_to,
                    DailyAnalytics.channel.is_(None),
                )
            )
            ad_spend = float(spend_result.scalar() or 0)
        else:
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

        # ── Conversions + revenue from ConversionEvent ──
        cev_clause = _conversion_event_campaign_clause(
            campaign_id, attora_campaign_id, org_id=org_id, source_type=source_type
        )
        conv_result = await db.execute(
            select(
                func.count().label("converted_count"),
                func.coalesce(func.sum(ConversionEvent.value), 0).label("revenue"),
            )
            .where(
                ConversionEvent.org_id == org_id,
                ConversionEvent.created_at >= dt_from,
                ConversionEvent.created_at <= dt_to,
                cev_clause,
            )
        )
        conv_row = conv_result.one()
        converted_count = int(conv_row.converted_count)
        revenue = float(conv_row.revenue)

        # ── Conversations: count via subscribers attributed to the campaign ──
        conversations_count = await _count_conversations_for_campaign(
            db, org_id, dt_from, dt_to, campaign_id, attora_campaign_id, source_type
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
    sub_clause = _subscriber_campaign_clause(
        campaign_id, attora_campaign_id, org_id=org_id, source_type=source_type
    )
    if sub_clause is not None:
        qualified_filters.append(sub_clause)
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
    campaign_id: str | None,
    attora_campaign_id: uuid.UUID | None = None,
    source_type: str | None = None,
) -> int:
    """Count conversations whose subscriber is attributed to this campaign.

    Routes through Subscriber attribution since Conversation has no direct
    campaign link. For paid (campaign_id) we include organic NULL to match
    the existing 'campaign + organic' semantic; for organic we strictly
    scope to the one attora_campaign_id; for source_type aggregate we scope
    to all campaigns of that source type in the org.
    """
    activity_ts = func.coalesce(Conversation.last_activity_at, Conversation.created_at)
    sub_clause = _subscriber_campaign_clause(
        campaign_id, attora_campaign_id, org_id=org_id, source_type=source_type
    )
    where_clauses = [
        Conversation.org_id == org_id,
        activity_ts >= dt_from,
        activity_ts <= dt_to,
    ]
    if sub_clause is not None:
        where_clauses.append(sub_clause)
    result = await db.execute(
        select(func.count())
        .select_from(Conversation)
        .join(Subscriber, Subscriber.id == Conversation.subscriber_id)
        .where(*where_clauses)
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
