"""Additive OLAP endpoints backed by the configured query engine."""

import csv
import io
import logging
import uuid
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_org_id, get_org_id_from_header
from app.database import get_db
from app.jobs.scheduler import run_olap_job
from app.models.base import UserRole
from app.models.user import OrgUser
from app.models.user import User
from app.schemas.analytics import AIPerformanceResponse, AnalyticsResponse, ROIResponse
from app.schemas.campaigns import AdSetSummary, AdSummary, BreakdownItem, CampaignDailyMetric, CampaignSummary
from app.schemas.dashboard import DashboardOverviewResponse
from app.services.olap_service import (
    get_olap_ai_performance,
    get_olap_analytics,
    get_olap_analytics_export_data,
    get_olap_campaign_breakdowns,
    get_olap_campaign_detail,
    get_olap_dashboard_overview,
    get_olap_roi,
    list_olap_adsets,
    list_olap_ads,
    list_olap_campaigns,
)
from app.services.analytics_service import (
    get_ai_performance,
    get_analytics,
    get_analytics_export_data,
    get_roi,
)
from app.services.olap_seed_service import (
    DEFAULT_TEST_DATA_SEED,
    SeedOlapTestDataParams,
    seed_olap_test_data,
    summarize_seed_result,
)

router = APIRouter()
logger = logging.getLogger("attora.api.olap")


class TriggerOlapJobRequest(BaseModel):
    job: Literal[
        "export_campaign_facts",
        "export_daily_analytics",
        "export_ai_usage",
        "archive_messages",
        "check_olap_parity",
        "check_reporting_parity",
    ]
    org_id: uuid.UUID | None = None
    org_ids: list[uuid.UUID] | None = None
    date_from: date | None = None
    date_to: date | None = None
    target_date: date | None = None
    older_than_days: int | None = None
    limit: int | None = None
    delta_days: int | None = None
    use_checkpoint: bool = True
    export_all: bool = False


class SeedOlapTestDataRequest(BaseModel):
    date_from: date
    date_to: date
    seed: int = DEFAULT_TEST_DATA_SEED
    campaign_count: int = 3
    adsets_per_campaign: int = 2
    ads_per_adset: int = 2
    replace_existing: bool = False


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


def _default_date_from() -> date:
    return date.today() - timedelta(days=30)


def _default_date_to() -> date:
    return date.today()


