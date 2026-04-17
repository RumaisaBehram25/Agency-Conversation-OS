import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import deps as api_deps
from app.api import olap as olap_api
from app.database import get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def client():
    test_user = User(
        id=uuid.uuid4(),
        email="owner@example.com",
        hashed_password="hashed",
        is_active=True,
    )
    test_user.created_at = datetime(2026, 4, 1, tzinfo=timezone.utc)
    org_id = uuid.uuid4()

    async def override_current_user():
        return test_user

    async def override_org_id():
        return org_id

    async def override_org_id_from_header():
        return org_id

    app.dependency_overrides[api_deps.get_current_user] = override_current_user
    app.dependency_overrides[api_deps.get_org_id] = override_org_id
    app.dependency_overrides[api_deps.get_org_id_from_header] = override_org_id_from_header

    with TestClient(app) as test_client:
        yield test_client, org_id

    app.dependency_overrides.clear()


class DummySession:
    async def commit(self):
        return None

    async def rollback(self):
        return None


def test_olap_dashboard_contract(client, monkeypatch):
    test_client, _ = client

    async def fake_dashboard(org_id):
        return {
            "cpqc": 12.5,
            "cpqc_trend": [{"date": date(2026, 4, 1), "value": 10.0}],
            "ccr": 0.24,
            "ccr_trend": [{"date": date(2026, 4, 1), "value": 0.2}],
            "active_conversations_count": 4,
            "todays_conversions": 2,
            "todays_revenue": 199.0,
            "campaign_health": [{"name": "messenger", "status": "green", "reason": "CPA $42.00"}],
        }

    monkeypatch.setattr(olap_api, "get_olap_dashboard_overview", fake_dashboard)

    response = test_client.get("/api/olap/dashboard")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {
        "cpqc", "cpqc_trend", "ccr", "ccr_trend", "active_conversations_count",
        "todays_conversions", "todays_revenue", "campaign_health",
    }


def test_olap_analytics_contracts(client, monkeypatch):
    test_client, _ = client

    async def fake_analytics(org_id, date_from, date_to, channel):
        return {
            "date_from": date_from,
            "date_to": date_to,
            "channel": channel,
            "cpqc": 10.0,
            "ccr": 0.1,
            "avg_response_time_ms": 350,
            "qualification_rate": 0.1,
            "total_conversations": 100,
            "total_conversions": 10,
            "total_revenue": 500.0,
            "funnel": [
                {"name": "conversations", "volume": 100, "drop_off_rate": None},
                {"name": "qualified", "volume": 100, "drop_off_rate": 0.0},
                {"name": "converted", "volume": 10, "drop_off_rate": 0.9},
            ],
            "cpqc_trend": [{"date": date(2026, 4, 1), "value": 8.5}],
            "ccr_trend": [{"date": date(2026, 4, 1), "value": 0.1}],
        }

    async def fake_roi(org_id, date_from, date_to):
        return {
            "date_from": date_from,
            "date_to": date_to,
            "ad_spend": 500.0,
            "conversations_count": 100,
            "cost_per_conversation": 5.0,
            "qualified_count": 100,
            "cost_per_qualified": 5.0,
            "converted_count": 10,
            "cpa": 50.0,
            "revenue": 900.0,
            "roas": 1.8,
            "baseline_cpa": 60.0,
            "current_cpa": 45.0,
            "baseline_roas": 1.2,
            "current_roas": 2.0,
        }

    async def fake_ai(org_id, date_from, date_to):
        return {
            "fallback_rate": 0.05,
            "fallback_trend": [{"date": date(2026, 4, 1), "value": 0.02}],
            "avg_response_time_ms": 400,
            "total_ai_tokens": 12000,
            "total_ai_cost": 4.25,
        }

    async def fake_export(org_id, date_from, date_to, channel):
        return [{
            "date": "2026-04-01",
            "channel": "all",
            "new_conversations": 10,
            "active_conversations": 12,
            "total_messages": 40,
            "avg_messages_per_conversation": 4.0,
            "avg_ai_response_time_ms": 350,
            "conversions": 2,
            "conversion_value": 99.0,
            "conversion_rate": 0.2,
            "ad_spend": 50.0,
            "cpa": 25.0,
            "roas": 1.98,
            "ai_tokens_used": 500,
            "ai_cost": 0.25,
            "fallback_count": 1,
        }]

    monkeypatch.setattr(olap_api, "get_olap_analytics", fake_analytics)
    monkeypatch.setattr(olap_api, "get_olap_roi", fake_roi)
    monkeypatch.setattr(olap_api, "get_olap_ai_performance", fake_ai)
    monkeypatch.setattr(olap_api, "get_olap_analytics_export_data", fake_export)

    analytics_response = test_client.get("/api/olap/analytics")
    assert analytics_response.status_code == 200
    assert set(analytics_response.json().keys()) == {
        "date_from", "date_to", "channel", "cpqc", "ccr", "avg_response_time_ms",
        "qualification_rate", "total_conversations", "total_conversions", "total_revenue",
        "funnel", "cpqc_trend", "ccr_trend",
    }

    roi_response = test_client.get("/api/olap/analytics/roi")
    assert roi_response.status_code == 200
    assert "roas" in roi_response.json()

    ai_response = test_client.get("/api/olap/analytics/ai-performance")
    assert ai_response.status_code == 200
    assert set(ai_response.json().keys()) == {
        "fallback_rate", "fallback_trend", "avg_response_time_ms", "total_ai_tokens", "total_ai_cost",
    }

    export_response = test_client.get("/api/olap/analytics/export")
    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("text/csv")
    assert "date,channel,new_conversations" in export_response.text


