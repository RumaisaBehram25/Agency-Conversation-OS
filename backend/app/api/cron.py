"""
Attora — Cron Job API Routes

POST /api/cron/stale-conversations  — Mark stale conversations
POST /api/cron/daily-digest         — Aggregate daily analytics

Protected by CRON_SECRET header — not accessible to regular users.
"""

from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.jobs.ad_spend_sync import sync_ad_spend
from app.jobs.daily_digest import aggregate_daily_analytics
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
) -> dict:
    """
    Pull ad spend from Meta Marketing API and upsert into daily_analytics.

    Fetches the last N days of spend data for all orgs with a configured
    meta_ad_account_id. Protected by CRON_SECRET header.
    """
    return await sync_ad_spend(db, days_back=days_back)