def _raise_olap_error(error: Exception) -> None:
    if isinstance(error, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


async def _ensure_org_admin_access(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    membership_result = await db.execute(
        select(OrgUser)
        .where(OrgUser.user_id == user_id)
        .where(OrgUser.org_id == org_id)
    )
    membership = membership_result.scalar_one_or_none()
    if membership is None or membership.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Requires owner or admin role.",
        )


@router.post("/jobs/trigger")
async def trigger_olap_job(
    payload: TriggerOlapJobRequest,
    current_user: User = Depends(get_current_user),
    current_org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await run_olap_job(
            db,
            payload.job,
            org_id=payload.org_id or current_org_id,
            org_ids=payload.org_ids,
            date_from=payload.date_from,
            date_to=payload.date_to,
            target_date=payload.target_date,
            older_than_days=payload.older_than_days,
            limit=payload.limit,
            delta_days=payload.delta_days,
            use_checkpoint=payload.use_checkpoint,
            export_all=payload.export_all,
        )
        await db.commit()
        return {"job": payload.job, "result": result}
    except Exception as error:
        await db.rollback()
        _raise_olap_error(error)


@router.post("/jobs/seed-test-data")
async def seed_test_data(
    payload: SeedOlapTestDataRequest,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id_from_header),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _ensure_org_admin_access(db, user_id=current_user.id, org_id=org_id)

    try:
        summary = await seed_olap_test_data(
            db,
            SeedOlapTestDataParams(
                date_from=payload.date_from,
                date_to=payload.date_to,
                org_id=org_id,
                seed=payload.seed,
                campaign_count=payload.campaign_count,
                adsets_per_campaign=payload.adsets_per_campaign,
                ads_per_adset=payload.ads_per_adset,
                replace_existing=payload.replace_existing,
            ),
        )
        await db.commit()
        return {
            "org_id": str(org_id),
            "date_from": payload.date_from.isoformat(),
            "date_to": payload.date_to.isoformat(),
            "seed": payload.seed,
            "campaign_count": payload.campaign_count,
            "adsets_per_campaign": payload.adsets_per_campaign,
            "ads_per_adset": payload.ads_per_adset,
            "replace_existing": payload.replace_existing,
            "result": summarize_seed_result(summary),
        }
    except Exception as error:
        await db.rollback()
        _raise_olap_error(error)


@router.get("/dashboard", response_model=DashboardOverviewResponse)
async def olap_dashboard_overview(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
) -> DashboardOverviewResponse:
    try:
        return DashboardOverviewResponse(**(await get_olap_dashboard_overview(org_id)))
    except Exception as error:
        _raise_olap_error(error)


@router.get("/analytics", response_model=AnalyticsResponse)
async def olap_analytics_overview(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    date_from: date = Query(default_factory=_default_date_from),
    date_to: date = Query(default_factory=_default_date_to),
    channel: str | None = Query(None),
) -> AnalyticsResponse:
    try:
        response = await get_olap_analytics(org_id, date_from, date_to, channel)
        if not _is_empty_analytics_response(response):
            return response
        logger.info("OLAP analytics endpoint returned empty data for org %s; falling back to PostgreSQL", org_id)
        return await get_analytics(db, org_id, date_from, date_to, channel)
    except Exception as error:
        logger.exception("OLAP analytics endpoint failed for org %s; falling back to PostgreSQL", org_id)
        try:
            return await get_analytics(db, org_id, date_from, date_to, channel)
        except Exception:
            _raise_olap_error(error)


@router.get("/analytics/roi", response_model=ROIResponse)
async def olap_analytics_roi(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    date_from: date = Query(default_factory=_default_date_from),
    date_to: date = Query(default_factory=_default_date_to),
) -> ROIResponse:
    try:
        response = await get_olap_roi(org_id, date_from, date_to)
        if not _is_empty_roi_response(response):
            return response
        logger.info("OLAP ROI endpoint returned empty data for org %s; falling back to PostgreSQL", org_id)
        return await get_roi(db, org_id, date_from, date_to)
    except Exception as error:
        logger.exception("OLAP ROI endpoint failed for org %s; falling back to PostgreSQL", org_id)
        try:
            return await get_roi(db, org_id, date_from, date_to)
        except Exception:
            _raise_olap_error(error)


@router.get("/analytics/ai-performance", response_model=AIPerformanceResponse)
async def olap_analytics_ai_performance(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    date_from: date = Query(default_factory=_default_date_from),
    date_to: date = Query(default_factory=_default_date_to),
) -> AIPerformanceResponse:
    try:
        response = await get_olap_ai_performance(org_id, date_from, date_to)
        if not _is_empty_ai_response(response):
            return response
        logger.info("OLAP AI performance endpoint returned empty data for org %s; falling back to PostgreSQL", org_id)
        return await get_ai_performance(db, org_id, date_from, date_to)
    except Exception as error:
        logger.exception("OLAP AI performance endpoint failed for org %s; falling back to PostgreSQL", org_id)
        try:
            return await get_ai_performance(db, org_id, date_from, date_to)
        except Exception:
            _raise_olap_error(error)


@router.get("/analytics/export")
async def olap_analytics_export(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    date_from: date = Query(default_factory=_default_date_from),
    date_to: date = Query(default_factory=_default_date_to),
    channel: str | None = Query(None),
) -> StreamingResponse:
    try:
        data = await get_olap_analytics_export_data(org_id, date_from, date_to, channel)
        if not data:
            logger.info("OLAP analytics export endpoint returned empty data for org %s; falling back to PostgreSQL", org_id)
            data = await get_analytics_export_data(db, org_id, date_from, date_to, channel)
    except Exception as error:
        logger.exception("OLAP analytics export endpoint failed for org %s; falling back to PostgreSQL", org_id)
        try:
            data = await get_analytics_export_data(db, org_id, date_from, date_to, channel)
        except Exception:
            _raise_olap_error(error)

    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    else:
        headers = [
            "date", "channel", "new_conversations", "active_conversations",
            "total_messages", "avg_messages_per_conversation", "avg_ai_response_time_ms",
            "conversions", "conversion_value", "conversion_rate",
            "ad_spend", "cpa", "roas", "ai_tokens_used", "ai_cost", "fallback_count",
        ]
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()

    output.seek(0)
    filename = f"attora-olap-analytics-{date_from.isoformat()}-to-{date_to.isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/campaigns", response_model=list[CampaignSummary])
async def olap_list_campaigns(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    date_from: date = Query(default_factory=_default_date_from),
    date_to: date = Query(default_factory=_default_date_to),
) -> list[CampaignSummary]:
    try:
        return await list_olap_campaigns(org_id, date_from, date_to)
    except Exception as error:
        _raise_olap_error(error)


@router.get("/campaigns/{campaign_id}", response_model=list[CampaignDailyMetric])
async def olap_campaign_detail(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    date_from: date = Query(default_factory=_default_date_from),
    date_to: date = Query(default_factory=_default_date_to),
) -> list[CampaignDailyMetric]:
    try:
        return await get_olap_campaign_detail(org_id, campaign_id, date_from, date_to)
    except Exception as error:
        _raise_olap_error(error)


@router.get("/campaigns/{campaign_id}/adsets", response_model=list[AdSetSummary])
async def olap_list_adsets(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    date_from: date = Query(default_factory=_default_date_from),
    date_to: date = Query(default_factory=_default_date_to),
) -> list[AdSetSummary]:
    try:
        return await list_olap_adsets(org_id, campaign_id, date_from, date_to)
    except Exception as error:
        _raise_olap_error(error)


@router.get("/campaigns/{campaign_id}/adsets/{adset_id}/ads", response_model=list[AdSummary])
async def olap_list_ads(
    campaign_id: str,
    adset_id: str,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    date_from: date = Query(default_factory=_default_date_from),
    date_to: date = Query(default_factory=_default_date_to),
) -> list[AdSummary]:
    try:
        return await list_olap_ads(org_id, campaign_id, adset_id, date_from, date_to)
    except Exception as error:
        _raise_olap_error(error)


@router.get("/campaigns/{campaign_id}/breakdowns", response_model=list[BreakdownItem])
async def olap_campaign_breakdowns(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    type: str = Query(..., description='Breakdown type: "age_gender" or "platform"'),
    date_from: date = Query(default_factory=_default_date_from),
    date_to: date = Query(default_factory=_default_date_to),
) -> list[BreakdownItem]:
    try:
        return await get_olap_campaign_breakdowns(org_id, campaign_id, type, date_from, date_to)
    except Exception as error:
        _raise_olap_error(error)