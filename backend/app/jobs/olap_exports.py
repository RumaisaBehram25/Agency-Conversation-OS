"""Phase 1 OLAP export, archive, checkpoint, and parity-check jobs."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.ai_usage_event import AIUsageEvent
from app.models.analytics import DailyAnalytics
from app.models.campaign_metrics import CampaignBreakdown, CampaignMetric
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.organization import Organization
from app.olap import OLAP_DATASETS, get_object_storage_adapter
from app.olap.checkpoints import load_checkpoint, save_checkpoint
from app.olap.parquet import records_from_parquet_bytes, upsert_dataset_records
from app.services.olap_service import force_sync_tables

logger = logging.getLogger("attora.jobs.olap_exports")

_PARITY_DATASETS = {
    "campaign_metrics",
    "campaign_breakdowns",
    "daily_analytics",
    "ai_usage_events",
    "archived_messages",
}


async def export_campaign_facts_to_olap(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    """Export campaign metrics and breakdowns for an org/date range to OLAP storage."""
    storage = get_object_storage_adapter()
    if not settings.olap_storage_enabled:
        return _skipped_summary(storage.provider)

    metric_rows = await _load_campaign_metric_records(db, org_id, date_from, date_to)
    breakdown_rows = await _load_campaign_breakdown_records(db, org_id, date_from, date_to)
    aggregate_rows = _build_campaign_metric_agg_records(metric_rows)
    metric_result = upsert_dataset_records(storage, OLAP_DATASETS["campaign_metrics"], metric_rows)
    breakdown_result = upsert_dataset_records(storage, OLAP_DATASETS["campaign_breakdowns"], breakdown_rows)
    aggregate_result = upsert_dataset_records(storage, OLAP_DATASETS["campaign_metrics_agg"], aggregate_rows)
    if settings.olap_query_enabled:
        await force_sync_tables(["campaign_metrics", "campaign_breakdowns", "campaign_metrics_agg"])
    return {
        "storage_provider": storage.provider,
        "campaign_metrics_rows": metric_result["rows_written"],
        "campaign_breakdowns_rows": breakdown_result["rows_written"],
        "campaign_aggregate_rows": aggregate_result["rows_written"],
        "aggregate_objects_written": aggregate_result["objects_written"],
        "objects_written": metric_result["objects_written"] + breakdown_result["objects_written"] + aggregate_result["objects_written"],
        "skipped": False,
    }


async def export_daily_analytics_to_olap(
    db: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    org_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Export serving-layer daily analytics rows to OLAP storage."""
    storage = get_object_storage_adapter()
    if not settings.olap_storage_enabled:
        return _skipped_summary(storage.provider)

    rows = await _load_daily_analytics_records(db, org_id, date_from, date_to)
    result = upsert_dataset_records(storage, OLAP_DATASETS["daily_analytics"], rows)
    compact_result = upsert_dataset_records(storage, OLAP_DATASETS["daily_analytics_compact"], rows)
    if settings.olap_query_enabled:
        await force_sync_tables(["daily_analytics", "daily_analytics_compact"])
    return {
        "storage_provider": storage.provider,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "rows_exported": result["rows_written"],
        "objects_written": result["objects_written"] + compact_result["objects_written"],
        "compact_objects_written": compact_result["objects_written"],
        "skipped": False,
    }


async def export_daily_analytics_delta_to_olap(
    db: AsyncSession,
    *,
    org_id: uuid.UUID | None = None,
    delta_days: int | None = None,
) -> dict[str, Any]:
    """Export daily_analytics incrementally using checkpoint metadata."""
    storage = get_object_storage_adapter()
    if not settings.olap_storage_enabled:
        return _skipped_summary(storage.provider)

    window_days = delta_days or settings.olap_delta_window_days
    today = date.today()
    scope = _scope_key(org_id)
    checkpoint = load_checkpoint(storage, job_name="daily-analytics-export", scope=scope)
    if checkpoint and checkpoint.get("cursor_date"):
        start_date = date.fromisoformat(checkpoint["cursor_date"]) + timedelta(days=1)
    else:
        start_date = today - timedelta(days=window_days - 1)
    end_date = min(start_date + timedelta(days=window_days - 1), today)

    if start_date > end_date:
        return {
            "storage_provider": storage.provider,
            "date_from": start_date.isoformat(),
            "date_to": end_date.isoformat(),
            "rows_exported": 0,
            "objects_written": 0,
            "skipped": True,
            "reason": "checkpoint is already up to date",
        }

    result = await export_daily_analytics_to_olap(db, date_from=start_date, date_to=end_date, org_id=org_id)
    save_checkpoint(
        storage,
        job_name="daily-analytics-export",
        scope=scope,
        payload={
            "cursor_date": end_date.isoformat(),
            "window_start": start_date.isoformat(),
            "window_end": end_date.isoformat(),
            "rows_exported": result["rows_exported"],
        },
    )
    result["checkpoint_scope"] = scope
    return result


