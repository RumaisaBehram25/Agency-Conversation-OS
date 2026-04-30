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
    ROIResponse,
)
from app.services.analytics_service import (
    get_ai_performance,
    get_analytics,
    get_analytics_export_data,
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
    attora_campaign_id: uuid.UUID | None = Query(
        None,
        description=(
            "Scope to a specific organic Attora campaign (UUID). Mutually "
            "exclusive with campaign_id; ad spend is forced to $0."
        ),
    ),
    source_type: str | None = Query(
        None,
        pattern="^(paid|organic)$",
        description=(
            "Aggregate-scope to all campaigns of this source type. Ignored "
            "when campaign_id or attora_campaign_id is also set."
        ),
    ),
) -> AnalyticsResponse:
    """
    Get aggregated analytics metrics for a date range.

    Returns CPQC, CCR, avg response time, qualification rate,
    funnel data, and daily trends. When campaign_id is provided,
    CPQC is scoped to that campaign plus organic (no-attribution)
    qualifications, with organic counted at $0 spend.
    """
    return await get_analytics(
        db, org_id, date_from, date_to, channel, campaign_id, attora_campaign_id, source_type
    )


@router.get("/roi", response_model=ROIResponse)
async def analytics_roi(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    date_from: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    date_to: date = Query(default_factory=date.today),
    campaign_id: str | None = Query(None),
    attora_campaign_id: uuid.UUID | None = Query(
        None,
        description=(
            "Scope to a specific organic Attora campaign (UUID). Mutually "
            "exclusive with campaign_id; ad spend is forced to $0."
        ),
    ),
    source_type: str | None = Query(
        None,
        pattern="^(paid|organic)$",
        description=(
            "Aggregate-scope to all campaigns of this source type. Ignored "
            "when campaign_id or attora_campaign_id is also set."
        ),
    ),
) -> ROIResponse:
    """
    Get ROI / money metrics.

    Returns ad spend, CPA, ROAS, revenue, and before/after comparison.
    When campaign_id is provided, ad spend comes from that campaign's
    campaign_metrics rows and conversions/revenue/qualified are scoped
    to that campaign plus organic — same semantic as the CPQC card.
    """
    return await get_roi(
        db, org_id, date_from, date_to, campaign_id, attora_campaign_id, source_type
    )


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
