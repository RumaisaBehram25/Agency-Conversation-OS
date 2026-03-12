"""
Attora — Dashboard Overview Pydantic Schemas

Response model for the single dashboard overview endpoint.
"""

from pydantic import BaseModel

from app.schemas.analytics import DailyTrend


class CampaignHealth(BaseModel):
    """Health status for a single campaign."""

    name: str
    status: str  # green | yellow | red
    reason: str | None = None


class DashboardOverviewResponse(BaseModel):
    """GET /api/dashboard — Dashboard overview data."""

    cpqc: float | None = None
    cpqc_trend: list[DailyTrend] = []

    ccr: float | None = None
    ccr_trend: list[DailyTrend] = []

    active_conversations_count: int = 0
    todays_conversions: int = 0
    todays_revenue: float = 0.0

    campaign_health: list[CampaignHealth] = []