async def export_ai_usage_events_to_olap(
    db: AsyncSession,
    target_date: date | None = None,
    org_id: uuid.UUID | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> dict[str, Any]:
    """Export AI usage events into Parquet partitions."""
    storage = get_object_storage_adapter()
    if not settings.olap_storage_enabled:
        return _skipped_summary(storage.provider)

    if target_date is not None:
        start_at = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
        end_at = datetime.combine(target_date, time.max, tzinfo=timezone.utc)
    elif start_at is None or end_at is None:
        export_date = date.today() - timedelta(days=1)
        start_at = datetime.combine(export_date, time.min, tzinfo=timezone.utc)
        end_at = datetime.combine(export_date, time.max, tzinfo=timezone.utc)

    rows = await _load_ai_usage_event_records(db, start_at=start_at, end_at=end_at, org_id=org_id)
    result = upsert_dataset_records(storage, OLAP_DATASETS["ai_usage_events"], rows)
    aggregate_rows = _build_ai_usage_event_agg_records(rows)
    aggregate_result = upsert_dataset_records(storage, OLAP_DATASETS["ai_usage_events_agg"], aggregate_rows)
    if settings.olap_query_enabled:
        await force_sync_tables(["ai_usage_events", "ai_usage_events_agg"])
    return {
        "storage_provider": storage.provider,
        "window_start": start_at.isoformat(),
        "window_end": end_at.isoformat(),
        "rows_exported": result["rows_written"],
        "aggregate_rows_exported": aggregate_result["rows_written"],
        "objects_written": result["objects_written"] + aggregate_result["objects_written"],
        "skipped": False,
    }


async def export_ai_usage_events_delta_to_olap(
    db: AsyncSession,
    *,
    org_id: uuid.UUID | None = None,
    delta_days: int | None = None,
) -> dict[str, Any]:
    """Export AI usage events incrementally using checkpoint metadata."""
    storage = get_object_storage_adapter()
    if not settings.olap_storage_enabled:
        return _skipped_summary(storage.provider)

    window_days = delta_days or settings.olap_delta_window_days
    upper_bound = datetime.now(timezone.utc)
    scope = _scope_key(org_id)
    checkpoint = load_checkpoint(storage, job_name="ai-usage-export", scope=scope)
    if checkpoint and checkpoint.get("cursor_at"):
        start_at = datetime.fromisoformat(checkpoint["cursor_at"])
        end_at = min(start_at + timedelta(days=window_days), upper_bound)
    else:
        end_at = upper_bound
        start_at = end_at - timedelta(days=window_days)

    if start_at >= end_at:
        return {
            "storage_provider": storage.provider,
            "window_start": start_at.isoformat(),
            "window_end": end_at.isoformat(),
            "rows_exported": 0,
            "objects_written": 0,
            "skipped": True,
            "reason": "checkpoint is already up to date",
        }

    result = await export_ai_usage_events_to_olap(db, org_id=org_id, start_at=start_at, end_at=end_at)
    save_checkpoint(
        storage,
        job_name="ai-usage-export",
        scope=scope,
        payload={
            "cursor_at": end_at.isoformat(),
            "window_start": start_at.isoformat(),
            "window_end": end_at.isoformat(),
            "rows_exported": result["rows_exported"],
        },
    )
    result["checkpoint_scope"] = scope
    return result


async def archive_messages_to_olap(
    db: AsyncSession,
    *,
    older_than_days: int | None = None,
    limit: int | None = None,
    org_id: uuid.UUID | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> dict[str, Any]:
    """Shadow-archive older messages to OLAP without deleting PostgreSQL rows."""
    storage = get_object_storage_adapter()
    if not settings.olap_storage_enabled:
        return _skipped_summary(storage.provider)

    retention_days = older_than_days or settings.olap_message_hot_retention_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    query_end = min(end_at or cutoff, cutoff)
    rows = await _load_archived_message_records(
        db,
        cutoff=cutoff,
        limit=limit,
        org_id=org_id,
        start_at=start_at,
        end_at=query_end,
    )
    result = upsert_dataset_records(storage, OLAP_DATASETS["archived_messages"], rows)
    aggregate_rows = _build_archived_message_agg_records(rows)
    aggregate_result = upsert_dataset_records(storage, OLAP_DATASETS["archived_messages_agg"], aggregate_rows)
    if settings.olap_query_enabled:
        await force_sync_tables(["archived_messages", "archived_messages_agg"])
    return {
        "storage_provider": storage.provider,
        "cutoff": cutoff.isoformat(),
        "window_start": start_at.isoformat() if start_at else None,
        "window_end": query_end.isoformat() if query_end else None,
        "rows_archived": result["rows_written"],
        "aggregate_rows_archived": aggregate_result["rows_written"],
        "objects_written": result["objects_written"] + aggregate_result["objects_written"],
        "rows_deleted": 0,
        "archive_mode": "shadow",
        "skipped": False,
    }


async def archive_messages_delta_to_olap(
    db: AsyncSession,
    *,
    older_than_days: int | None = None,
    org_id: uuid.UUID | None = None,
    delta_days: int | None = None,
) -> dict[str, Any]:
    """Archive messages incrementally using checkpoint metadata."""
    storage = get_object_storage_adapter()
    if not settings.olap_storage_enabled:
        return _skipped_summary(storage.provider)

    retention_days = older_than_days or settings.olap_message_hot_retention_days
    window_days = delta_days or settings.olap_delta_window_days
    eligible_upper_bound = datetime.now(timezone.utc) - timedelta(days=retention_days)
    scope = _scope_key(org_id)
    checkpoint = load_checkpoint(storage, job_name="message-archive", scope=scope)
    if checkpoint and checkpoint.get("cursor_at"):
        start_at = datetime.fromisoformat(checkpoint["cursor_at"])
    else:
        start_at = await _find_earliest_eligible_message_created_at(db, eligible_upper_bound, org_id)
        if start_at is None:
            return {
                "storage_provider": storage.provider,
                "rows_archived": 0,
                "objects_written": 0,
                "rows_deleted": 0,
                "skipped": True,
                "reason": "no eligible messages found",
            }
    end_at = min(start_at + timedelta(days=window_days), eligible_upper_bound)

    if start_at >= end_at:
        return {
            "storage_provider": storage.provider,
            "rows_archived": 0,
            "objects_written": 0,
            "rows_deleted": 0,
            "skipped": True,
            "reason": "checkpoint is already up to date",
        }

    result = await archive_messages_to_olap(
        db,
        older_than_days=retention_days,
        limit=None,
        org_id=org_id,
        start_at=start_at,
        end_at=end_at,
    )
    save_checkpoint(
        storage,
        job_name="message-archive",
        scope=scope,
        payload={
            "cursor_at": end_at.isoformat(),
            "window_start": start_at.isoformat(),
            "window_end": end_at.isoformat(),
            "rows_archived": result["rows_archived"],
        },
    )
    result["checkpoint_scope"] = scope
    return result


async def run_olap_parity_check(
    db: AsyncSession,
    *,
    datasets: list[str],
    date_from: date | None = None,
    date_to: date | None = None,
    org_id: uuid.UUID | None = None,
    older_than_days: int | None = None,
) -> dict[str, Any]:
    """Compare PostgreSQL source rows against exported Parquet datasets."""
    storage = get_object_storage_adapter()
    requested = datasets or ["campaign_metrics", "campaign_breakdowns", "daily_analytics", "ai_usage_events"]

    invalid = sorted(set(requested) - _PARITY_DATASETS)
    if invalid:
        raise ValueError(f"Unsupported parity dataset(s): {', '.join(invalid)}")

    if not settings.olap_storage_enabled:
        return {
            "storage_provider": storage.provider,
            "datasets": {},
            "matched": False,
            "message": "OLAP storage is disabled",
        }

    results: dict[str, Any] = {}
    all_match = True
    for dataset_name in requested:
        source_records = await _source_records_for_dataset(
            db,
            dataset_name,
            date_from=date_from,
            date_to=date_to,
            org_id=org_id,
            older_than_days=older_than_days,
        )
        exported_records = _load_exported_records(
            storage,
            dataset_name,
            org_id=org_id,
            date_from=date_from,
            date_to=date_to,
        )
        source_summary = _summarize_dataset(dataset_name, source_records)
        exported_summary = _summarize_dataset(dataset_name, exported_records)
        matches = source_summary == exported_summary
        all_match = all_match and matches
        results[dataset_name] = {
            "postgres": source_summary,
            "olap": exported_summary,
            "matches": matches,
        }

    return {
        "storage_provider": storage.provider,
        "datasets": results,
        "matched": all_match,
    }


async def run_reporting_parity_check(
    db: AsyncSession,
    *,
    org_ids: list[uuid.UUID] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """Compare reporting-facing PostgreSQL aggregates with OLAP exports by org/date range."""
    storage = get_object_storage_adapter()
    if not settings.olap_storage_enabled:
        return {
            "storage_provider": storage.provider,
            "matched": False,
            "message": "OLAP storage is disabled",
            "orgs": [],
        }

    effective_date_to = date_to or date.today()
    effective_date_from = date_from or (effective_date_to - timedelta(days=settings.olap_delta_window_days - 1))
    target_org_ids = org_ids or await _load_all_org_ids(db)

    org_results = []
    overall_match = True
    for current_org_id in target_org_ids:
        pg_daily = await _load_daily_analytics_records(db, current_org_id, effective_date_from, effective_date_to)
        olap_daily = _load_exported_records(storage, "daily_analytics", org_id=current_org_id, date_from=effective_date_from, date_to=effective_date_to)
        pg_campaign = await _load_campaign_metric_records(db, current_org_id, effective_date_from, effective_date_to)
        olap_campaign = _load_exported_records(storage, "campaign_metrics", org_id=current_org_id, date_from=effective_date_from, date_to=effective_date_to)
        pg_breakdowns = await _load_campaign_breakdown_records(db, current_org_id, effective_date_from, effective_date_to)
        olap_breakdowns = _load_exported_records(storage, "campaign_breakdowns", org_id=current_org_id, date_from=effective_date_from, date_to=effective_date_to)

        analytics_pg = _summarize_reporting_daily_analytics(pg_daily)
        analytics_olap = _summarize_reporting_daily_analytics(olap_daily)
        campaign_pg = _summarize_campaign_reporting(pg_campaign, pg_breakdowns)
        campaign_olap = _summarize_campaign_reporting(olap_campaign, olap_breakdowns)

        analytics_match = analytics_pg == analytics_olap
        campaign_match = campaign_pg == campaign_olap
        org_match = analytics_match and campaign_match
        overall_match = overall_match and org_match

        org_results.append({
            "org_id": str(current_org_id),
            "date_from": effective_date_from.isoformat(),
            "date_to": effective_date_to.isoformat(),
            "analytics_serving": {
                "postgres": analytics_pg,
                "olap": analytics_olap,
                "matches": analytics_match,
            },
            "campaign_reporting": {
                "postgres": campaign_pg,
                "olap": campaign_olap,
                "matches": campaign_match,
            },
        })

    return {
        "storage_provider": storage.provider,
        "matched": overall_match,
        "orgs": org_results,
    }


def _skipped_summary(storage_provider: str) -> dict[str, Any]:
    return {
        "storage_provider": storage_provider,
        "rows_exported": 0,
        "objects_written": 0,
        "skipped": True,
    }


async def _source_records_for_dataset(
    db: AsyncSession,
    dataset_name: str,
    *,
    date_from: date | None,
    date_to: date | None,
    org_id: uuid.UUID | None,
    older_than_days: int | None,
) -> list[dict[str, Any]]:
    if dataset_name == "campaign_metrics":
        return await _load_campaign_metric_records(db, org_id, date_from, date_to)
    if dataset_name == "campaign_breakdowns":
        return await _load_campaign_breakdown_records(db, org_id, date_from, date_to)
    if dataset_name == "daily_analytics":
        return await _load_daily_analytics_records(db, org_id, date_from, date_to)
    if dataset_name == "ai_usage_events":
        start_at, end_at = _date_range_to_datetimes(date_from, date_to)
        return await _load_ai_usage_event_records(db, start_at=start_at, end_at=end_at, org_id=org_id)
    if dataset_name == "archived_messages":
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days or settings.olap_message_hot_retention_days)
        return await _load_archived_message_records(db, cutoff=cutoff, limit=None, org_id=org_id)
    raise ValueError(f"Unsupported dataset: {dataset_name}")


async def _load_campaign_metric_records(
    db: AsyncSession,
    org_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> list[dict[str, Any]]:
    filters = []
    if org_id is not None:
        filters.append(CampaignMetric.org_id == org_id)
    if date_from is not None:
        filters.append(CampaignMetric.date >= date_from)
    if date_to is not None:
        filters.append(CampaignMetric.date <= date_to)

    query = select(CampaignMetric)
    if filters:
        query = query.where(and_(*filters))
    result = await db.execute(query)
    return [_campaign_metric_record(row) for row in result.scalars().all()]


async def _load_campaign_breakdown_records(
    db: AsyncSession,
    org_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> list[dict[str, Any]]:
    filters = []
    if org_id is not None:
        filters.append(CampaignBreakdown.org_id == org_id)
    if date_from is not None:
        filters.append(CampaignBreakdown.date >= date_from)
    if date_to is not None:
        filters.append(CampaignBreakdown.date <= date_to)

    query = select(CampaignBreakdown)
    if filters:
        query = query.where(and_(*filters))
    result = await db.execute(query)
    return [_campaign_breakdown_record(row) for row in result.scalars().all()]


async def _load_daily_analytics_records(
    db: AsyncSession,
    org_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> list[dict[str, Any]]:
    filters = []
    if org_id is not None:
        filters.append(DailyAnalytics.org_id == org_id)
    if date_from is not None:
        filters.append(DailyAnalytics.date >= date_from)
    if date_to is not None:
        filters.append(DailyAnalytics.date <= date_to)

    query = select(DailyAnalytics)
    if filters:
        query = query.where(and_(*filters))
    result = await db.execute(query)
    return [_daily_analytics_record(row) for row in result.scalars().all()]


async def _load_ai_usage_event_records(
    db: AsyncSession,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
    org_id: uuid.UUID | None,
) -> list[dict[str, Any]]:
    filters = []
    if org_id is not None:
        filters.append(AIUsageEvent.org_id == org_id)
    if start_at is not None:
        filters.append(AIUsageEvent.created_at >= start_at)
    if end_at is not None:
        filters.append(AIUsageEvent.created_at <= end_at)

    query = select(AIUsageEvent)
    if filters:
        query = query.where(and_(*filters))
    result = await db.execute(query)
    return [_ai_usage_event_record(row) for row in result.scalars().all()]


async def _load_archived_message_records(
    db: AsyncSession,
    *,
    cutoff: datetime,
    limit: int | None,
    org_id: uuid.UUID | None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> list[dict[str, Any]]:
    filters = [Message.created_at < cutoff]
    if start_at is not None:
        filters.append(Message.created_at >= start_at)
    if end_at is not None:
        filters.append(Message.created_at <= end_at)

    query = (
        select(Message, Conversation.org_id, Conversation.channel, Conversation.status)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(and_(*filters))
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    if org_id is not None:
        query = query.where(Conversation.org_id == org_id)
    if limit is not None:
        query = query.limit(limit)

    result = await db.execute(query)
    return [
        _archived_message_record(message, message_org_id, channel, status)
        for message, message_org_id, channel, status in result.all()
    ]


async def _find_earliest_eligible_message_created_at(
    db: AsyncSession,
    eligible_upper_bound: datetime,
    org_id: uuid.UUID | None,
) -> datetime | None:
    query = (
        select(func.min(Message.created_at))
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.created_at < eligible_upper_bound)
    )
    if org_id is not None:
        query = query.where(Conversation.org_id == org_id)
    result = await db.execute(query)
    return result.scalar()


async def _load_all_org_ids(db: AsyncSession) -> list[uuid.UUID]:
    result = await db.execute(select(Organization.id).order_by(Organization.id))
    return [row[0] for row in result.all()]


def _campaign_metric_record(row: CampaignMetric) -> dict[str, Any]:
    return {
        "id": row.id,
        "org_id": row.org_id,
        "event_date": row.date,
        "level": row.level,
        "meta_campaign_id": row.meta_campaign_id,
        "meta_campaign_name": row.meta_campaign_name,
        "meta_adset_id": row.meta_adset_id,
        "meta_adset_name": row.meta_adset_name,
        "meta_ad_id": row.meta_ad_id,
        "meta_ad_name": row.meta_ad_name,
        "status": row.status,
        "objective": row.objective,
        "daily_budget": row.daily_budget,
        "spend": row.spend,
        "impressions": row.impressions,
        "clicks": row.clicks,
        "reach": row.reach,
        "frequency": row.frequency,
        "cpc": row.cpc,
        "cpm": row.cpm,
        "ctr": row.ctr,
        "leads": row.leads,
        "cost_per_lead": row.cost_per_lead,
        "link_clicks": row.link_clicks,
        "landing_page_views": row.landing_page_views,
        "video_views": row.video_views,
        "post_engagement": row.post_engagement,
        "messaging_conversations_started": row.messaging_conversations_started,
        "messaging_first_reply": row.messaging_first_reply,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _build_campaign_metric_agg_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    additive_fields = (
        "spend",
        "impressions",
        "clicks",
        "reach",
        "leads",
        "link_clicks",
        "landing_page_views",
        "video_views",
        "post_engagement",
        "messaging_conversations_started",
        "messaging_first_reply",
    )
    averaged_fields = (
        "frequency",
        "cpc",
        "cpm",
        "ctr",
        "cost_per_lead",
        "daily_budget",
    )
    int_fields = {
        "impressions",
        "clicks",
        "reach",
        "leads",
        "link_clicks",
        "landing_page_views",
        "video_views",
        "post_engagement",
        "messaging_conversations_started",
        "messaging_first_reply",
    }

    grouped: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    average_counts: dict[tuple[Any, Any, Any], dict[str, int]] = {}

    for record in records:
        if record.get("level") != "campaign":
            continue
        org_value = record.get("org_id")
        event_date = record.get("event_date")
        campaign_id = record.get("meta_campaign_id")
        if org_value is None or event_date is None or not campaign_id:
            continue

        key = (org_value, event_date, campaign_id)
        aggregate = grouped.setdefault(
            key,
            {
                "org_id": org_value,
                "event_date": event_date,
                "level": "campaign",
                "meta_campaign_id": campaign_id,
                "meta_campaign_name": record.get("meta_campaign_name"),
                "status": record.get("status"),
                "objective": record.get("objective"),
                "created_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
                **{field: 0.0 for field in additive_fields},
                **{field: None for field in averaged_fields},
            },
        )
        counts = average_counts.setdefault(key, {field: 0 for field in averaged_fields})

        for field in additive_fields:
            aggregate[field] += float(record.get(field) or 0)

        for field in averaged_fields:
            value = record.get(field)
            if value is None:
                continue
            current_total = float(aggregate[field] or 0)
            aggregate[field] = current_total + float(value)
            counts[field] += 1

        for field in ("meta_campaign_name", "status", "objective"):
            if record.get(field):
                aggregate[field] = record[field]

        created_at = record.get("created_at")
        updated_at = record.get("updated_at")
        if created_at is not None and (aggregate["created_at"] is None or created_at < aggregate["created_at"]):
            aggregate["created_at"] = created_at
        if updated_at is not None and (aggregate["updated_at"] is None or updated_at > aggregate["updated_at"]):
            aggregate["updated_at"] = updated_at

    output: list[dict[str, Any]] = []
    for key, aggregate in grouped.items():
        counts = average_counts[key]
        for field in additive_fields:
            if field in int_fields:
                aggregate[field] = int(round(float(aggregate[field] or 0)))
            else:
                aggregate[field] = round(float(aggregate[field] or 0), 4)
        for field in averaged_fields:
            count = counts[field]
            if count == 0:
                aggregate[field] = None
            else:
                aggregate[field] = round(float(aggregate[field] or 0) / count, 4)
        output.append(aggregate)

    return output


def _campaign_breakdown_record(row: CampaignBreakdown) -> dict[str, Any]:
    return {
        "id": row.id,
        "org_id": row.org_id,
        "event_date": row.date,
        "meta_campaign_id": row.meta_campaign_id,
        "meta_adset_id": row.meta_adset_id,
        "meta_ad_id": row.meta_ad_id,
        "breakdown_type": row.breakdown_type,
        "breakdown_key": row.breakdown_key,
        "spend": row.spend,
        "impressions": row.impressions,
        "clicks": row.clicks,
        "leads": row.leads,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _daily_analytics_record(row: DailyAnalytics) -> dict[str, Any]:
    return {
        "id": row.id,
        "org_id": row.org_id,
        "event_date": row.date,
        "channel": row.channel,
        "new_conversations": row.new_conversations,
        "active_conversations": row.active_conversations,
        "total_messages": row.total_messages,
        "avg_messages_per_conversation": row.avg_messages_per_conversation,
        "avg_ai_response_time_ms": row.avg_ai_response_time_ms,
        "conversions": row.conversions,
        "conversion_value": row.conversion_value,
        "conversion_rate": row.conversion_rate,
        "ad_spend": row.ad_spend,
        "cpa": row.cpa,
        "roas": row.roas,
        "ai_tokens_used": row.ai_tokens_used,
        "ai_cost": row.ai_cost,
        "fallback_count": row.fallback_count,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _ai_usage_event_record(row: AIUsageEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "org_id": row.org_id,
        "event_date": row.created_at.date(),
        "conversation_id": row.conversation_id,
        "message_id": row.message_id,
        "stage": row.stage,
        "model": row.model,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "cache_read_tokens": row.cache_read_tokens,
        "cache_creation_tokens": row.cache_creation_tokens,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _build_ai_usage_event_agg_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for record in records:
        org_id = record.get("org_id")
        conversation_id = record.get("conversation_id")
        event_date = record.get("event_date")
        if org_id is None or event_date is None:
            continue

        key = (org_id, conversation_id, event_date)
        bucket = grouped.setdefault(
            key,
            {
                "org_id": org_id,
                "conversation_id": conversation_id,
                "event_date": event_date,
                "event_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
                "first_event_at": record.get("created_at"),
                "last_event_at": record.get("created_at"),
                "created_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
            },
        )

        bucket["event_count"] += 1
        bucket["input_tokens"] += int(record.get("input_tokens") or 0)
        bucket["output_tokens"] += int(record.get("output_tokens") or 0)
        bucket["cache_read_tokens"] += int(record.get("cache_read_tokens") or 0)
        bucket["cache_creation_tokens"] += int(record.get("cache_creation_tokens") or 0)

        created_at = record.get("created_at")
        updated_at = record.get("updated_at")
        if created_at is not None and (bucket["first_event_at"] is None or created_at < bucket["first_event_at"]):
            bucket["first_event_at"] = created_at
        if created_at is not None and (bucket["last_event_at"] is None or created_at > bucket["last_event_at"]):
            bucket["last_event_at"] = created_at
        if created_at is not None and (bucket["created_at"] is None or created_at < bucket["created_at"]):
            bucket["created_at"] = created_at
        if updated_at is not None and (bucket["updated_at"] is None or updated_at > bucket["updated_at"]):
            bucket["updated_at"] = updated_at

    return list(grouped.values())


def _archived_message_record(
    row: Message,
    org_id: uuid.UUID,
    channel: Any,
    status: Any,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "org_id": org_id,
        "event_date": row.created_at.date(),
        "conversation_id": row.conversation_id,
        "sender": row.sender,
        "content": row.content,
        "intent_signals": row.intent_signals,
        "buyer_stage_at_time": row.buyer_stage_at_time,
        "compliance_flags": row.compliance_flags,
        "ai_model": row.ai_model,
        "ai_response_time_ms": row.ai_response_time_ms,
        "ai_tokens_used": row.ai_tokens_used,
        "quick_replies": row.quick_replies,
        "conversation_channel": channel,
        "conversation_status": status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "archived_at": datetime.now(timezone.utc),
        "archive_mode": "shadow",
    }


def _build_archived_message_agg_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for record in records:
        org_id = record.get("org_id")
        conversation_id = record.get("conversation_id")
        event_date = record.get("event_date")
        if org_id is None or event_date is None:
            continue

        key = (org_id, conversation_id, event_date)
        bucket = grouped.setdefault(
            key,
            {
                "org_id": org_id,
                "conversation_id": conversation_id,
                "event_date": event_date,
                "conversation_channel": record.get("conversation_channel"),
                "conversation_status": record.get("conversation_status"),
                "message_count": 0,
                "ai_message_count": 0,
                "user_message_count": 0,
                "total_ai_tokens_used": 0,
                "total_ai_response_time_ms": 0,
                "ai_response_samples": 0,
                "first_message_at": record.get("created_at"),
                "last_message_at": record.get("created_at"),
                "created_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
            },
        )

        sender = str(record.get("sender") or "")
        bucket["message_count"] += 1
        if sender == "ai":
            bucket["ai_message_count"] += 1
        elif sender == "user":
            bucket["user_message_count"] += 1

        bucket["total_ai_tokens_used"] += int(record.get("ai_tokens_used") or 0)
        response_time = record.get("ai_response_time_ms")
        if response_time is not None:
            bucket["total_ai_response_time_ms"] += int(response_time)
            bucket["ai_response_samples"] += 1

        if record.get("conversation_channel") is not None:
            bucket["conversation_channel"] = record.get("conversation_channel")
        if record.get("conversation_status") is not None:
            bucket["conversation_status"] = record.get("conversation_status")

        created_at = record.get("created_at")
        updated_at = record.get("updated_at")
        if created_at is not None and (bucket["first_message_at"] is None or created_at < bucket["first_message_at"]):
            bucket["first_message_at"] = created_at
        if created_at is not None and (bucket["last_message_at"] is None or created_at > bucket["last_message_at"]):
            bucket["last_message_at"] = created_at
        if created_at is not None and (bucket["created_at"] is None or created_at < bucket["created_at"]):
            bucket["created_at"] = created_at
        if updated_at is not None and (bucket["updated_at"] is None or updated_at > bucket["updated_at"]):
            bucket["updated_at"] = updated_at

    output: list[dict[str, Any]] = []
    for bucket in grouped.values():
        samples = int(bucket.pop("ai_response_samples"))
        if samples > 0:
            bucket["avg_ai_response_time_ms"] = round(bucket.pop("total_ai_response_time_ms") / samples, 2)
        else:
            bucket.pop("total_ai_response_time_ms")
            bucket["avg_ai_response_time_ms"] = None
        output.append(bucket)
    return output


def _load_exported_records(
    storage,
    dataset_name: str,
    *,
    org_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> list[dict[str, Any]]:
    dataset = OLAP_DATASETS[dataset_name]
    records: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for prefix in _dataset_scan_prefixes(storage, dataset, org_id=org_id, date_from=date_from, date_to=date_to):
        for storage_object in storage.list_objects(prefix):
            if storage_object.key in seen_keys:
                continue
            seen_keys.add(storage_object.key)
            payload = storage.download_bytes(storage_object.key)
            for record in records_from_parquet_bytes(payload):
                event_date = _coerce_date(record.get("event_date"))
                if org_id is not None and str(record.get("org_id")) != str(org_id):
                    continue
                if date_from is not None and event_date is not None and event_date < date_from:
                    continue
                if date_to is not None and event_date is not None and event_date > date_to:
                    continue
                records.append(record)
    return records


def _dataset_scan_prefixes(
    storage,
    dataset,
    *,
    org_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> list[str]:
    base_prefix = storage.dataset_prefix(dataset)
    partition_values: list[list[str]] = []

    for key in dataset.partition_keys:
        if key == "org_id" and org_id is not None:
            partition_values.append([str(org_id)])
            continue
        if key == "event_date" and date_from is not None and date_to is not None and date_from <= date_to:
            day_count = (date_to - date_from).days + 1
            partition_values.append([
                (date_from + timedelta(days=offset)).isoformat()
                for offset in range(day_count)
            ])
            continue
        return [base_prefix]

    if not partition_values:
        return [base_prefix]

    prefixes = [base_prefix]
    for key, values in zip(dataset.partition_keys, partition_values, strict=False):
        prefixes = [f"{prefix}/{key}={value}" for prefix in prefixes for value in values]
    return prefixes


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return None


def _summarize_dataset(dataset_name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {"row_count": len(records)}
    numeric_fields_by_dataset = {
        "campaign_metrics": ["spend", "impressions", "clicks", "leads"],
        "campaign_metrics_agg": ["spend", "impressions", "clicks", "leads"],
        "campaign_breakdowns": ["spend", "impressions", "clicks", "leads"],
        "daily_analytics": ["new_conversations", "active_conversations", "total_messages", "conversions", "conversion_value", "ad_spend", "ai_tokens_used", "ai_cost", "fallback_count"],
        "ai_usage_events": ["input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"],
        "archived_messages": ["ai_tokens_used"],
    }
    int_fields = {
        "impressions", "clicks", "leads", "new_conversations", "active_conversations", "total_messages",
        "conversions", "ai_tokens_used", "fallback_count", "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens",
    }
    for field in numeric_fields_by_dataset.get(dataset_name, []):
        total = 0.0
        for record in records:
            value = record.get(field)
            if value is None:
                continue
            total += float(value)
        summary[field] = int(total) if field in int_fields else round(total, 4)
    return summary


def _summarize_reporting_daily_analytics(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _summarize_dataset("daily_analytics", records)
    summary["channels"] = sorted({record.get("channel") or "all" for record in records})
    summary["campaign_health"] = _campaign_health_from_daily_records(records)
    return summary


def _campaign_health_from_daily_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, float]] = {}
    for record in records:
        channel_name = record.get("channel") or "all"
        bucket = grouped.setdefault(channel_name, {"ad_spend": 0.0, "conversions": 0.0})
        bucket["ad_spend"] += float(record.get("ad_spend") or 0.0)
        bucket["conversions"] += float(record.get("conversions") or 0.0)

    items = []
    for channel_name, values in sorted(grouped.items()):
        ad_spend = values["ad_spend"]
        conversions = int(values["conversions"])
        if ad_spend <= 0:
            status = "green"
            reason = "No ad spend"
        elif conversions == 0:
            status = "red"
            reason = f"No conversions with ${ad_spend:.0f} spend"
        else:
            cpa = ad_spend / conversions
            if cpa < 50:
                status = "green"
                reason = f"CPA ${cpa:.2f}"
            elif cpa < 100:
                status = "yellow"
                reason = f"CPA ${cpa:.2f} — consider optimization"
            else:
                status = "red"
                reason = f"CPA ${cpa:.2f} — needs attention"
        items.append({"name": channel_name, "status": status, "reason": reason})
    return items


def _summarize_campaign_reporting(
    metric_records: list[dict[str, Any]],
    breakdown_records: list[dict[str, Any]],
) -> dict[str, Any]:
    by_level: dict[str, dict[str, float]] = {}
    for record in metric_records:
        level = record.get("level") or "unknown"
        bucket = by_level.setdefault(level, {"row_count": 0, "spend": 0.0, "impressions": 0.0, "clicks": 0.0, "leads": 0.0})
        bucket["row_count"] += 1
        bucket["spend"] += float(record.get("spend") or 0.0)
        bucket["impressions"] += float(record.get("impressions") or 0.0)
        bucket["clicks"] += float(record.get("clicks") or 0.0)
        bucket["leads"] += float(record.get("leads") or 0.0)

    breakdowns: dict[str, dict[str, float]] = {}
    for record in breakdown_records:
        breakdown_type = record.get("breakdown_type") or "unknown"
        bucket = breakdowns.setdefault(breakdown_type, {"row_count": 0, "spend": 0.0, "impressions": 0.0, "clicks": 0.0, "leads": 0.0})
        bucket["row_count"] += 1
        bucket["spend"] += float(record.get("spend") or 0.0)
        bucket["impressions"] += float(record.get("impressions") or 0.0)
        bucket["clicks"] += float(record.get("clicks") or 0.0)
        bucket["leads"] += float(record.get("leads") or 0.0)

    return {
        "levels": {key: _round_summary(value) for key, value in sorted(by_level.items())},
        "breakdowns": {key: _round_summary(value) for key, value in sorted(breakdowns.items())},
    }


def _round_summary(value: dict[str, float]) -> dict[str, Any]:
    rounded = {}
    for key, item in value.items():
        if key == "row_count" or key in {"impressions", "clicks", "leads"}:
            rounded[key] = int(item)
        else:
            rounded[key] = round(item, 4)
    return rounded


def _date_range_to_datetimes(
    date_from: date | None,
    date_to: date | None,
) -> tuple[datetime | None, datetime | None]:
    start_at = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else None
    end_at = datetime.combine(date_to, time.max, tzinfo=timezone.utc) if date_to else None
    return start_at, end_at


def _scope_key(org_id: uuid.UUID | None) -> str:
    return str(org_id) if org_id is not None else "global"