"""Self-hosted scheduler for phase 1 OLAP maintenance jobs."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.jobs.olap_exports import (
    archive_messages_to_olap,
    archive_messages_delta_to_olap,
    export_ai_usage_events_to_olap,
    export_ai_usage_events_delta_to_olap,
    export_campaign_facts_to_olap,
    export_daily_analytics_to_olap,
    export_daily_analytics_delta_to_olap,
    run_olap_parity_check,
    run_reporting_parity_check,
)
from app.models.ai_usage_event import AIUsageEvent
from app.models.analytics import DailyAnalytics
from app.models.campaign_metrics import CampaignBreakdown, CampaignMetric
from app.models.conversation import Conversation
from app.models.message import Message
from app.jobs.email_queue_processor import process_email_queue
from app.jobs.hyros_sync import sync_hyros_purchases
from app.services.follow_up_engine import dispatch_follow_ups

logger = logging.getLogger("attora.jobs.scheduler")

OlapJobName = Literal[
    "export_campaign_facts",
    "export_daily_analytics",
    "export_ai_usage",
    "archive_messages",
    "check_olap_parity",
    "check_reporting_parity",
]


async def run_olap_job(
    session: AsyncSession,
    job_name: OlapJobName,
    *,
    org_id: uuid.UUID | None = None,
    org_ids: list[uuid.UUID] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    target_date: date | None = None,
    older_than_days: int | None = None,
    limit: int | None = None,
    delta_days: int | None = None,
    use_checkpoint: bool = True,
    export_all: bool = False,
) -> dict:
    """Run a supported OLAP maintenance job through a shared interface."""
    if job_name == "export_campaign_facts":
        if export_all:
            resolved_window = await _resolve_export_all_date_window(
                session,
                dataset_name="campaign_facts",
                org_id=org_id,
            )
            if resolved_window is None:
                return {"skipped": True, "reason": "no campaign fact source data found"}
            effective_date_from, effective_date_to = resolved_window
        else:
            effective_date_from, effective_date_to = _resolve_date_window(
                date_from=date_from,
                date_to=date_to,
                delta_days=delta_days,
            )
        return await export_campaign_facts_to_olap(
            session,
            org_id=org_id,
            date_from=effective_date_from,
            date_to=effective_date_to,
        )

    if job_name == "export_daily_analytics":
        if export_all:
            resolved_window = await _resolve_export_all_date_window(
                session,
                dataset_name="daily_analytics",
                org_id=org_id,
            )
            if resolved_window is None:
                return {"skipped": True, "reason": "no daily analytics source data found"}
            effective_date_from, effective_date_to = resolved_window
            return await export_daily_analytics_to_olap(
                session,
                org_id=org_id,
                date_from=effective_date_from,
                date_to=effective_date_to,
            )

        if use_checkpoint:
            return await export_daily_analytics_delta_to_olap(
                session,
                org_id=org_id,
                delta_days=delta_days,
            )

        effective_date_from, effective_date_to = _resolve_date_window(
            date_from=date_from,
            date_to=date_to,
            delta_days=delta_days,
        )
        return await export_daily_analytics_to_olap(
            session,
            org_id=org_id,
            date_from=effective_date_from,
            date_to=effective_date_to,
        )

    if job_name == "export_ai_usage":
        if export_all:
            resolved_window = await _resolve_export_all_datetime_window(
                session,
                dataset_name="ai_usage_events",
                org_id=org_id,
            )
            if resolved_window is None:
                return {"skipped": True, "reason": "no ai usage source data found"}
            start_at, end_at = resolved_window
            return await export_ai_usage_events_to_olap(
                session,
                org_id=org_id,
                start_at=start_at,
                end_at=end_at,
            )

        if use_checkpoint:
            return await export_ai_usage_events_delta_to_olap(
                session,
                org_id=org_id,
                delta_days=delta_days,
            )

        start_at, end_at = _resolve_datetime_window(
            target_date=target_date,
            date_from=date_from,
            date_to=date_to,
            delta_days=delta_days,
        )
        return await export_ai_usage_events_to_olap(
            session,
            org_id=org_id,
            target_date=target_date,
            start_at=start_at,
            end_at=end_at,
        )

    if job_name == "archive_messages":
        retention_days = older_than_days or settings.olap_message_hot_retention_days
        if export_all:
            resolved_window = await _resolve_archive_export_all_window(
                session,
                older_than_days=retention_days,
                org_id=org_id,
            )
            if resolved_window is None:
                return {"skipped": True, "reason": "no archive-eligible messages found"}
            start_at, end_at = resolved_window
            return await archive_messages_to_olap(
                session,
                older_than_days=retention_days,
                limit=limit or settings.olap_export_batch_size,
                org_id=org_id,
                start_at=start_at,
                end_at=end_at,
            )

        if use_checkpoint:
            return await archive_messages_delta_to_olap(
                session,
                older_than_days=retention_days,
                org_id=org_id,
                delta_days=delta_days,
            )

        start_at, end_at = _resolve_datetime_window(
            target_date=target_date,
            date_from=date_from,
            date_to=date_to,
            delta_days=delta_days,
        )
        return await archive_messages_to_olap(
            session,
            older_than_days=retention_days,
            limit=limit or settings.olap_export_batch_size,
            org_id=org_id,
            start_at=start_at,
            end_at=end_at,
        )

    if job_name == "check_olap_parity":
        return await run_olap_parity_check(
            session,
            datasets=["campaign_metrics", "campaign_breakdowns", "daily_analytics", "ai_usage_events"],
            org_id=org_id,
            date_from=date_from,
            date_to=date_to,
            older_than_days=older_than_days,
        )

    if job_name == "check_reporting_parity":
        return await run_reporting_parity_check(
            session,
            org_ids=org_ids,
            date_from=date_from,
            date_to=date_to,
        )

    raise ValueError(f"Unsupported OLAP job: {job_name}")


def _resolve_date_window(
    *,
    date_from: date | None,
    date_to: date | None,
    delta_days: int | None,
) -> tuple[date, date]:
    window_days = delta_days or settings.olap_delta_window_days
    effective_date_to = date_to or date.today()
    effective_date_from = date_from or (effective_date_to - timedelta(days=window_days - 1))
    if effective_date_from > effective_date_to:
        raise ValueError("date_from must be on or before date_to")
    return effective_date_from, effective_date_to


def _resolve_datetime_window(
    *,
    target_date: date | None,
    date_from: date | None,
    date_to: date | None,
    delta_days: int | None,
) -> tuple[datetime | None, datetime | None]:
    if target_date is not None:
        return (
            datetime.combine(target_date, time.min, tzinfo=timezone.utc),
            datetime.combine(target_date, time.max, tzinfo=timezone.utc),
        )

    effective_date_from, effective_date_to = _resolve_date_window(
        date_from=date_from,
        date_to=date_to,
        delta_days=delta_days,
    )
    return (
        datetime.combine(effective_date_from, time.min, tzinfo=timezone.utc),
        datetime.combine(effective_date_to, time.max, tzinfo=timezone.utc),
    )


async def _resolve_export_all_date_window(
    session: AsyncSession,
    *,
    dataset_name: Literal["campaign_facts", "daily_analytics"],
    org_id: uuid.UUID | None,
) -> tuple[date, date] | None:
    if dataset_name == "daily_analytics":
        query = select(func.min(DailyAnalytics.date), func.max(DailyAnalytics.date))
        if org_id is not None:
            query = query.where(DailyAnalytics.org_id == org_id)
        result = await session.execute(query)
        date_from, date_to = result.one()
        return (date_from, date_to) if date_from and date_to else None

    metric_query = select(func.min(CampaignMetric.date), func.max(CampaignMetric.date))
    breakdown_query = select(func.min(CampaignBreakdown.date), func.max(CampaignBreakdown.date))
    if org_id is not None:
        metric_query = metric_query.where(CampaignMetric.org_id == org_id)
        breakdown_query = breakdown_query.where(CampaignBreakdown.org_id == org_id)

    metric_result = await session.execute(metric_query)
    breakdown_result = await session.execute(breakdown_query)
    metric_min, metric_max = metric_result.one()
    breakdown_min, breakdown_max = breakdown_result.one()

    minimums = [value for value in (metric_min, breakdown_min) if value is not None]
    maximums = [value for value in (metric_max, breakdown_max) if value is not None]
    if not minimums or not maximums:
        return None
    return min(minimums), max(maximums)


async def _resolve_export_all_datetime_window(
    session: AsyncSession,
    *,
    dataset_name: Literal["ai_usage_events"],
    org_id: uuid.UUID | None,
) -> tuple[datetime, datetime] | None:
    if dataset_name != "ai_usage_events":
        raise ValueError(f"Unsupported export-all datetime dataset: {dataset_name}")

    query = select(func.min(AIUsageEvent.created_at), func.max(AIUsageEvent.created_at))
    if org_id is not None:
        query = query.where(AIUsageEvent.org_id == org_id)
    result = await session.execute(query)
    start_at, end_at = result.one()
    return (start_at, end_at) if start_at and end_at else None


async def _resolve_archive_export_all_window(
    session: AsyncSession,
    *,
    older_than_days: int,
    org_id: uuid.UUID | None,
) -> tuple[datetime, datetime] | None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    query = (
        select(func.min(Message.created_at), func.max(Message.created_at))
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.created_at < cutoff)
    )
    if org_id is not None:
        query = query.where(Conversation.org_id == org_id)
    result = await session.execute(query)
    start_at, end_at = result.one()
    return (start_at, end_at) if start_at and end_at else None


async def _run_export_daily_analytics() -> None:
    async with async_session_factory() as session:
        result = await run_olap_job(session, "export_daily_analytics")
        await session.commit()
        logger.info("Scheduled daily_analytics export result: %s", result)


async def _run_export_ai_usage() -> None:
    async with async_session_factory() as session:
        result = await run_olap_job(session, "export_ai_usage")
        await session.commit()
        logger.info("Scheduled ai_usage_events export result: %s", result)


async def _run_archive_messages() -> None:
    async with async_session_factory() as session:
        result = await run_olap_job(session, "archive_messages")
        await session.commit()
        logger.info("Scheduled archived_messages export result: %s", result)


async def _run_hyros_sync_dispatch() -> None:
    async with async_session_factory() as session:
        result = await sync_hyros_purchases(session)
        await session.commit()
        logger.info("Scheduled Hyros purchase sync result: %s", result)


async def _run_follow_up_dispatch() -> None:
    async with async_session_factory() as session:
        result = await dispatch_follow_ups(session)
        await session.commit()
        logger.info("Scheduled follow-up dispatch result: %s", result)


async def _run_email_queue_processor() -> None:
    async with async_session_factory() as session:
        result = await process_email_queue(session)
        await session.commit()
        logger.info("Scheduled email queue processor result: %s", result)


def build_follow_up_scheduler() -> AsyncIOScheduler:
    """
    APScheduler for follow-up dispatch and the email queue processor.

    Used by the FastAPI app lifespan. OLAP / Hyros cron jobs stay in
    ``python -m app.jobs.scheduler`` (see ``build_scheduler``).
    """
    scheduler = AsyncIOScheduler(timezone=settings.olap_scheduler_timezone)
    scheduler.add_job(
        _run_follow_up_dispatch,
        CronTrigger.from_crontab(settings.follow_up_scheduler_cron, timezone=settings.olap_scheduler_timezone),
        id="follow-up-dispatch",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        _run_email_queue_processor,
        CronTrigger.from_crontab("*/15 * * * *", timezone=settings.olap_scheduler_timezone),
        id="email-queue-processor",
        replace_existing=True,
        max_instances=1,
    )
    return scheduler


async def _run_parity() -> None:
    org_ids = [uuid.UUID(value) for value in settings.olap_scheduler_parity_org_ids_list]
    async with async_session_factory() as session:
        low_level = await run_olap_job(
            session,
            "check_olap_parity",
            org_id=org_ids[0] if len(org_ids) == 1 else None,
        )
        reporting = await run_olap_job(
            session,
            "check_reporting_parity",
            org_ids=org_ids or None,
        )
        await session.commit()
        logger.info("Scheduled low-level parity result: %s", low_level)
        logger.info("Scheduled reporting parity result: %s", reporting)


def build_scheduler() -> AsyncIOScheduler:
    """Create APScheduler jobs for OLAP maintenance and Hyros purchase sync (standalone container).

    Follow-up dispatch is registered separately via ``build_follow_up_scheduler`` in the API process.
    """
    scheduler = AsyncIOScheduler(timezone=settings.olap_scheduler_timezone)
    if settings.olap_scheduler_enabled:
        scheduler.add_job(_run_export_daily_analytics, CronTrigger.from_crontab(settings.olap_scheduler_export_daily_analytics_cron, timezone=settings.olap_scheduler_timezone), id="olap-export-daily-analytics", replace_existing=True, max_instances=1)
        scheduler.add_job(_run_export_ai_usage, CronTrigger.from_crontab(settings.olap_scheduler_export_ai_usage_cron, timezone=settings.olap_scheduler_timezone), id="olap-export-ai-usage", replace_existing=True, max_instances=1)
        scheduler.add_job(_run_archive_messages, CronTrigger.from_crontab(settings.olap_scheduler_archive_messages_cron, timezone=settings.olap_scheduler_timezone), id="olap-archive-messages", replace_existing=True, max_instances=1)
        scheduler.add_job(_run_parity, CronTrigger.from_crontab(settings.olap_scheduler_parity_cron, timezone=settings.olap_scheduler_timezone), id="olap-parity", replace_existing=True, max_instances=1)
    if settings.hyros_sync_scheduler_enabled:
        scheduler.add_job(
            _run_hyros_sync_dispatch,
            CronTrigger.from_crontab(settings.hyros_sync_scheduler_cron, timezone=settings.olap_scheduler_timezone),
            id="hyros-purchase-sync",
            replace_existing=True,
            max_instances=1,
        )
    return scheduler


async def main() -> None:
    """Run the scheduler loop until the process is stopped."""
    if not settings.olap_scheduler_enabled and not settings.hyros_sync_scheduler_enabled:
        logger.info("OLAP and Hyros schedulers are both disabled; exiting")
        return

    scheduler = build_scheduler()
    if not scheduler.get_jobs():
        logger.info("Scheduler has no jobs configured; exiting")
        return

    scheduler.start()
    logger.info(
        "Scheduler started timezone=%s jobs=%s",
        settings.olap_scheduler_timezone,
        [job.id for job in scheduler.get_jobs()],
    )
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    asyncio.run(main())