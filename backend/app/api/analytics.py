"""
Attora — Analytics API Routes

GET  /api/analytics                — Aggregated metrics for date range
GET  /api/analytics/roi            — Cost and revenue metrics
GET  /api/analytics/ai-performance — AI metrics
GET  /api/analytics/export         — CSV download
"""

import csv
import io
import logging
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
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
from app.services.olap_service import (
    get_olap_ai_performance,
    get_olap_analytics,
    get_olap_analytics_export_data,
    get_olap_roi,
)
from app.api.deps import get_current_user, get_org_id

router = APIRouter()
logger = logging.getLogger("attora.api.analytics")


def _is_empty_analytics_response(payload: AnalyticsResponse | dict) -> bool:
    data = payload.model_dump() if isinstance(payload, AnalyticsResponse) else payload
    return (
        int(data.get("total_conversations") or 0) == 0
        and int(data.get("total_conversions") or 0) == 0
        and float(data.get("total_revenue") or 0.0) == 0.0
        and not data.get("cpqc_trend")
        and not data.get("ccr_trend")
    )


def _is_empty_roi_response(payload: ROIResponse | dict) -> bool:
    data = payload.model_dump() if isinstance(payload, ROIResponse) else payload
    return (
        float(data.get("ad_spend") or 0.0) == 0.0
        and int(data.get("conversations_count") or 0) == 0
        and int(data.get("converted_count") or 0) == 0
        and float(data.get("revenue") or 0.0) == 0.0
    )


def _is_empty_ai_response(payload: AIPerformanceResponse | dict) -> bool:
    data = payload.model_dump() if isinstance(payload, AIPerformanceResponse) else payload
    return (
        int(data.get("total_ai_tokens") or 0) == 0
        and float(data.get("total_ai_cost") or 0.0) == 0.0
        and not data.get("fallback_trend")
        and data.get("avg_response_time_ms") is None
    )


@router.get("", response_model=AnalyticsResponse)
async def analytics_overview(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    date_from: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    date_to: date = Query(default_factory=date.today),
    channel: str | None = Query(None),
) -> AnalyticsResponse:
    """
    Get aggregated analytics metrics for a date range.

    Returns CPQC, CCR, avg response time, qualification rate,
    funnel data, and daily trends.
    """
    if settings.reporting_api_use_olap:
        try:
            response = await get_olap_analytics(org_id, date_from, date_to, channel)
            if not _is_empty_analytics_response(response):
                return response
            logger.info("OLAP analytics returned empty data for org %s; falling back to PostgreSQL", org_id)
        except Exception:
            logger.exception("OLAP analytics failed for org %s; falling back to PostgreSQL", org_id)
    return await get_analytics(db, org_id, date_from, date_to, channel)


@router.get("/roi", response_model=ROIResponse)
async def analytics_roi(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    date_from: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    date_to: date = Query(default_factory=date.today),
) -> ROIResponse:
    """
    Get ROI / money metrics.

    Returns ad spend, CPA, ROAS, revenue, and before/after comparison.
    """
    if settings.reporting_api_use_olap:
        try:
            response = await get_olap_roi(org_id, date_from, date_to)
            if not _is_empty_roi_response(response):
                return response
            logger.info("OLAP ROI returned empty data for org %s; falling back to PostgreSQL", org_id)
        except Exception:
            logger.exception("OLAP ROI failed for org %s; falling back to PostgreSQL", org_id)
    return await get_roi(db, org_id, date_from, date_to)


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
    if settings.reporting_api_use_olap:
        try:
            response = await get_olap_ai_performance(org_id, date_from, date_to)
            if not _is_empty_ai_response(response):
                return response
            logger.info("OLAP AI performance returned empty data for org %s; falling back to PostgreSQL", org_id)
        except Exception:
            logger.exception("OLAP AI performance failed for org %s; falling back to PostgreSQL", org_id)
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
    if settings.reporting_api_use_olap:
        try:
            data = await get_olap_analytics_export_data(org_id, date_from, date_to, channel)
            if not data:
                logger.info("OLAP analytics export returned empty data for org %s; falling back to PostgreSQL", org_id)
                data = await get_analytics_export_data(db, org_id, date_from, date_to, channel)
        except Exception:
            logger.exception("OLAP analytics export failed for org %s; falling back to PostgreSQL", org_id)
            data = await get_analytics_export_data(db, org_id, date_from, date_to, channel)
    else:
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
