from datetime import date, datetime, timezone
import uuid

import pytest

from app.jobs import scheduler


@pytest.mark.asyncio
async def test_run_olap_job_manual_daily_analytics_export(monkeypatch):
    captured = {}

    async def fake_export_daily_analytics_to_olap(session, *, date_from, date_to, org_id=None):
        captured["date_from"] = date_from
        captured["date_to"] = date_to
        captured["org_id"] = org_id
        return {"status": "ok"}

    monkeypatch.setattr(scheduler, "export_daily_analytics_to_olap", fake_export_daily_analytics_to_olap)

    org_id = uuid.uuid4()
    result = await scheduler.run_olap_job(
        object(),
        "export_daily_analytics",
        org_id=org_id,
        date_from=date(2026, 4, 1),
        date_to=date(2026, 4, 7),
        use_checkpoint=False,
    )

    assert result == {"status": "ok"}
    assert captured == {
        "date_from": date(2026, 4, 1),
        "date_to": date(2026, 4, 7),
        "org_id": org_id,
    }


@pytest.mark.asyncio
async def test_run_olap_job_export_all_daily_analytics(monkeypatch):
    captured = {}

    async def fake_resolve_window(session, *, dataset_name, org_id):
        captured["dataset_name"] = dataset_name
        captured["org_id"] = org_id
        return date(2026, 4, 1), date(2026, 4, 30)

    async def fake_export_daily_analytics_to_olap(session, *, date_from, date_to, org_id=None):
        captured["date_from"] = date_from
        captured["date_to"] = date_to
        return {"status": "ok"}

    monkeypatch.setattr(scheduler, "_resolve_export_all_date_window", fake_resolve_window)
    monkeypatch.setattr(scheduler, "export_daily_analytics_to_olap", fake_export_daily_analytics_to_olap)

    org_id = uuid.uuid4()
    result = await scheduler.run_olap_job(
        object(),
        "export_daily_analytics",
        org_id=org_id,
        export_all=True,
    )

    assert result == {"status": "ok"}
    assert captured == {
        "dataset_name": "daily_analytics",
        "org_id": org_id,
        "date_from": date(2026, 4, 1),
        "date_to": date(2026, 4, 30),
    }


@pytest.mark.asyncio
async def test_run_olap_job_manual_ai_usage_export_with_target_date(monkeypatch):
    captured = {}

    async def fake_export_ai_usage_events_to_olap(session, *, target_date=None, org_id=None, start_at=None, end_at=None):
        captured["target_date"] = target_date
        captured["org_id"] = org_id
        captured["start_at"] = start_at
        captured["end_at"] = end_at
        return {"status": "ok"}

    monkeypatch.setattr(scheduler, "export_ai_usage_events_to_olap", fake_export_ai_usage_events_to_olap)

    org_id = uuid.uuid4()
    result = await scheduler.run_olap_job(
        object(),
        "export_ai_usage",
        org_id=org_id,
        target_date=date(2026, 4, 3),
        use_checkpoint=False,
    )

    assert result == {"status": "ok"}
    assert captured["target_date"] == date(2026, 4, 3)
    assert captured["org_id"] == org_id
    assert captured["start_at"] == datetime(2026, 4, 3, 0, 0, tzinfo=timezone.utc)
    assert captured["end_at"] == datetime(2026, 4, 3, 23, 59, 59, 999999, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_run_olap_job_manual_campaign_export(monkeypatch):
    captured = {}

    async def fake_export_campaign_facts_to_olap(session, org_id, date_from, date_to):
        captured["org_id"] = org_id
        captured["date_from"] = date_from
        captured["date_to"] = date_to
        return {"status": "ok"}

    monkeypatch.setattr(scheduler, "export_campaign_facts_to_olap", fake_export_campaign_facts_to_olap)

    org_id = uuid.uuid4()
    result = await scheduler.run_olap_job(
        object(),
        "export_campaign_facts",
        org_id=org_id,
        date_from=date(2026, 4, 1),
        date_to=date(2026, 4, 7),
    )

    assert result == {"status": "ok"}
    assert captured == {
        "org_id": org_id,
        "date_from": date(2026, 4, 1),
        "date_to": date(2026, 4, 7),
    }


def test_resolve_date_window_rejects_inverted_range():
    with pytest.raises(ValueError, match="date_from must be on or before date_to"):
        scheduler._resolve_date_window(
            date_from=date(2026, 4, 7),
            date_to=date(2026, 4, 1),
            delta_days=None,
        )