def test_olap_analytics_falls_back_to_postgres_when_olap_is_empty(client, monkeypatch):
    test_client, _ = client

    async def fake_olap_analytics(org_id, date_from, date_to, channel):
        return {
            "date_from": date_from,
            "date_to": date_to,
            "channel": channel,
            "cpqc": None,
            "ccr": None,
            "avg_response_time_ms": None,
            "qualification_rate": None,
            "total_conversations": 0,
            "total_conversions": 0,
            "total_revenue": 0.0,
            "funnel": [],
            "cpqc_trend": [],
            "ccr_trend": [],
        }

    async def fake_pg_analytics(db, org_id, date_from, date_to, channel):
        return {
            "date_from": date_from,
            "date_to": date_to,
            "channel": channel,
            "cpqc": 7.5,
            "ccr": 0.25,
            "avg_response_time_ms": 280,
            "qualification_rate": 0.25,
            "total_conversations": 40,
            "total_conversions": 10,
            "total_revenue": 400.0,
            "funnel": [{"name": "conversations", "volume": 40, "drop_off_rate": None}],
            "cpqc_trend": [{"date": date(2026, 4, 1), "value": 7.5}],
            "ccr_trend": [{"date": date(2026, 4, 1), "value": 0.25}],
        }

    monkeypatch.setattr(olap_api, "get_olap_analytics", fake_olap_analytics)
    monkeypatch.setattr(olap_api, "get_analytics", fake_pg_analytics)

    async def override_db():
        yield DummySession()

    app.dependency_overrides[get_db] = override_db

    response = test_client.get("/api/olap/analytics")

    assert response.status_code == 200
    assert response.json()["total_conversations"] == 40

    app.dependency_overrides.pop(get_db, None)


