"""
Attora — Campaign Drill-Down API Routes

GET  /api/campaign-metrics                                  — List campaigns with aggregated metrics
GET  /api/campaign-metrics/{campaign_id}                    — Campaign detail with daily time series
GET  /api/campaign-metrics/{campaign_id}/adsets             — Ad sets within a campaign
GET  /api/campaign-metrics/{campaign_id}/adsets/{adset_id}/ads — Ads within an ad set
GET  /api/campaign-metrics/{campaign_id}/breakdowns         — Breakdown data (age_gender or platform)
"""

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_org_id
from app.database import get_db
from app.models.campaign import AdCampaign
from app.models.campaign_metrics import CampaignBreakdown, CampaignMetric
from app.models.user import User
from app.schemas.campaigns import (
    AdSetSummary,
    AdSummary,
    BreakdownItem,
    CampaignDailyMetric,
    CampaignSummary,
)

router = APIRouter()


def _default_date_from() -> date:
    return date.today() - timedelta(days=30)


def _default_date_to() -> date:
    return date.today()


def _coalesce_sum(column):
    return func.coalesce(func.sum(column), 0)


def _coalesce_avg(column):
    return func.avg(column)


@router.get("", response_model=list[CampaignSummary])
async def list_campaigns(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    date_from: date = Query(default_factory=_default_date_from),
    date_to: date = Query(default_factory=_default_date_to),
) -> list[CampaignSummary]:
    """List campaigns with aggregated metrics for the given date range.

    Sources the campaign list from ad_campaigns (auto-imported during Meta sync)
    so every Attora-managed campaign appears in the dropdown — even when it had
    no spend in the selected window. Metrics are left-joined from campaign_metrics
    and aggregate to 0 when no rows exist for the range.
    """
    metric_filter = (
        (CampaignMetric.org_id == org_id)
        & (CampaignMetric.level == "campaign")
        & (CampaignMetric.meta_campaign_id == AdCampaign.meta_campaign_id)
        & (CampaignMetric.date >= date_from)
        & (CampaignMetric.date <= date_to)
    )

    query = (
        select(
            AdCampaign.meta_campaign_id.label("meta_campaign_id"),
            func.coalesce(
                func.max(CampaignMetric.meta_campaign_name),
                AdCampaign.name,
            ).label("meta_campaign_name"),
            func.max(CampaignMetric.status).label("status"),
            _coalesce_sum(CampaignMetric.spend).label("spend"),
            _coalesce_sum(CampaignMetric.impressions).label("impressions"),
            _coalesce_sum(CampaignMetric.clicks).label("clicks"),
            _coalesce_sum(CampaignMetric.leads).label("leads"),
            _coalesce_sum(CampaignMetric.link_clicks).label("link_clicks"),
            _coalesce_sum(CampaignMetric.video_views).label("video_views"),
            _coalesce_avg(CampaignMetric.cpc).label("cpc"),
            _coalesce_avg(CampaignMetric.cpm).label("cpm"),
            _coalesce_avg(CampaignMetric.ctr).label("ctr"),
        )
        .select_from(AdCampaign)
        .outerjoin(CampaignMetric, metric_filter)
        .where(AdCampaign.org_id == org_id)
        .where(AdCampaign.is_attora_managed.is_(True))
        .where(AdCampaign.is_active.is_(True))
        .where(AdCampaign.meta_campaign_id.isnot(None))
        .group_by(AdCampaign.meta_campaign_id, AdCampaign.name)
        .order_by(func.coalesce(func.sum(CampaignMetric.spend), 0).desc())
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        CampaignSummary(
            meta_campaign_id=row.meta_campaign_id,
            meta_campaign_name=row.meta_campaign_name,
            status=row.status,
            spend=float(row.spend) if row.spend else 0.0,
            impressions=int(row.impressions) if row.impressions else 0,
            clicks=int(row.clicks) if row.clicks else 0,
            leads=int(row.leads) if row.leads else 0,
            link_clicks=int(row.link_clicks) if row.link_clicks else 0,
            video_views=int(row.video_views) if row.video_views else 0,
            cpc=float(row.cpc) if row.cpc is not None else None,
            cpm=float(row.cpm) if row.cpm is not None else None,
            ctr=float(row.ctr) if row.ctr is not None else None,
        )
        for row in rows
    ]


