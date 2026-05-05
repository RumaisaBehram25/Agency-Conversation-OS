"""
Attora — Analytics Pydantic Schemas

Request/response models for analytics aggregation and export endpoints.
"""

from datetime import date, datetime

from pydantic import BaseModel


class FunnelStep(BaseModel):
    """Single step in the conversion funnel."""

    name: str
    volume: int
    drop_off_rate: float | None = None


class PurchasesDailyPoint(BaseModel):
    """One calendar day of Hyros-attributed purchases (by hyros_synced_at bucket)."""

    date: date
    purchases: int = 0


class DailyTrend(BaseModel):
    """Single data point in a daily trend array.

    value=None means "no data for this day" — frontend should render
    this as a gap in the line, not a flat zero, so paused-campaign and
    no-traffic days don't read as legitimate $0 / 0% values.
    """

    date: date
    value: float | None = None


class OrganicPostBreakdown(BaseModel):
    """Per-post metrics for organic traffic.

    Organic = subscribers with post_id populated and ad_id NULL. Each row
    represents one post_id and its attributed funnel volumes.
    """

    post_id: str
    channel: str | None = None
    conversations: int = 0
    qualified: int = 0
    converted: int = 0
    qualification_rate: float | None = None
    conversion_rate: float | None = None


class AnalyticsResponse(BaseModel):
    """GET /api/analytics — Aggregated metrics for a date range."""

    date_from: date
    date_to: date
    channel: str | None = None

    # Key metrics
    cpqc: float | None = None
    ccr: float | None = None
    avg_response_time_ms: int | None = None
    qualification_rate: float | None = None
    hyros_confirmed_purchases: int = 0

    # Hyros + spend efficiency (same date range + scope as other tiles)
    cost_per_purchase: float | None = None
    cost_per_conversation: float | None = None
    purchases_count: int = 0
    conversations_count: int = 0

    # Totals
    total_conversations: int = 0
    total_conversions: int = 0
    total_revenue: float = 0.0

    # Funnel
    funnel: list[FunnelStep] = []

    # Daily trends
    cpqc_trend: list[DailyTrend] = []
    ccr_trend: list[DailyTrend] = []

    purchases_over_time: list[PurchasesDailyPoint] = []

    # Per-post breakdown — only populated when organic=true is requested.
    organic_posts: list[OrganicPostBreakdown] = []


class ROIResponse(BaseModel):
    """GET /api/analytics/roi — Cost and revenue metrics."""

    date_from: date
    date_to: date

    ad_spend: float = 0.0
    conversations_count: int = 0
    cost_per_conversation: float | None = None
    qualified_count: int = 0
    cost_per_qualified: float | None = None
    converted_count: int = 0
    cpa: float | None = None
    revenue: float = 0.0
    roas: float | None = None

    # Before/after comparison
    baseline_cpa: float | None = None
    current_cpa: float | None = None
    baseline_roas: float | None = None
    current_roas: float | None = None


class AIPerformanceResponse(BaseModel):
    """GET /api/analytics/ai-performance — AI metrics."""

    fallback_rate: float | None = None
    fallback_trend: list[DailyTrend] = []
    avg_response_time_ms: int | None = None
    total_ai_tokens: int = 0
    total_ai_cost: float = 0.0


class ManyChatMetricSubscriber(BaseModel):
    """Subscriber entry shown in ManyChat metric detail modal."""

    manychat_subscriber_id: str
    name: str
    channel: str | None = None


class ManyChatMetricCard(BaseModel):
    """Single metric card with count + subscriber drill-down."""

    count: int = 0
    source: str = "manychat_api"
    subscribers: list[ManyChatMetricSubscriber] = []


class ManyChatFlowStat(BaseModel):
    """Per-flow engagement metrics from ManyChat."""

    flow_id: str
    flow_name: str | None = None
    channel: str
    sent: int = 0
    clicked: int = 0


class ManyChatFlowStatsResponse(BaseModel):
    """Aggregated stats for selected ManyChat workflows."""

    page_id: str | None = None
    channel: str = "all"
    available: bool = True
    message: str | None = None
    sent: ManyChatMetricCard = ManyChatMetricCard()
    clicked: ManyChatMetricCard = ManyChatMetricCard()
    flows: list[ManyChatFlowStat] = []


class HyrosSyncRunSummary(BaseModel):
    """One persisted Hyros sync run for match-quality visibility."""

    synced_at: datetime
    sales_scanned: int
    purchases_matched: int
    unmatched_sales: int
    matched_by_attora_id: int
    matched_by_attora_sub: int
    matched_by_email: int
    match_rate_pct: float | None = None
    # Lead-side attora_id matches ÷ Hyros sale rows (proxy for tagging quality).
    attora_id_signal_pct: float | None = None


class HyrosSourceBreakdownRow(BaseModel):
    """Per Hyros traffic-source bucket: volume + allocated campaign spend + ratios."""

    traffic_source: str | None = None  # None = organic (null/blank hyros_traffic_source)
    purchases_count: int = 0
    conversations_count: int = 0
    ad_spend: float | None = None
    cost_per_purchase: float | None = None
    cost_per_conversation: float | None = None


class HyrosSyncHealthResponse(BaseModel):
    """GET /api/analytics/hyros-sync-health — recent sync runs + aggregate match rate."""

    sync_runs: list[HyrosSyncRunSummary] = []
    avg_match_rate: float | None = None
    last_synced_at: datetime | None = None


class OrganicKeywordStatsResponse(BaseModel):
    """GET /api/analytics/organic-keyword-stats — counts for macros/muscles keyword conversations."""

    total_conversations: int = 0
    total_conversions: int = 0
    total_revenue: float = 0.0
    funnel_conversations: int = 0
    funnel_qualified: int = 0
    funnel_converted: int = 0
