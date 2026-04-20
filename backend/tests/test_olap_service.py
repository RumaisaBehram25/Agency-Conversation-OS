from datetime import date

import pytest

from app.olap.query import QueryResult
from app.services import olap_service


@pytest.mark.asyncio
async def test_ensure_tables_ready_throttles_partition_sync(monkeypatch):
    calls: list[tuple[str, ...]] = []

    async def fake_execute_queries(*sql_statements: str):
        calls.append(sql_statements)
        return tuple(QueryResult(columns=(), rows=(), row_count=0) for _ in sql_statements)

    monkeypatch.setattr(olap_service.settings, "olap_query_provider", "trino")
    monkeypatch.setattr(olap_service.settings, "olap_partition_refresh_interval_seconds", 300)
    monkeypatch.setattr(olap_service, "_execute_queries", fake_execute_queries)

    olap_service._CATALOG_READY = False
    olap_service._PARTITION_LAST_SYNC.clear()

    await olap_service._ensure_tables_ready([olap_service._DAILY_ANALYTICS_TABLE])
    await olap_service._ensure_tables_ready([olap_service._DAILY_ANALYTICS_TABLE])

    sync_statements = [
        sql
        for batch in calls
        for sql in batch
        if "sync_partition_metadata" in sql
    ]
    assert len(sync_statements) == 1


@pytest.mark.asyncio
async def test_ensure_catalog_ready_rebuilds_stale_partition_layout(monkeypatch):
    executed_queries: list[str] = []
    executed_batches: list[tuple[str, ...]] = []

    async def fake_execute_query(sql: str):
        executed_queries.append(sql)
        if sql.startswith("SHOW CREATE TABLE daily_analytics_compact"):
            return QueryResult(
                columns=("Create Table",),
                rows=(
                    {
                        "Create Table": """
CREATE TABLE lakehouse.default.daily_analytics_compact (
   id varchar,
   event_date date,
   org_id varchar
)
WITH (
   external_location = 's3a://attora-analytics/attora-lake/daily_analytics_compact',
   format = 'PARQUET',
   partitioned_by = ARRAY['org_id']
)""",
                    },
                ),
                row_count=1,
            )
        if sql.startswith("SHOW CREATE TABLE"):
            raise RuntimeError("table does not exist")
        return QueryResult(columns=(), rows=(), row_count=0)

    async def fake_execute_queries(*sql_statements: str):
        executed_batches.append(sql_statements)
        return tuple(QueryResult(columns=(), rows=(), row_count=0) for _ in sql_statements)

    monkeypatch.setattr(olap_service.settings, "olap_query_provider", "trino")
    monkeypatch.setattr(olap_service, "_execute_query", fake_execute_query)
    monkeypatch.setattr(olap_service, "_execute_queries", fake_execute_queries)

    olap_service._CATALOG_READY = False

    await olap_service._ensure_catalog_ready()

    assert any(sql.startswith("CREATE SCHEMA IF NOT EXISTS") for sql in executed_queries)
    assert any(
        batch[0] == "DROP TABLE IF EXISTS daily_analytics_compact"
        and "CREATE TABLE IF NOT EXISTS daily_analytics_compact" in batch[1]
        for batch in executed_batches
    )


@pytest.mark.asyncio
async def test_get_olap_analytics_batches_related_queries(monkeypatch):
    batches: list[tuple[str, ...]] = []

    async def fake_ensure_tables_ready(table_names: list[str]):
        assert table_names == [olap_service._DAILY_ANALYTICS_TABLE]

    async def fake_execute_queries(*sql_statements: str):
        batches.append(sql_statements)
        return (
            QueryResult(
                columns=(
                    "total_conversations",
                    "total_conversions",
                    "total_revenue",
                    "total_ad_spend",
                    "avg_response_time_ms",
                ),
                rows=(
                    {
                        "total_conversations": 10,
                        "total_conversions": 2,
                        "total_revenue": 100.0,
                        "total_ad_spend": 50.0,
                        "avg_response_time_ms": 320,
                    },
                ),
                row_count=1,
            ),
            QueryResult(
                columns=("trend_date", "ad_spend", "conversations"),
                rows=({"trend_date": date(2026, 4, 1), "ad_spend": 50.0, "conversations": 10},),
                row_count=1,
            ),
            QueryResult(
                columns=("trend_date", "conversions", "conversations"),
                rows=({"trend_date": date(2026, 4, 1), "conversions": 2, "conversations": 10},),
                row_count=1,
            ),
        )

    monkeypatch.setattr(olap_service, "_ensure_tables_ready", fake_ensure_tables_ready)
    monkeypatch.setattr(olap_service, "_execute_queries", fake_execute_queries)

    response = await olap_service.get_olap_analytics(
        org_id="57be9d82-4c25-4092-b52d-5302a7459b21",
        date_from=date(2026, 4, 1),
        date_to=date(2026, 4, 1),
        channel=None,
    )

    assert len(batches) == 1
    assert len(batches[0]) == 3
    assert response.total_conversations == 10
    assert response.cpqc == 5.0
    assert response.ccr == 0.2


@pytest.mark.asyncio
async def test_list_olap_campaigns_reads_aggregate_table(monkeypatch):
    queries: list[str] = []

    async def fake_ensure_tables_ready(table_names: list[str]):
        assert table_names == [olap_service._CAMPAIGN_METRICS_AGG_TABLE]

    async def fake_execute_query(sql: str):
        queries.append(sql)
        return QueryResult(
            columns=(
                "meta_campaign_id",
                "meta_campaign_name",
                "status",
                "spend",
                "impressions",
                "clicks",
                "leads",
                "link_clicks",
                "video_views",
                "cpc",
                "cpm",
                "ctr",
            ),
            rows=(
                {
                    "meta_campaign_id": "cmp_1",
                    "meta_campaign_name": "Campaign 1",
                    "status": "ACTIVE",
                    "spend": 120.0,
                    "impressions": 1000,
                    "clicks": 45,
                    "leads": 5,
                    "link_clicks": 20,
                    "video_views": 300,
                    "cpc": 2.67,
                    "cpm": 12.0,
                    "ctr": 0.045,
                },
            ),
            row_count=1,
        )

    monkeypatch.setattr(olap_service, "_ensure_tables_ready", fake_ensure_tables_ready)
    monkeypatch.setattr(olap_service, "_execute_query", fake_execute_query)

    response = await olap_service.list_olap_campaigns(
        org_id="57be9d82-4c25-4092-b52d-5302a7459b21",
        date_from=date(2026, 4, 1),
        date_to=date(2026, 4, 30),
    )

    assert len(queries) == 1
    assert olap_service._CAMPAIGN_METRICS_AGG_TABLE in queries[0]
    assert response[0].meta_campaign_id == "cmp_1"