"""
Attora — Analytics API Routes

GET  /api/analytics                — Aggregated metrics for date range
GET  /api/analytics/roi            — Cost and revenue metrics
GET  /api/analytics/ai-performance — AI metrics
GET  /api/analytics/export         — CSV download
"""

import csv
import io
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.analytics import (
    AIPerformanceResponse,
    AnalyticsResponse,
    ManyChatFlowStatsResponse,
    ROIResponse,
)
from app.services.analytics_service import (
    get_ai_performance,
    get_analytics,
    get_analytics_export_data,
    get_manychat_flow_stats,
    get_roi,
)
from app.api.deps import get_current_user, get_org_id

router = APIRouter()


@router.get("", response_model=AnalyticsResponse)
async def analytics_overview(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    date_from: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    date_to: date = Query(default_factory=date.today),
    channel: str | None = Query(None),
    campaign_id: str | None = Query(None),
    organic: bool = Query(False),
) -> AnalyticsResponse:
    """
    Get aggregated analytics metrics for a date range.

    Returns CPQC, CCR, avg response time, qualification rate,
    funnel data, and daily trends. When campaign_id is provided,
    CPQC is scoped to that campaign plus organic (no-attribution)
    qualifications, with organic counted at $0 spend. When organic=true,
    metrics are scoped to subscribers with post_id populated AND ad_id NULL,
    and a per-post_id breakdown is included in `organic_posts`.
    """
    return await get_analytics(db, org_id, date_from, date_to, channel, campaign_id, organic)


@router.get("/roi", response_model=ROIResponse)
async def analytics_roi(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    date_from: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    date_to: date = Query(default_factory=date.today),
    campaign_id: str | None = Query(None),
) -> ROIResponse:
    """
    Get ROI / money metrics.

    Returns ad spend, CPA, ROAS, revenue, and before/after comparison.
    When campaign_id is provided, ad spend comes from that campaign's
    campaign_metrics rows and conversions/revenue/qualified are scoped
    to that campaign plus organic — same semantic as the CPQC card.
    """
    return await get_roi(db, org_id, date_from, date_to, campaign_id)


@router.get("/ai-performance", response_model=AIPerformanceResponse)
async def analytics_ai_performance(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    date_from: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    date_to: date = Query(default_factory=date.today),
) -> AIPerformanceResponse:
    """
    Get AI performance metrics.

    Returns fallback rate (with 7-day trend), average response time,
    total tokens, and total AI cost.
    """
    return await get_ai_performance(db, org_id, date_from, date_to)


@router.get("/manychat-flow-stats", response_model=ManyChatFlowStatsResponse)
async def analytics_manychat_flow_stats(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    channel: str = Query(default="all"),
) -> ManyChatFlowStatsResponse:
    """
    Get engagement stats for two configured ManyChat workflows.

    Returns sent/clicked counts and subscriber drill-down lists using
    webhook-captured events.
    """
    return await get_manychat_flow_stats(db, org_id, channel)


@router.get("/export")
async def analytics_export(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    date_from: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    date_to: date = Query(default_factory=date.today),
    channel: str | None = Query(None),
) -> StreamingResponse:
    """
    Export analytics data as CSV.

    Returns a CSV file with daily breakdown of all metrics.
    """
    data = await get_analytics_export_data(db, org_id, date_from, date_to, channel)

    # Build CSV in memory
    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    else:
        # Write empty CSV with headers
        headers = [
            "date", "channel", "new_conversations", "active_conversations",
            "total_messages", "avg_messages_per_conversation", "avg_ai_response_time_ms",
            "conversions", "conversion_value", "conversion_rate",
            "ad_spend", "cpa", "roas", "ai_tokens_used", "ai_cost", "fallback_count",
        ]
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()

    output.seek(0)

    filename = f"attora-analytics-{date_from.isoformat()}-to-{date_to.isoformat()}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