@router.get("/{campaign_id}", response_model=list[CampaignDailyMetric])
async def get_campaign_detail(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    date_from: date = Query(default_factory=_default_date_from),
    date_to: date = Query(default_factory=_default_date_to),
) -> list[CampaignDailyMetric]:
    """Campaign detail with daily time series."""
    query = (
        select(
            CampaignMetric.date,
            CampaignMetric.spend,
            CampaignMetric.impressions,
            CampaignMetric.clicks,
            CampaignMetric.leads,
            CampaignMetric.cpc,
            CampaignMetric.cpm,
            CampaignMetric.ctr,
            CampaignMetric.reach,
            CampaignMetric.frequency,
        )
        .where(CampaignMetric.org_id == org_id)
        .where(CampaignMetric.level == "campaign")
        .where(CampaignMetric.meta_campaign_id == campaign_id)
        .where(CampaignMetric.date >= date_from)
        .where(CampaignMetric.date <= date_to)
        .order_by(CampaignMetric.date.asc())
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        CampaignDailyMetric(
            date=row.date,
            spend=float(row.spend) if row.spend else 0.0,
            impressions=int(row.impressions) if row.impressions else 0,
            clicks=int(row.clicks) if row.clicks else 0,
            leads=int(row.leads) if row.leads else 0,
            cpc=float(row.cpc) if row.cpc is not None else None,
            cpm=float(row.cpm) if row.cpm is not None else None,
            ctr=float(row.ctr) if row.ctr is not None else None,
            reach=int(row.reach) if row.reach else 0,
            frequency=float(row.frequency) if row.frequency is not None else None,
        )
        for row in rows
    ]


@router.get("/{campaign_id}/adsets", response_model=list[AdSetSummary])
async def list_adsets(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    date_from: date = Query(default_factory=_default_date_from),
    date_to: date = Query(default_factory=_default_date_to),
) -> list[AdSetSummary]:
    """List ad sets within a campaign with aggregated metrics."""
    query = (
        select(
            CampaignMetric.meta_adset_id,
            func.max(CampaignMetric.meta_adset_name).label("meta_adset_name"),
            func.max(CampaignMetric.status).label("status"),
            _coalesce_sum(CampaignMetric.spend).label("spend"),
            _coalesce_sum(CampaignMetric.impressions).label("impressions"),
            _coalesce_sum(CampaignMetric.clicks).label("clicks"),
            _coalesce_sum(CampaignMetric.leads).label("leads"),
            _coalesce_sum(CampaignMetric.link_clicks).label("link_clicks"),
            _coalesce_sum(CampaignMetric.video_views).label("video_views"),
            _coalesce_avg(CampaignMetric.cpc).label("cpc"),
            _coalesce_avg(CampaignMetric.cpm).label("cpm"),
            _coalesce_avg(CampaignMetric.ctr).label("ctr"),
        )
        .where(CampaignMetric.org_id == org_id)
        .where(CampaignMetric.level == "adset")
        .where(CampaignMetric.meta_campaign_id == campaign_id)
        .where(CampaignMetric.date >= date_from)
        .where(CampaignMetric.date <= date_to)
        .group_by(CampaignMetric.meta_adset_id)
        .order_by(func.coalesce(func.sum(CampaignMetric.spend), 0).desc())
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        AdSetSummary(
            meta_adset_id=row.meta_adset_id,
            meta_adset_name=row.meta_adset_name,
            status=row.status,
            spend=float(row.spend) if row.spend else 0.0,
            impressions=int(row.impressions) if row.impressions else 0,
            clicks=int(row.clicks) if row.clicks else 0,
            leads=int(row.leads) if row.leads else 0,
            link_clicks=int(row.link_clicks) if row.link_clicks else 0,
            video_views=int(row.video_views) if row.video_views else 0,
            cpc=float(row.cpc) if row.cpc is not None else None,
            cpm=float(row.cpm) if row.cpm is not None else None,
            ctr=float(row.ctr) if row.ctr is not None else None,
        )
        for row in rows
    ]