def test_olap_campaign_contracts(client, monkeypatch):
    test_client, _ = client

    async def fake_list_campaigns(org_id, date_from, date_to):
        return [{
            "meta_campaign_id": "cmp_1",
            "meta_campaign_name": "Campaign 1",
            "status": "ACTIVE",
            "spend": 100.0,
            "impressions": 1000,
            "clicks": 50,
            "leads": 5,
            "link_clicks": 20,
            "video_views": 200,
            "cpc": 2.0,
            "cpm": 10.0,
            "ctr": 0.05,
        }]

    async def fake_campaign_detail(org_id, campaign_id, date_from, date_to):
        return [{
            "date": date(2026, 4, 1),
            "spend": 100.0,
            "impressions": 1000,
            "clicks": 50,
            "leads": 5,
            "cpc": 2.0,
            "cpm": 10.0,
            "ctr": 0.05,
            "reach": 800,
            "frequency": 1.2,
        }]

    async def fake_adsets(org_id, campaign_id, date_from, date_to):
        return [{
            "meta_adset_id": "adset_1",
            "meta_adset_name": "Adset 1",
            "status": "ACTIVE",
            "spend": 70.0,
            "impressions": 800,
            "clicks": 40,
            "leads": 4,
            "link_clicks": 15,
            "video_views": 150,
            "cpc": 1.75,
            "cpm": 8.75,
            "ctr": 0.05,
        }]

    async def fake_ads(org_id, campaign_id, adset_id, date_from, date_to):
        return [{
            "meta_ad_id": "ad_1",
            "meta_ad_name": "Ad 1",
            "status": "ACTIVE",
            "spend": 35.0,
            "impressions": 400,
            "clicks": 18,
            "leads": 2,
            "link_clicks": 9,
            "video_views": 75,
            "cpc": 1.94,
            "cpm": 8.75,
            "ctr": 0.045,
        }]

    async def fake_breakdowns(org_id, campaign_id, breakdown_type, date_from, date_to):
        return [{
            "breakdown_key": "25-34_female",
            "spend": 50.0,
            "impressions": 400,
            "clicks": 20,
            "leads": 2,
        }]

    monkeypatch.setattr(olap_api, "list_olap_campaigns", fake_list_campaigns)
    monkeypatch.setattr(olap_api, "get_olap_campaign_detail", fake_campaign_detail)
    monkeypatch.setattr(olap_api, "list_olap_adsets", fake_adsets)
    monkeypatch.setattr(olap_api, "list_olap_ads", fake_ads)
    monkeypatch.setattr(olap_api, "get_olap_campaign_breakdowns", fake_breakdowns)

    assert test_client.get("/api/olap/campaigns").json()[0]["meta_campaign_id"] == "cmp_1"
    assert test_client.get("/api/olap/campaigns/cmp_1").json()[0]["spend"] == 100.0
    assert test_client.get("/api/olap/campaigns/cmp_1/adsets").json()[0]["meta_adset_id"] == "adset_1"
    assert test_client.get("/api/olap/campaigns/cmp_1/adsets/adset_1/ads").json()[0]["meta_ad_id"] == "ad_1"
    assert test_client.get("/api/olap/campaigns/cmp_1/breakdowns?type=age_gender").json()[0]["breakdown_key"] == "25-34_female"


def test_olap_job_trigger_contract(client, monkeypatch):
    test_client, _ = client

    async def fake_run_job(db, job_name, **kwargs):
        return {"status": "ok", "job_name": job_name, "kwargs": kwargs}

    monkeypatch.setattr(olap_api, "run_olap_job", fake_run_job)

    async def override_db():
        yield DummySession()

    app.dependency_overrides[get_db] = override_db

    response = test_client.post(
        "/api/olap/jobs/trigger",
        json={
            "job": "export_campaign_facts",
            "date_from": "2026-04-01",
            "date_to": "2026-04-07",
            "delta_days": 14,
            "limit": 25,
            "use_checkpoint": False,
            "export_all": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"] == "export_campaign_facts"
    assert payload["result"]["status"] == "ok"
    assert payload["result"]["kwargs"]["use_checkpoint"] is False
    assert payload["result"]["kwargs"]["date_from"] == "2026-04-01"
    assert payload["result"]["kwargs"]["date_to"] == "2026-04-07"
    assert payload["result"]["kwargs"]["delta_days"] == 14
    assert payload["result"]["kwargs"]["limit"] == 25
    assert payload["result"]["kwargs"]["export_all"] is True

    app.dependency_overrides.pop(get_db, None)


def test_olap_seed_test_data_contract(client, monkeypatch):
    test_client, org_id = client

    async def fake_ensure_access(db, *, user_id, org_id):
        return None

    async def fake_seed(db, params):
        assert params.org_id == org_id
        assert params.date_from == date(2026, 3, 1)
        assert params.date_to == date(2026, 3, 15)
        return SimpleNamespace(
            organizations=1,
            days=15,
            daily_created=60,
            daily_updated=0,
            campaign_created=315,
            campaign_updated=0,
            breakdown_created=90,
            breakdown_updated=0,
        )

    monkeypatch.setattr(olap_api, "_ensure_org_admin_access", fake_ensure_access)
    monkeypatch.setattr(olap_api, "seed_olap_test_data", fake_seed)

    async def override_db():
        yield DummySession()

    app.dependency_overrides[get_db] = override_db

    response = test_client.post(
        "/api/olap/jobs/seed-test-data",
        json={
            "date_from": "2026-03-01",
            "date_to": "2026-03-15",
            "replace_existing": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["org_id"] == str(org_id)
    assert payload["date_from"] == "2026-03-01"
    assert payload["date_to"] == "2026-03-15"
    assert payload["replace_existing"] is True
    assert payload["result"]["organizations"] == 1
    assert payload["result"]["org_days_processed"] == 15

    app.dependency_overrides.pop(get_db, None)