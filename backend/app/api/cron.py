"""
Attora — Cron Job API Routes

POST /api/cron/stale-conversations  — Mark stale conversations
POST /api/cron/daily-digest         — Aggregate daily analytics
POST /api/cron/ad-spend-sync        — Sync ad spend and dual-write campaign facts
POST /api/cron/export-ai-usage      — Export AI usage events to OLAP
POST /api/cron/archive-messages     — Shadow-archive old messages to OLAP
POST /api/cron/check-olap-parity    — Compare PostgreSQL facts vs exported Parquet
POST /api/cron/hyros-sync           — Sync Hyros purchases onto subscribers (org Hyros keys; scheduler optional every 3h via HYROS_SYNC_SCHEDULER_*)

Protected by CRON_SECRET header — not accessible to regular users.
"""

from datetime import date
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.jobs.ad_spend_sync import sync_ad_spend
from app.jobs.daily_digest import aggregate_daily_analytics
from app.jobs.hyros_sync import sync_hyros_purchases
from app.services.follow_up_engine import dispatch_follow_ups
from app.jobs.olap_exports import (
    archive_messages_to_olap,
    archive_messages_delta_to_olap,
    export_ai_usage_events_to_olap,
    export_ai_usage_events_delta_to_olap,
    export_daily_analytics_delta_to_olap,
    run_olap_parity_check,
    run_reporting_parity_check,
)
from app.jobs.stale_conversations import mark_stale_conversations

router = APIRouter()


async def verify_cron_secret(
    x_cron_secret: str = Header(..., description="Cron job authentication secret"),
) -> None:
    """Verify the CRON_SECRET header matches the configured secret."""
    if x_cron_secret != settings.cron_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid cron secret",
        )


@router.post("/stale-conversations")
async def cron_stale_conversations(
    _: None = Depends(verify_cron_secret),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Mark active conversations with no activity for 24+ hours as stale.

    Protected by CRON_SECRET header.
    """
    return await mark_stale_conversations(db)


@router.post("/daily-digest")
async def cron_daily_digest(
    _: None = Depends(verify_cron_secret),
    db: AsyncSession = Depends(get_db),
    target_date: date | None = Query(None, description="Date to aggregate (defaults to yesterday)"),
) -> dict:
    """
    Aggregate raw conversation/message/conversion data into daily_analytics.

    Protected by CRON_SECRET header. Defaults to aggregating yesterday's data.
    """
    return await aggregate_daily_analytics(db, target_date)


@router.post("/ad-spend-sync")
async def cron_ad_spend_sync(
    _: None = Depends(verify_cron_secret),
    db: AsyncSession = Depends(get_db),
    days_back: int = Query(7, description="Number of days to sync (default 7)"),
    granular: bool = Query(True, description="Pull campaign/adset/ad level metrics and breakdowns (default True)"),
) -> dict:
    """
    Pull ad spend from Meta Marketing API and upsert into daily_analytics.

    When granular=True (default), also pulls campaign/adset/ad level metrics
    and demographic breakdowns into campaign_metrics and campaign_breakdowns.

    Fetches the last N days of spend data for all orgs with a configured
    meta_ad_account_id. Protected by CRON_SECRET header.
    """
    return await sync_ad_spend(db, days_back=days_back, granular=granular)


@router.post("/export-ai-usage")
async def cron_export_ai_usage(
    _: None = Depends(verify_cron_secret),
    db: AsyncSession = Depends(get_db),
    target_date: date | None = Query(None, description="Date to export (defaults to yesterday)"),
    org_id: uuid.UUID | None = Query(None, description="Optional org filter"),
    use_checkpoint: bool = Query(False, description="Use checkpoint metadata for delta export"),
) -> dict:
    """Export AI usage events to OLAP object storage."""
    if use_checkpoint:
        return await export_ai_usage_events_delta_to_olap(db, org_id=org_id)
    return await export_ai_usage_events_to_olap(db, target_date=target_date, org_id=org_id)


@router.post("/export-daily-analytics")
async def cron_export_daily_analytics(
    _: None = Depends(verify_cron_secret),
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID | None = Query(None, description="Optional org filter"),
) -> dict:
    """Export daily_analytics rows to OLAP using checkpoint metadata."""
    return await export_daily_analytics_delta_to_olap(db, org_id=org_id)


@router.post("/archive-messages")
async def cron_archive_messages(
    _: None = Depends(verify_cron_secret),
    db: AsyncSession = Depends(get_db),
    older_than_days: int = Query(settings.olap_message_hot_retention_days, ge=1),
    limit: int = Query(settings.olap_export_batch_size, ge=1),
    org_id: uuid.UUID | None = Query(None, description="Optional org filter"),
    use_checkpoint: bool = Query(False, description="Use checkpoint metadata for delta archiving"),
) -> dict:
    """Shadow-archive older messages to OLAP without deleting PostgreSQL rows."""
    if use_checkpoint:
        return await archive_messages_delta_to_olap(
            db,
            older_than_days=older_than_days,
            org_id=org_id,
        )
    return await archive_messages_to_olap(
        db,
        older_than_days=older_than_days,
        limit=limit,
        org_id=org_id,
    )


@router.post("/check-olap-parity")
async def cron_check_olap_parity(
    _: None = Depends(verify_cron_secret),
    db: AsyncSession = Depends(get_db),
    datasets: str = Query(
        "campaign_metrics,campaign_breakdowns,ai_usage_events",
        description="Comma-separated dataset names to compare",
    ),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    org_id: uuid.UUID | None = Query(None, description="Optional org filter"),
    older_than_days: int | None = Query(None, ge=1),
) -> dict:
    """Compare PostgreSQL datasets against exported Parquet partitions."""
    dataset_names = [value.strip() for value in datasets.split(",") if value.strip()]
    return await run_olap_parity_check(
        db,
        datasets=dataset_names,
        date_from=date_from,
        date_to=date_to,
        org_id=org_id,
        older_than_days=older_than_days,
    )


@router.post("/check-reporting-parity")
async def cron_check_reporting_parity(
    _: None = Depends(verify_cron_secret),
    db: AsyncSession = Depends(get_db),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    org_ids: str | None = Query(None, description="Comma-separated org UUIDs"),
) -> dict:
    """Compare reporting-facing PostgreSQL aggregates to OLAP exports by org/date range."""
    parsed_org_ids = [uuid.UUID(value.strip()) for value in org_ids.split(",")] if org_ids else None
    return await run_reporting_parity_check(
        db,
        org_ids=parsed_org_ids,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/hyros-sync")
async def cron_hyros_sync(
    _: None = Depends(verify_cron_secret),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Pull Hyros purchases and match against subscriber name + utm_campaign."""
    return await sync_hyros_purchases(db)


@router.post("/follow-ups")
async def cron_follow_ups(
    _: None = Depends(verify_cron_secret),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Dispatch due follow-up nudges to silent, unbought subscribers via
    ManyChat's open outbound flow. Recommended cadence: every 15 minutes.
    """
    summary = await dispatch_follow_ups(db)
    await db.commit()
    return summary