@router.get("/{campaign_id}/adsets/{adset_id}/ads", response_model=list[AdSummary])
async def list_ads(
    campaign_id: str,
    adset_id: str,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    date_from: date = Query(default_factory=_default_date_from),
    date_to: date = Query(default_factory=_default_date_to),
) -> list[AdSummary]:
    """List ads within an ad set with aggregated metrics."""
    query = (
        select(
            CampaignMetric.meta_ad_id,
            func.max(CampaignMetric.meta_ad_name).label("meta_ad_name"),
            func.max(CampaignMetric.status).label("status"),
            _coalesce_sum(CampaignMetric.spend).label("spend"),
            _coalesce_sum(CampaignMetric.impressions).label("impressions"),
            _coalesce_sum(CampaignMetric.clicks).label("clicks"),
            _coalesce_sum(CampaignMetric.leads).label("leads"),
            _coalesce_sum(CampaignMetric.link_clicks).label("link_clicks"),
            _coalesce_sum(CampaignMetric.video_views).label("video_views"),
            _coalesce_avg(CampaignMetric.cpc).label("cpc"),
            _coalesce_avg(CampaignMetric.cpm).label("cpm"),
            _coalesce_avg(CampaignMetric.ctr).label("ctr"),
        )
        .where(CampaignMetric.org_id == org_id)
        .where(CampaignMetric.level == "ad")
        .where(CampaignMetric.meta_campaign_id == campaign_id)
        .where(CampaignMetric.meta_adset_id == adset_id)
        .where(CampaignMetric.date >= date_from)
        .where(CampaignMetric.date <= date_to)
        .group_by(CampaignMetric.meta_ad_id)
        .order_by(func.coalesce(func.sum(CampaignMetric.spend), 0).desc())
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        AdSummary(
            meta_ad_id=row.meta_ad_id,
            meta_ad_name=row.meta_ad_name,
            status=row.status,
            spend=float(row.spend) if row.spend else 0.0,
            impressions=int(row.impressions) if row.impressions else 0,
            clicks=int(row.clicks) if row.clicks else 0,
            leads=int(row.leads) if row.leads else 0,
            link_clicks=int(row.link_clicks) if row.link_clicks else 0,
            video_views=int(row.video_views) if row.video_views else 0,
            cpc=float(row.cpc) if row.cpc is not None else None,
            cpm=float(row.cpm) if row.cpm is not None else None,
            ctr=float(row.ctr) if row.ctr is not None else None,
        )
        for row in rows
    ]


@router.get("/{campaign_id}/breakdowns", response_model=list[BreakdownItem])
async def get_campaign_breakdowns(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    type: str = Query(..., description='Breakdown type: "age_gender" or "platform"'),
    date_from: date = Query(default_factory=_default_date_from),
    date_to: date = Query(default_factory=_default_date_to),
) -> list[BreakdownItem]:
    """Get breakdown data (age_gender or platform) for a campaign."""
    if type not in ("age_gender", "platform"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Invalid breakdown type. Must be "age_gender" or "platform".',
        )

    query = (
        select(
            CampaignBreakdown.breakdown_key,
            _coalesce_sum(CampaignBreakdown.spend).label("spend"),
            _coalesce_sum(CampaignBreakdown.impressions).label("impressions"),
            _coalesce_sum(CampaignBreakdown.clicks).label("clicks"),
            _coalesce_sum(CampaignBreakdown.leads).label("leads"),
        )
        .where(CampaignBreakdown.org_id == org_id)
        .where(CampaignBreakdown.meta_campaign_id == campaign_id)
        .where(CampaignBreakdown.breakdown_type == type)
        .where(CampaignBreakdown.date >= date_from)
        .where(CampaignBreakdown.date <= date_to)
        .group_by(CampaignBreakdown.breakdown_key)
        .order_by(func.coalesce(func.sum(CampaignBreakdown.spend), 0).desc())
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        BreakdownItem(
            breakdown_key=row.breakdown_key,
            spend=float(row.spend) if row.spend else 0.0,
            impressions=int(row.impressions) if row.impressions else 0,
            clicks=int(row.clicks) if row.clicks else 0,
            leads=int(row.leads) if row.leads else 0,
        )
        for row in rows
    ]
