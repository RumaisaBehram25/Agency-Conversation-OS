"""Trino-backed OLAP services for additive reporting endpoints."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import date, timedelta
from time import monotonic
from typing import Any

from app.config import settings
from app.models.base import ChannelType
from app.olap import get_query_adapter
from app.schemas.analytics import (
    AIPerformanceResponse,
    AnalyticsResponse,
    DailyTrend,
    FunnelStep,
    ROIResponse,
)
from app.schemas.campaigns import (
    AdSetSummary,
    AdSummary,
    BreakdownItem,
    CampaignDailyMetric,
    CampaignSummary,
)
from app.schemas.dashboard import CampaignHealth

_CATALOG_LOCK = asyncio.Lock()
_CATALOG_READY = False
_PARTITION_SYNC_LOCK = asyncio.Lock()
_PARTITION_LAST_SYNC: dict[str, float] = {}
_DAILY_ANALYTICS_TABLE = "daily_analytics_compact"
_CAMPAIGN_METRICS_TABLE = "campaign_metrics"
_CAMPAIGN_METRICS_AGG_TABLE = "campaign_metrics_agg"
_CAMPAIGN_BREAKDOWNS_TABLE = "campaign_breakdowns"


async def get_olap_analytics(
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    channel: str | None = None,
) -> AnalyticsResponse:
    return await _get_olap_analytics(org_id, date_from, date_to, channel, ensure_ready=True)


async def _get_olap_analytics(
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    channel: str | None,
    *,
    ensure_ready: bool,
) -> AnalyticsResponse:
    if ensure_ready:
        await _ensure_tables_ready([_DAILY_ANALYTICS_TABLE])

    aggregate_query = f"""
        SELECT
            COALESCE(SUM(CAST(new_conversations AS BIGINT)), 0) AS total_conversations,
            COALESCE(SUM(CAST(conversions AS BIGINT)), 0) AS total_conversions,
            COALESCE(SUM(CAST(conversion_value AS DOUBLE)), 0) AS total_revenue,
            COALESCE(SUM(CAST(ad_spend AS DOUBLE)), 0) AS total_ad_spend,
            AVG(CAST(avg_ai_response_time_ms AS DOUBLE)) AS avg_response_time_ms
        FROM {_DAILY_ANALYTICS_TABLE}
        WHERE {_daily_analytics_where(org_id, date_from, date_to, channel=channel)}
    """
    trend_cpqc_query = f"""
        SELECT
            event_date AS trend_date,
            COALESCE(SUM(CAST(ad_spend AS DOUBLE)), 0) AS ad_spend,
            COALESCE(SUM(CAST(new_conversations AS BIGINT)), 0) AS conversations
        FROM {_DAILY_ANALYTICS_TABLE}
        WHERE {_daily_analytics_where(org_id, date_from, date_to, channel=channel)}
        GROUP BY event_date
        ORDER BY event_date
    """
    trend_ccr_query = f"""
        SELECT
            event_date AS trend_date,
            COALESCE(SUM(CAST(conversions AS BIGINT)), 0) AS conversions,
            COALESCE(SUM(CAST(new_conversations AS BIGINT)), 0) AS conversations
        FROM {_DAILY_ANALYTICS_TABLE}
        WHERE {_daily_analytics_where(org_id, date_from, date_to, channel=channel)}
        GROUP BY event_date
        ORDER BY event_date
    """

    aggregate_result, cpqc_trend_result, ccr_trend_result = await _execute_queries(
        aggregate_query,
        trend_cpqc_query,
        trend_ccr_query,
    )
    aggregate_row = _first_row(aggregate_result)
    total_conversations = _int_value(aggregate_row, "total_conversations")
    total_conversions = _int_value(aggregate_row, "total_conversions")
    total_revenue = _float_value(aggregate_row, "total_revenue")
    total_ad_spend = _float_value(aggregate_row, "total_ad_spend")
    avg_response_time_ms = _optional_int_value(aggregate_row, "avg_response_time_ms")

    cpqc = round(total_ad_spend / total_conversations, 2) if total_conversations > 0 and total_ad_spend > 0 else None
    ccr = round(total_conversions / total_conversations, 4) if total_conversations > 0 else None
    qualification_rate = round(total_conversions / total_conversations, 4) if total_conversations > 0 else None

    cpqc_trend_rows = cpqc_trend_result.rows
    cpqc_trend = []
    for row in cpqc_trend_rows:
        conversations = _int_value(row, "conversations")
        ad_spend = _float_value(row, "ad_spend")
        value = round(ad_spend / conversations, 2) if conversations > 0 and ad_spend > 0 else 0.0
        cpqc_trend.append(DailyTrend(date=_date_value(row, "trend_date"), value=value))

    ccr_trend_rows = ccr_trend_result.rows
    ccr_trend = []
    for row in ccr_trend_rows:
        conversations = _int_value(row, "conversations")
        conversions = _int_value(row, "conversions")
        value = round(conversions / conversations, 4) if conversations > 0 else 0.0
        ccr_trend.append(DailyTrend(date=_date_value(row, "trend_date"), value=value))

    qualified_proxy = total_conversations
    funnel = _build_funnel_proxy(total_conversations, qualified_proxy, total_conversions)

    return AnalyticsResponse(
        date_from=date_from,
        date_to=date_to,
        channel=channel,
        cpqc=cpqc,
        ccr=ccr,
        avg_response_time_ms=avg_response_time_ms,
        qualification_rate=qualification_rate,
        total_conversations=total_conversations,
        total_conversions=total_conversions,
        total_revenue=total_revenue,
        funnel=funnel,
        cpqc_trend=cpqc_trend,
        ccr_trend=ccr_trend,
    )


async def get_olap_roi(
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> ROIResponse:
    await _ensure_tables_ready([_DAILY_ANALYTICS_TABLE])

    aggregate_query = f"""
        SELECT
            COALESCE(SUM(CAST(ad_spend AS DOUBLE)), 0) AS ad_spend,
            COALESCE(SUM(CAST(new_conversations AS BIGINT)), 0) AS conversations_count,
            COALESCE(SUM(CAST(conversions AS BIGINT)), 0) AS converted_count,
            COALESCE(SUM(CAST(conversion_value AS DOUBLE)), 0) AS revenue
        FROM {_DAILY_ANALYTICS_TABLE}
        WHERE {_daily_analytics_where(org_id, date_from, date_to)}
    """

    range_days = (date_to - date_from).days
    midpoint = date_from + timedelta(days=range_days // 2)

    baseline_query = f"""
        SELECT
            COALESCE(SUM(CAST(ad_spend AS DOUBLE)), 0) AS ad_spend,
            COALESCE(SUM(CAST(conversions AS BIGINT)), 0) AS conversions,
            COALESCE(SUM(CAST(conversion_value AS DOUBLE)), 0) AS revenue
        FROM {_DAILY_ANALYTICS_TABLE}
        WHERE {_daily_analytics_where(org_id, date_from, midpoint - timedelta(days=1))}
    """
    current_query = f"""
        SELECT
            COALESCE(SUM(CAST(ad_spend AS DOUBLE)), 0) AS ad_spend,
            COALESCE(SUM(CAST(conversions AS BIGINT)), 0) AS conversions,
            COALESCE(SUM(CAST(conversion_value AS DOUBLE)), 0) AS revenue
        FROM {_DAILY_ANALYTICS_TABLE}
        WHERE {_daily_analytics_where(org_id, midpoint, date_to)}
    """

    aggregate_result, baseline_result, current_result = await _execute_queries(
        aggregate_query,
        baseline_query,
        current_query,
    )
    aggregate_row = _first_row(aggregate_result)
    ad_spend = _float_value(aggregate_row, "ad_spend")
    conversations_count = _int_value(aggregate_row, "conversations_count")
    converted_count = _int_value(aggregate_row, "converted_count")
    revenue = _float_value(aggregate_row, "revenue")

    qualified_count = conversations_count
    cost_per_conversation = round(ad_spend / conversations_count, 2) if conversations_count > 0 and ad_spend > 0 else None
    cost_per_qualified = round(ad_spend / qualified_count, 2) if qualified_count > 0 and ad_spend > 0 else None
    cpa = round(ad_spend / converted_count, 2) if converted_count > 0 and ad_spend > 0 else None
    roas = round(revenue / ad_spend, 2) if ad_spend > 0 else None

    baseline_row = _first_row(baseline_result)
    current_row = _first_row(current_result)

    baseline_ad_spend = _float_value(baseline_row, "ad_spend")
    baseline_conversions = _int_value(baseline_row, "conversions")
    baseline_revenue = _float_value(baseline_row, "revenue")
    current_ad_spend = _float_value(current_row, "ad_spend")
    current_conversions = _int_value(current_row, "conversions")
    current_revenue = _float_value(current_row, "revenue")

    baseline_cpa = round(baseline_ad_spend / baseline_conversions, 2) if baseline_conversions > 0 and baseline_ad_spend > 0 else None
    current_cpa = round(current_ad_spend / current_conversions, 2) if current_conversions > 0 and current_ad_spend > 0 else None
    baseline_roas = round(baseline_revenue / baseline_ad_spend, 2) if baseline_ad_spend > 0 else None
    current_roas = round(current_revenue / current_ad_spend, 2) if current_ad_spend > 0 else None

    return ROIResponse(
        date_from=date_from,
        date_to=date_to,
        ad_spend=ad_spend,
        conversations_count=conversations_count,
        cost_per_conversation=cost_per_conversation,
        qualified_count=qualified_count,
        cost_per_qualified=cost_per_qualified,
        converted_count=converted_count,
        cpa=cpa,
        revenue=revenue,
        roas=roas,
        baseline_cpa=baseline_cpa,
        current_cpa=current_cpa,
        baseline_roas=baseline_roas,
        current_roas=current_roas,
    )


async def get_olap_ai_performance(
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> AIPerformanceResponse:
    await _ensure_tables_ready([_DAILY_ANALYTICS_TABLE])

    aggregate_query = f"""
        SELECT
            COALESCE(SUM(CAST(ai_tokens_used AS BIGINT)), 0) AS total_ai_tokens,
            COALESCE(SUM(CAST(ai_cost AS DOUBLE)), 0) AS total_ai_cost,
            COALESCE(SUM(CAST(fallback_count AS BIGINT)), 0) AS total_fallbacks,
            COALESCE(SUM(CAST(total_messages AS BIGINT)), 0) AS total_messages,
            AVG(CAST(avg_ai_response_time_ms AS DOUBLE)) AS avg_response_time_ms
        FROM {_DAILY_ANALYTICS_TABLE}
        WHERE {_daily_analytics_where(org_id, date_from, date_to)}
    """
    trend_query = f"""
        SELECT
            event_date AS trend_date,
            COALESCE(SUM(CAST(fallback_count AS BIGINT)), 0) AS fallbacks,
            COALESCE(SUM(CAST(total_messages AS BIGINT)), 0) AS messages
        FROM {_DAILY_ANALYTICS_TABLE}
        WHERE {_daily_analytics_where(org_id, date_from, date_to)}
        GROUP BY event_date
        ORDER BY event_date
    """

    aggregate_result, trend_result = await _execute_queries(aggregate_query, trend_query)
    aggregate_row = _first_row(aggregate_result)
    total_ai_tokens = _int_value(aggregate_row, "total_ai_tokens")
    total_ai_cost = _float_value(aggregate_row, "total_ai_cost")
    total_fallbacks = _int_value(aggregate_row, "total_fallbacks")
    total_messages = _int_value(aggregate_row, "total_messages")
    avg_response_time_ms = _optional_int_value(aggregate_row, "avg_response_time_ms")

    fallback_rate = round(total_fallbacks / total_messages, 4) if total_messages > 0 else None

    trend_rows = trend_result.rows
    fallback_trend = []
    for row in trend_rows:
        messages = _int_value(row, "messages")
        fallbacks = _int_value(row, "fallbacks")
        value = round(fallbacks / messages, 4) if messages > 0 else 0.0
        fallback_trend.append(DailyTrend(date=_date_value(row, "trend_date"), value=value))

    return AIPerformanceResponse(
        fallback_rate=fallback_rate,
        fallback_trend=fallback_trend,
        avg_response_time_ms=avg_response_time_ms,
        total_ai_tokens=total_ai_tokens,
        total_ai_cost=total_ai_cost,
    )


async def get_olap_dashboard_overview(org_id: uuid.UUID) -> dict[str, Any]:
    await _ensure_tables_ready([_DAILY_ANALYTICS_TABLE])

    today = date.today()
    seven_days_ago = today - timedelta(days=7)
    analytics = await _get_olap_analytics(org_id, seven_days_ago, today, None, ensure_ready=False)

    today_query = f"""
        SELECT
            COALESCE(SUM(CAST(active_conversations AS BIGINT)), 0) AS active_conversations_count,
            COALESCE(SUM(CAST(conversions AS BIGINT)), 0) AS todays_conversions,
            COALESCE(SUM(CAST(conversion_value AS DOUBLE)), 0) AS todays_revenue
        FROM {_DAILY_ANALYTICS_TABLE}
        WHERE {_daily_analytics_where(org_id, today, today, combined_only=True)}
    """
    health_query = f"""
        SELECT
            channel,
            COALESCE(SUM(CAST(ad_spend AS DOUBLE)), 0) AS ad_spend,
            COALESCE(SUM(CAST(conversions AS BIGINT)), 0) AS conversions
        FROM {_DAILY_ANALYTICS_TABLE}
        WHERE {_daily_analytics_where(org_id, seven_days_ago, today, exclude_null_channel=True)}
        GROUP BY channel
        ORDER BY channel
    """
    avg_steps_query = f"""
        SELECT
            CAST(SUM(CAST(total_messages AS BIGINT)) AS DOUBLE)
                / CAST(NULLIF(SUM(CAST(active_conversations AS BIGINT)), 0) AS DOUBLE)
                AS avg_steps_per_conversation
        FROM {_DAILY_ANALYTICS_TABLE}
        WHERE {_daily_analytics_where(org_id, date(1970, 1, 1), today, combined_only=True)}
    """

    today_result, health_result, avg_steps_result = await _execute_queries(
        today_query, health_query, avg_steps_query
    )
    today_row = _first_row(today_result)
    health_rows = health_result.rows

    campaign_health = []
    for row in health_rows:
        channel_name = str(row.get("channel") or "all")
        ad_spend = _float_value(row, "ad_spend")
        conversions = _int_value(row, "conversions")
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
        campaign_health.append(CampaignHealth(name=channel_name, status=status, reason=reason))

    avg_steps_row = _first_row(avg_steps_result)
    avg_steps_val = _optional_float_value(avg_steps_row, "avg_steps_per_conversation")
    avg_steps_per_conversation = (
        round(avg_steps_val, 2) if avg_steps_val is not None else None
    )

    return {
        "cpqc": analytics.cpqc,
        "cpqc_trend": analytics.cpqc_trend,
        "ccr": analytics.ccr,
        "ccr_trend": analytics.ccr_trend,
        "avg_steps_per_conversation": avg_steps_per_conversation,
        "active_conversations_count": _int_value(today_row, "active_conversations_count"),
        "todays_conversions": _int_value(today_row, "todays_conversions"),
        "todays_revenue": _float_value(today_row, "todays_revenue"),
        "campaign_health": campaign_health,
    }


async def get_olap_analytics_export_data(
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    channel: str | None = None,
) -> list[dict[str, Any]]:
    await _ensure_tables_ready([_DAILY_ANALYTICS_TABLE])

    export_query = f"""
        SELECT
            event_date AS export_date,
            COALESCE(channel, 'all') AS export_channel,
            CAST(new_conversations AS BIGINT) AS new_conversations,
            CAST(active_conversations AS BIGINT) AS active_conversations,
            CAST(total_messages AS BIGINT) AS total_messages,
            CAST(avg_messages_per_conversation AS DOUBLE) AS avg_messages_per_conversation,
            CAST(avg_ai_response_time_ms AS INTEGER) AS avg_ai_response_time_ms,
            CAST(conversions AS BIGINT) AS conversions,
            CAST(conversion_value AS DOUBLE) AS conversion_value,
            CAST(conversion_rate AS DOUBLE) AS conversion_rate,
            CAST(ad_spend AS DOUBLE) AS ad_spend,
            CAST(cpa AS DOUBLE) AS cpa,
            CAST(roas AS DOUBLE) AS roas,
            CAST(ai_tokens_used AS BIGINT) AS ai_tokens_used,
            CAST(ai_cost AS DOUBLE) AS ai_cost,
            CAST(fallback_count AS BIGINT) AS fallback_count
        FROM {_DAILY_ANALYTICS_TABLE}
        WHERE {_daily_analytics_where(org_id, date_from, date_to, channel=channel)}
        ORDER BY event_date, COALESCE(channel, 'all')
    """

    rows = (await _execute_query(export_query)).rows
    return [
        {
            "date": _date_value(row, "export_date").isoformat(),
            "channel": str(row.get("export_channel") or "all"),
            "new_conversations": _int_value(row, "new_conversations"),
            "active_conversations": _int_value(row, "active_conversations"),
            "total_messages": _int_value(row, "total_messages"),
            "avg_messages_per_conversation": _optional_float_value(row, "avg_messages_per_conversation"),
            "avg_ai_response_time_ms": _optional_int_value(row, "avg_ai_response_time_ms"),
            "conversions": _int_value(row, "conversions"),
            "conversion_value": _float_value(row, "conversion_value"),
            "conversion_rate": _optional_float_value(row, "conversion_rate"),
            "ad_spend": _optional_float_value(row, "ad_spend"),
            "cpa": _optional_float_value(row, "cpa"),
            "roas": _optional_float_value(row, "roas"),
            "ai_tokens_used": _int_value(row, "ai_tokens_used"),
            "ai_cost": _float_value(row, "ai_cost"),
            "fallback_count": _int_value(row, "fallback_count"),
        }
        for row in rows
    ]


async def list_olap_campaigns(
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> list[CampaignSummary]:
    await _ensure_tables_ready([_CAMPAIGN_METRICS_AGG_TABLE])

    query = f"""
        SELECT
            meta_campaign_id,
            MAX(meta_campaign_name) AS meta_campaign_name,
            MAX(status) AS status,
            COALESCE(SUM(CAST(spend AS DOUBLE)), 0) AS spend,
            COALESCE(SUM(CAST(impressions AS BIGINT)), 0) AS impressions,
            COALESCE(SUM(CAST(clicks AS BIGINT)), 0) AS clicks,
            COALESCE(SUM(CAST(leads AS BIGINT)), 0) AS leads,
            COALESCE(SUM(CAST(link_clicks AS BIGINT)), 0) AS link_clicks,
            COALESCE(SUM(CAST(video_views AS BIGINT)), 0) AS video_views,
            AVG(CAST(cpc AS DOUBLE)) AS cpc,
            AVG(CAST(cpm AS DOUBLE)) AS cpm,
            AVG(CAST(ctr AS DOUBLE)) AS ctr
        FROM {_CAMPAIGN_METRICS_AGG_TABLE}
        WHERE {_campaign_metrics_where(org_id, date_from, date_to, "campaign")}
        GROUP BY meta_campaign_id
        ORDER BY spend DESC
    """
    rows = (await _execute_query(query)).rows
    return [_campaign_summary_from_row(row) for row in rows]


async def get_olap_campaign_detail(
    org_id: uuid.UUID,
    campaign_id: str,
    date_from: date,
    date_to: date,
) -> list[CampaignDailyMetric]:
    await _ensure_tables_ready([_CAMPAIGN_METRICS_AGG_TABLE])

    query = f"""
        SELECT
            event_date AS metric_date,
            CAST(spend AS DOUBLE) AS spend,
            CAST(impressions AS BIGINT) AS impressions,
            CAST(clicks AS BIGINT) AS clicks,
            CAST(leads AS BIGINT) AS leads,
            CAST(cpc AS DOUBLE) AS cpc,
            CAST(cpm AS DOUBLE) AS cpm,
            CAST(ctr AS DOUBLE) AS ctr,
            CAST(reach AS BIGINT) AS reach,
            CAST(frequency AS DOUBLE) AS frequency
        FROM {_CAMPAIGN_METRICS_AGG_TABLE}
        WHERE {_campaign_metrics_where(org_id, date_from, date_to, "campaign", campaign_id=campaign_id)}
        ORDER BY event_date ASC
    """
    rows = (await _execute_query(query)).rows
    return [
        CampaignDailyMetric(
            date=_date_value(row, "metric_date"),
            spend=_float_value(row, "spend"),
            impressions=_int_value(row, "impressions"),
            clicks=_int_value(row, "clicks"),
            leads=_int_value(row, "leads"),
            cpc=_optional_float_value(row, "cpc"),
            cpm=_optional_float_value(row, "cpm"),
            ctr=_optional_float_value(row, "ctr"),
            reach=_int_value(row, "reach"),
            frequency=_optional_float_value(row, "frequency"),
        )
        for row in rows
    ]


async def list_olap_adsets(
    org_id: uuid.UUID,
    campaign_id: str,
    date_from: date,
    date_to: date,
) -> list[AdSetSummary]:
    await _ensure_tables_ready([_CAMPAIGN_METRICS_TABLE])

    query = f"""
        SELECT
            meta_adset_id,
            MAX(meta_adset_name) AS meta_adset_name,
            MAX(status) AS status,
            COALESCE(SUM(CAST(spend AS DOUBLE)), 0) AS spend,
            COALESCE(SUM(CAST(impressions AS BIGINT)), 0) AS impressions,
            COALESCE(SUM(CAST(clicks AS BIGINT)), 0) AS clicks,
            COALESCE(SUM(CAST(leads AS BIGINT)), 0) AS leads,
            COALESCE(SUM(CAST(link_clicks AS BIGINT)), 0) AS link_clicks,
            COALESCE(SUM(CAST(video_views AS BIGINT)), 0) AS video_views,
            AVG(CAST(cpc AS DOUBLE)) AS cpc,
            AVG(CAST(cpm AS DOUBLE)) AS cpm,
            AVG(CAST(ctr AS DOUBLE)) AS ctr
        FROM {_CAMPAIGN_METRICS_TABLE}
        WHERE {_campaign_metrics_where(org_id, date_from, date_to, "adset", campaign_id=campaign_id)}
        GROUP BY meta_adset_id
        ORDER BY spend DESC
    """
    rows = (await _execute_query(query)).rows
    return [_adset_summary_from_row(row) for row in rows]


async def list_olap_ads(
    org_id: uuid.UUID,
    campaign_id: str,
    adset_id: str,
    date_from: date,
    date_to: date,
) -> list[AdSummary]:
    await _ensure_tables_ready([_CAMPAIGN_METRICS_TABLE])

    query = f"""
        SELECT
            meta_ad_id,
            MAX(meta_ad_name) AS meta_ad_name,
            MAX(status) AS status,
            COALESCE(SUM(CAST(spend AS DOUBLE)), 0) AS spend,
            COALESCE(SUM(CAST(impressions AS BIGINT)), 0) AS impressions,
            COALESCE(SUM(CAST(clicks AS BIGINT)), 0) AS clicks,
            COALESCE(SUM(CAST(leads AS BIGINT)), 0) AS leads,
            COALESCE(SUM(CAST(link_clicks AS BIGINT)), 0) AS link_clicks,
            COALESCE(SUM(CAST(video_views AS BIGINT)), 0) AS video_views,
            AVG(CAST(cpc AS DOUBLE)) AS cpc,
            AVG(CAST(cpm AS DOUBLE)) AS cpm,
            AVG(CAST(ctr AS DOUBLE)) AS ctr
        FROM {_CAMPAIGN_METRICS_TABLE}
        WHERE {_campaign_metrics_where(org_id, date_from, date_to, "ad", campaign_id=campaign_id, adset_id=adset_id)}
        GROUP BY meta_ad_id
        ORDER BY spend DESC
    """
    rows = (await _execute_query(query)).rows
    return [_ad_summary_from_row(row) for row in rows]


async def get_olap_campaign_breakdowns(
    org_id: uuid.UUID,
    campaign_id: str,
    breakdown_type: str,
    date_from: date,
    date_to: date,
) -> list[BreakdownItem]:
    await _ensure_tables_ready([_CAMPAIGN_BREAKDOWNS_TABLE])

    if breakdown_type not in {"age_gender", "platform"}:
        raise ValueError('Invalid breakdown type. Must be "age_gender" or "platform".')

    query = f"""
        SELECT
            breakdown_key,
            COALESCE(SUM(CAST(spend AS DOUBLE)), 0) AS spend,
            COALESCE(SUM(CAST(impressions AS BIGINT)), 0) AS impressions,
            COALESCE(SUM(CAST(clicks AS BIGINT)), 0) AS clicks,
            COALESCE(SUM(CAST(leads AS BIGINT)), 0) AS leads
        FROM {_CAMPAIGN_BREAKDOWNS_TABLE}
        WHERE {_campaign_breakdowns_where(org_id, date_from, date_to, campaign_id, breakdown_type)}
        GROUP BY breakdown_key
        ORDER BY spend DESC
    """
    rows = (await _execute_query(query)).rows
    return [
        BreakdownItem(
            breakdown_key=str(row.get("breakdown_key") or ""),
            spend=_float_value(row, "spend"),
            impressions=_int_value(row, "impressions"),
            clicks=_int_value(row, "clicks"),
            leads=_int_value(row, "leads"),
        )
        for row in rows
    ]


async def _ensure_tables_ready(table_names: list[str]) -> None:
    await _ensure_catalog_ready()
    await _sync_partitions_if_due(table_names)


async def force_sync_tables(table_names: list[str]) -> None:
    await _ensure_catalog_ready()
    await _sync_tables(table_names, force=True)


async def _ensure_catalog_ready() -> None:
    global _CATALOG_READY

    if not settings.olap_query_enabled:
        raise RuntimeError("OLAP query engine is disabled")

    schema_location = _olap_query_location(settings.olap_s3_uri)
    async with _CATALOG_LOCK:
        if not _CATALOG_READY:
            await _execute_query(
                f"CREATE SCHEMA IF NOT EXISTS {settings.trino_schema} WITH (location = {_sql_text(schema_location)})"
            )
            await _ensure_table_layouts(_bootstrap_table_statements())
            _CATALOG_READY = True


async def _execute_query(sql: str):
    return await get_query_adapter().execute(_compact_sql(sql))


async def _execute_queries(*sql_statements: str):
    return await get_query_adapter().execute_many(tuple(_compact_sql(sql) for sql in sql_statements))


async def _ensure_table_layouts(table_statements: dict[str, str]) -> None:
    for table_name, create_statement in table_statements.items():
        show_create = await _show_create_table(table_name)
        if show_create is None:
            await _execute_query(create_statement)
            continue

        if _table_layout_matches_expected(show_create, create_statement):
            continue

        await _execute_queries(
            f"DROP TABLE IF EXISTS {table_name}",
            create_statement,
        )
        _PARTITION_LAST_SYNC.pop(table_name, None)


async def _show_create_table(table_name: str) -> str | None:
    try:
        result = await _execute_query(f"SHOW CREATE TABLE {table_name}")
    except Exception:
        return None

    first_row = _first_row(result)
    if not first_row:
        return None
    return str(next(iter(first_row.values())))


def _table_layout_matches_expected(actual_ddl: str, expected_ddl: str) -> bool:
    return (
        _extract_partition_keys(actual_ddl) == _extract_partition_keys(expected_ddl)
        and _extract_external_location(actual_ddl) == _extract_external_location(expected_ddl)
    )


def _extract_partition_keys(ddl: str) -> tuple[str, ...]:
    match = re.search(r"partitioned_by\s*=\s*ARRAY\[(.*?)\]", ddl, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ()
    raw_items = match.group(1)
    items = []
    for part in raw_items.split(","):
        normalized = part.strip().strip("'").strip('"')
        if normalized:
            items.append(normalized)
    return tuple(items)


def _extract_external_location(ddl: str) -> str | None:
    match = re.search(r"external_location\s*=\s*'([^']+)'", ddl, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


async def _sync_partitions_if_due(table_names: list[str]) -> None:
    refresh_interval = settings.olap_partition_refresh_interval_seconds
    if refresh_interval < 0:
        refresh_interval = 0

    now = monotonic()
    due_tables = []
    for table_name in table_names:
        last_synced_at = _PARTITION_LAST_SYNC.get(table_name)
        if last_synced_at is None or (now - last_synced_at) >= refresh_interval:
            due_tables.append(table_name)

    if not due_tables:
        return

    await _sync_tables(due_tables, force=False)


async def _sync_tables(table_names: list[str], *, force: bool) -> None:
    refresh_interval = settings.olap_partition_refresh_interval_seconds

    async with _PARTITION_SYNC_LOCK:
        sync_now = monotonic()
        statements = []
        synced_tables = []
        for table_name in table_names:
            last_synced_at = _PARTITION_LAST_SYNC.get(table_name)
            if not force and last_synced_at is not None and (sync_now - last_synced_at) < refresh_interval:
                continue
            statements.append(
                f"CALL system.sync_partition_metadata(schema_name => {_sql_text(settings.trino_schema)}, table_name => {_sql_text(table_name)}, mode => 'ADD')"
            )
            synced_tables.append(table_name)

        if not statements:
            return

        await _execute_queries(*statements)
        completed_at = monotonic()
        for table_name in synced_tables:
            _PARTITION_LAST_SYNC[table_name] = completed_at


def _bootstrap_table_statements() -> dict[str, str]:
    bucket_root = _olap_query_location(settings.olap_s3_uri).rstrip("/")
    return {
        "daily_analytics": f"""
            CREATE TABLE IF NOT EXISTS daily_analytics (
                id VARCHAR,
                channel VARCHAR,
                new_conversations INTEGER,
                active_conversations INTEGER,
                total_messages INTEGER,
                avg_messages_per_conversation DOUBLE,
                avg_ai_response_time_ms INTEGER,
                conversions INTEGER,
                conversion_value DOUBLE,
                conversion_rate DOUBLE,
                ad_spend DOUBLE,
                cpa DOUBLE,
                roas DOUBLE,
                ai_tokens_used INTEGER,
                ai_cost DOUBLE,
                fallback_count INTEGER,
                created_at TIMESTAMP(6),
                updated_at TIMESTAMP(6),
                org_id VARCHAR,
                event_date DATE
            )
            WITH (
                external_location = {_sql_text(f'{bucket_root}/daily_analytics')},
                format = 'PARQUET',
                partitioned_by = ARRAY['event_date']
            )
        """,
        "daily_analytics_compact": f"""
            CREATE TABLE IF NOT EXISTS daily_analytics_compact (
                id VARCHAR,
                channel VARCHAR,
                new_conversations INTEGER,
                active_conversations INTEGER,
                total_messages INTEGER,
                avg_messages_per_conversation DOUBLE,
                avg_ai_response_time_ms INTEGER,
                conversions INTEGER,
                conversion_value DOUBLE,
                conversion_rate DOUBLE,
                ad_spend DOUBLE,
                cpa DOUBLE,
                roas DOUBLE,
                ai_tokens_used INTEGER,
                ai_cost DOUBLE,
                fallback_count INTEGER,
                created_at TIMESTAMP(6),
                updated_at TIMESTAMP(6),
                org_id VARCHAR,
                event_date DATE
            )
            WITH (
                external_location = {_sql_text(f'{bucket_root}/daily_analytics_compact')},
                format = 'PARQUET',
                partitioned_by = ARRAY['event_date']
            )
        """,
        "campaign_metrics": f"""
            CREATE TABLE IF NOT EXISTS campaign_metrics (
                id VARCHAR,
                level VARCHAR,
                meta_campaign_id VARCHAR,
                meta_campaign_name VARCHAR,
                meta_adset_id VARCHAR,
                meta_adset_name VARCHAR,
                meta_ad_id VARCHAR,
                meta_ad_name VARCHAR,
                status VARCHAR,
                spend DOUBLE,
                impressions BIGINT,
                clicks BIGINT,
                reach BIGINT,
                frequency DOUBLE,
                cpc DOUBLE,
                cpm DOUBLE,
                ctr DOUBLE,
                leads BIGINT,
                cost_per_lead DOUBLE,
                link_clicks BIGINT,
                landing_page_views BIGINT,
                video_views BIGINT,
                post_engagement BIGINT,
                messaging_conversations_started BIGINT,
                messaging_first_reply BIGINT,
                created_at TIMESTAMP(6),
                updated_at TIMESTAMP(6),
                org_id VARCHAR,
                event_date DATE
            )
            WITH (
                external_location = {_sql_text(f'{bucket_root}/campaign_metrics')},
                format = 'PARQUET',
                partitioned_by = ARRAY['event_date']
            )
        """,
        "campaign_metrics_agg": f"""
            CREATE TABLE IF NOT EXISTS campaign_metrics_agg (
                level VARCHAR,
                meta_campaign_id VARCHAR,
                meta_campaign_name VARCHAR,
                status VARCHAR,
                objective VARCHAR,
                spend DOUBLE,
                impressions BIGINT,
                clicks BIGINT,
                reach BIGINT,
                frequency DOUBLE,
                cpc DOUBLE,
                cpm DOUBLE,
                ctr DOUBLE,
                leads BIGINT,
                cost_per_lead DOUBLE,
                daily_budget DOUBLE,
                link_clicks BIGINT,
                landing_page_views BIGINT,
                video_views BIGINT,
                post_engagement BIGINT,
                messaging_conversations_started BIGINT,
                messaging_first_reply BIGINT,
                created_at TIMESTAMP(6),
                updated_at TIMESTAMP(6),
                org_id VARCHAR,
                event_date DATE
            )
            WITH (
                external_location = {_sql_text(f'{bucket_root}/campaign_metrics_agg')},
                format = 'PARQUET',
                partitioned_by = ARRAY['event_date']
            )
        """,
        "campaign_breakdowns": f"""
            CREATE TABLE IF NOT EXISTS campaign_breakdowns (
                id VARCHAR,
                meta_campaign_id VARCHAR,
                meta_adset_id VARCHAR,
                meta_ad_id VARCHAR,
                breakdown_type VARCHAR,
                breakdown_key VARCHAR,
                spend DOUBLE,
                impressions BIGINT,
                clicks BIGINT,
                leads BIGINT,
                created_at TIMESTAMP(6),
                updated_at TIMESTAMP(6),
                org_id VARCHAR,
                event_date DATE
            )
            WITH (
                external_location = {_sql_text(f'{bucket_root}/campaign_breakdowns')},
                format = 'PARQUET',
                partitioned_by = ARRAY['event_date']
            )
        """,
        "conversion_events": f"""
            CREATE TABLE IF NOT EXISTS conversion_events (
                id VARCHAR,
                subscriber_id VARCHAR,
                conversation_id VARCHAR,
                conversion_type VARCHAR,
                value DOUBLE,
                currency VARCHAR,
                ctwa_clid VARCHAR,
                capi_event_sent BOOLEAN,
                capi_event_id VARCHAR,
                capi_sent_at TIMESTAMP(6),
                meta_ad_id VARCHAR,
                meta_campaign_id VARCHAR,
                created_at TIMESTAMP(6),
                updated_at TIMESTAMP(6),
                org_id VARCHAR,
                event_date DATE
            )
            WITH (
                external_location = {_sql_text(f'{bucket_root}/conversion_events')},
                format = 'PARQUET',
                partitioned_by = ARRAY['event_date']
            )
        """,
        "ai_usage_events": f"""
            CREATE TABLE IF NOT EXISTS ai_usage_events (
                id VARCHAR,
                conversation_id VARCHAR,
                message_id VARCHAR,
                stage VARCHAR,
                model VARCHAR,
                input_tokens INTEGER,
                output_tokens INTEGER,
                cache_read_tokens INTEGER,
                cache_creation_tokens INTEGER,
                created_at TIMESTAMP(6),
                updated_at TIMESTAMP(6),
                org_id VARCHAR,
                event_date DATE
            )
            WITH (
                external_location = {_sql_text(f'{bucket_root}/ai_usage_events')},
                format = 'PARQUET',
                partitioned_by = ARRAY['event_date']
            )
        """,
        "ai_usage_events_agg": f"""
            CREATE TABLE IF NOT EXISTS ai_usage_events_agg (
                conversation_id VARCHAR,
                event_count INTEGER,
                input_tokens INTEGER,
                output_tokens INTEGER,
                cache_read_tokens INTEGER,
                cache_creation_tokens INTEGER,
                first_event_at TIMESTAMP(6),
                last_event_at TIMESTAMP(6),
                created_at TIMESTAMP(6),
                updated_at TIMESTAMP(6),
                org_id VARCHAR,
                event_date DATE
            )
            WITH (
                external_location = {_sql_text(f'{bucket_root}/ai_usage_events_agg')},
                format = 'PARQUET',
                partitioned_by = ARRAY['event_date']
            )
        """,
        "archived_messages": f"""
            CREATE TABLE IF NOT EXISTS archived_messages (
                id VARCHAR,
                conversation_id VARCHAR,
                sender VARCHAR,
                content VARCHAR,
                intent_signals ARRAY(VARCHAR),
                buyer_stage_at_time VARCHAR,
                compliance_flags ARRAY(VARCHAR),
                ai_model VARCHAR,
                ai_response_time_ms INTEGER,
                ai_tokens_used INTEGER,
                quick_replies ARRAY(VARCHAR),
                conversation_channel VARCHAR,
                conversation_status VARCHAR,
                created_at TIMESTAMP(6),
                updated_at TIMESTAMP(6),
                archived_at TIMESTAMP(6),
                archive_mode VARCHAR,
                org_id VARCHAR,
                event_date DATE
            )
            WITH (
                external_location = {_sql_text(f'{bucket_root}/archived_messages')},
                format = 'PARQUET',
                partitioned_by = ARRAY['event_date']
            )
        """,
        "archived_messages_agg": f"""
            CREATE TABLE IF NOT EXISTS archived_messages_agg (
                conversation_id VARCHAR,
                conversation_channel VARCHAR,
                conversation_status VARCHAR,
                message_count INTEGER,
                ai_message_count INTEGER,
                user_message_count INTEGER,
                total_ai_tokens_used INTEGER,
                avg_ai_response_time_ms DOUBLE,
                first_message_at TIMESTAMP(6),
                last_message_at TIMESTAMP(6),
                created_at TIMESTAMP(6),
                updated_at TIMESTAMP(6),
                org_id VARCHAR,
                event_date DATE
            )
            WITH (
                external_location = {_sql_text(f'{bucket_root}/archived_messages_agg')},
                format = 'PARQUET',
                partitioned_by = ARRAY['event_date']
            )
        """,
    }


def _olap_query_location(uri: str) -> str:
    if uri.startswith("s3://"):
        return f"s3a://{uri.removeprefix('s3://')}"
    return uri


def _daily_analytics_where(
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    *,
    channel: str | None = None,
    combined_only: bool = False,
    exclude_null_channel: bool = False,
) -> str:
    conditions = [
        f"org_id = {_sql_text(str(org_id))}",
        f"event_date >= DATE {_sql_text(date_from.isoformat())}",
        f"event_date <= DATE {_sql_text(date_to.isoformat())}",
    ]
    if channel and channel != "all":
        channel_value = _validated_channel(channel)
        conditions.append(f"channel = {_sql_text(channel_value)}")
    if combined_only:
        conditions.append("channel IS NULL")
    if exclude_null_channel:
        conditions.append("channel IS NOT NULL")
    return " AND ".join(conditions)


def _campaign_metrics_where(
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    level: str,
    *,
    campaign_id: str | None = None,
    adset_id: str | None = None,
) -> str:
    conditions = [
        f"org_id = {_sql_text(str(org_id))}",
        f"level = {_sql_text(level)}",
        f"event_date >= DATE {_sql_text(date_from.isoformat())}",
        f"event_date <= DATE {_sql_text(date_to.isoformat())}",
    ]
    if campaign_id is not None:
        conditions.append(f"meta_campaign_id = {_sql_text(campaign_id)}")
    if adset_id is not None:
        conditions.append(f"meta_adset_id = {_sql_text(adset_id)}")
    return " AND ".join(conditions)


def _campaign_breakdowns_where(
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    campaign_id: str,
    breakdown_type: str,
) -> str:
    return " AND ".join(
        [
            f"org_id = {_sql_text(str(org_id))}",
            f"meta_campaign_id = {_sql_text(campaign_id)}",
            f"breakdown_type = {_sql_text(breakdown_type)}",
            f"event_date >= DATE {_sql_text(date_from.isoformat())}",
            f"event_date <= DATE {_sql_text(date_to.isoformat())}",
        ]
    )


def _validated_channel(channel: str) -> str:
    try:
        return ChannelType(channel).value
    except ValueError:
        return channel


def _build_funnel_proxy(
    total_conversations: int,
    qualified_count: int,
    total_conversions: int,
) -> list[FunnelStep]:
    steps = [FunnelStep(name="conversations", volume=total_conversations, drop_off_rate=None)]
    drop_off_qualified = None
    if total_conversations > 0:
        drop_off_qualified = round(1 - (qualified_count / total_conversations), 4)
    steps.append(FunnelStep(name="qualified", volume=qualified_count, drop_off_rate=drop_off_qualified))

    drop_off_converted = None
    if qualified_count > 0:
        drop_off_converted = round(1 - (total_conversions / qualified_count), 4)
    steps.append(FunnelStep(name="converted", volume=total_conversions, drop_off_rate=drop_off_converted))
    return steps


def _campaign_summary_from_row(row: dict[str, Any]) -> CampaignSummary:
    return CampaignSummary(
        meta_campaign_id=str(row.get("meta_campaign_id") or ""),
        meta_campaign_name=_optional_str_value(row, "meta_campaign_name"),
        status=_optional_str_value(row, "status"),
        spend=_float_value(row, "spend"),
        impressions=_int_value(row, "impressions"),
        clicks=_int_value(row, "clicks"),
        leads=_int_value(row, "leads"),
        link_clicks=_int_value(row, "link_clicks"),
        video_views=_int_value(row, "video_views"),
        cpc=_optional_float_value(row, "cpc"),
        cpm=_optional_float_value(row, "cpm"),
        ctr=_optional_float_value(row, "ctr"),
    )


def _adset_summary_from_row(row: dict[str, Any]) -> AdSetSummary:
    return AdSetSummary(
        meta_adset_id=str(row.get("meta_adset_id") or ""),
        meta_adset_name=_optional_str_value(row, "meta_adset_name"),
        status=_optional_str_value(row, "status"),
        spend=_float_value(row, "spend"),
        impressions=_int_value(row, "impressions"),
        clicks=_int_value(row, "clicks"),
        leads=_int_value(row, "leads"),
        link_clicks=_int_value(row, "link_clicks"),
        video_views=_int_value(row, "video_views"),
        cpc=_optional_float_value(row, "cpc"),
        cpm=_optional_float_value(row, "cpm"),
        ctr=_optional_float_value(row, "ctr"),
    )


def _ad_summary_from_row(row: dict[str, Any]) -> AdSummary:
    return AdSummary(
        meta_ad_id=str(row.get("meta_ad_id") or ""),
        meta_ad_name=_optional_str_value(row, "meta_ad_name"),
        status=_optional_str_value(row, "status"),
        spend=_float_value(row, "spend"),
        impressions=_int_value(row, "impressions"),
        clicks=_int_value(row, "clicks"),
        leads=_int_value(row, "leads"),
        link_clicks=_int_value(row, "link_clicks"),
        video_views=_int_value(row, "video_views"),
        cpc=_optional_float_value(row, "cpc"),
        cpm=_optional_float_value(row, "cpm"),
        ctr=_optional_float_value(row, "ctr"),
    )


def _compact_sql(sql: str) -> str:
    return " ".join(line.strip() for line in sql.strip().splitlines() if line.strip())


def _sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _first_row(result) -> dict[str, Any]:
    return dict(result.rows[0]) if result.rows else {}


def _date_value(row: dict[str, Any], key: str) -> date:
    value = row.get(key)
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _int_value(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if value is None:
        return 0
    return int(float(value))


def _optional_int_value(row: dict[str, Any], key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None
    return int(float(value))


def _float_value(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if value is None:
        return 0.0
    return float(value)


def _optional_float_value(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    return float(value)


def _optional_str_value(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    return str(value)