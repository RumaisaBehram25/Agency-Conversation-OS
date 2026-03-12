"""
Attora — Analytics Pydantic Schemas

Request/response models for analytics aggregation and export endpoints.
"""

from datetime import date

from pydantic import BaseModel


class FunnelStep(BaseModel):
    """Single step in the conversion funnel."""

    name: str
    volume: int
    drop_off_rate: float | None = None


class DailyTrend(BaseModel):
    """Single data point in a daily trend array."""

    date: date
    value: float


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

    # Totals
    total_conversations: int = 0
    total_conversions: int = 0
    total_revenue: float = 0.0

    # Funnel
    funnel: list[FunnelStep] = []

    # Daily trends
    cpqc_trend: list[DailyTrend] = []
    ccr_trend: list[DailyTrend] = []


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
