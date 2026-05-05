import uuid
from collections import deque
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import deps as api_deps
from app.api import analytics as analytics_api
from app.api import auth as auth_api
from app.api import dashboard as dashboard_api
from app.api import campaigns as campaigns_api
from app.database import get_db
from app.main import app
from app.models.base import BuyerStage, ChannelType, ConversationStatus, MessageSender, UserRole
from app.models.product import Product
from app.models.user import User


class FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class FakeResult:
    def __init__(self, *, scalar=None, scalars=None, all_rows=None):
        self._scalar = scalar
        self._scalars = scalars if scalars is not None else []
        self._all_rows = all_rows if all_rows is not None else []

    def scalar_one_or_none(self):
        return self._scalar

    def scalar(self):
        return self._scalar

    def scalars(self):
        return FakeScalars(self._scalars)

    def all(self):
        return self._all_rows

    def __iter__(self):
        """SQLAlchemy `Result` is iterable for streaming rows (e.g. subqueries)."""
        return iter(self._all_rows)


class QueueSession:
    def __init__(self, results=None):
        self._results = deque(results or [])
        self.added = []
        self.deleted = []

    async def execute(self, query):
        if not self._results:
            raise AssertionError(f"Unexpected query with no queued result: {query}")
        return self._results.popleft()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            _hydrate_model(obj)

    async def refresh(self, obj):
        _hydrate_model(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        return None

    async def rollback(self):
        return None


def _hydrate_model(obj):
    now = datetime.now(timezone.utc)
    if getattr(obj, "id", None) is None:
        obj.id = uuid.uuid4()
    if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
        obj.created_at = now
    if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
        obj.updated_at = now


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

    app.dependency_overrides[api_deps.get_current_user] = override_current_user
    app.dependency_overrides[api_deps.get_org_id] = override_org_id

    with TestClient(app) as test_client:
        yield test_client, test_user, org_id

    app.dependency_overrides.clear()


def test_dashboard_contract(client, monkeypatch):
    test_client, _, _ = client

    async def fake_dashboard(db, org_id):
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

    monkeypatch.setattr(dashboard_api, "get_dashboard_overview", fake_dashboard)

    async def override_db():
        yield QueueSession()

    app.dependency_overrides[get_db] = override_db
    response = test_client.get("/api/dashboard")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {
        "cpqc", "cpqc_trend", "ccr", "ccr_trend", "active_conversations_count",
        "todays_conversions", "todays_revenue", "campaign_health",
    }
    app.dependency_overrides.pop(get_db, None)


def test_analytics_contracts(client, monkeypatch):
    test_client, _, _ = client

    async def fake_analytics(
        db,
        org_id,
        date_from,
        date_to,
        channel,
        campaign_id=None,
        attora_campaign_id=None,
        source_type=None,
    ):
        return {
            "date_from": date_from,
            "date_to": date_to,
            "channel": channel,
            "cpqc": 12.0,
            "ccr": 0.12,
            "avg_response_time_ms": 350,
            "qualification_rate": 0.3,
            "hyros_confirmed_purchases": 0,
            "cost_per_purchase": None,
            "cost_per_conversation": None,
            "purchases_count": 0,
            "conversations_count": 0,
            "total_conversations": 100,
            "total_conversions": 12,
            "total_revenue": 950.0,
            "funnel": [{"name": "conversations", "volume": 100, "drop_off_rate": None}],
            "cpqc_trend": [{"date": date(2026, 4, 1), "value": 10.0}],
            "ccr_trend": [{"date": date(2026, 4, 1), "value": 0.1}],
            "purchases_over_time": [],
            "organic_posts": [],
        }

    async def fake_roi(
        db,
        org_id,
        date_from,
        date_to,
        campaign_id=None,
        attora_campaign_id=None,
        source_type=None,
    ):
        return {
            "date_from": date_from,
            "date_to": date_to,
            "ad_spend": 500.0,
            "conversations_count": 100,
            "cost_per_conversation": 5.0,
            "qualified_count": 40,
            "cost_per_qualified": 12.5,
            "converted_count": 12,
            "cpa": 41.67,
            "revenue": 950.0,
            "roas": 1.9,
            "baseline_cpa": 45.0,
            "current_cpa": 39.0,
            "baseline_roas": 1.4,
            "current_roas": 2.1,
        }

    async def fake_ai_performance(db, org_id, date_from, date_to):
        return {
            "fallback_rate": 0.05,
            "fallback_trend": [{"date": date(2026, 4, 1), "value": 0.02}],
            "avg_response_time_ms": 400,
            "total_ai_tokens": 12000,
            "total_ai_cost": 4.25,
        }

    async def fake_export_data(db, org_id, date_from, date_to, channel):
        return [{
            "date": "2026-04-01",
            "channel": "messenger",
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

    monkeypatch.setattr(analytics_api, "get_analytics", fake_analytics)
    monkeypatch.setattr(analytics_api, "get_roi", fake_roi)
    monkeypatch.setattr(analytics_api, "get_ai_performance", fake_ai_performance)
    monkeypatch.setattr(analytics_api, "get_analytics_export_data", fake_export_data)

    async def override_db():
        yield QueueSession()

    app.dependency_overrides[get_db] = override_db

    analytics_response = test_client.get("/api/analytics")
    assert analytics_response.status_code == 200
    assert set(analytics_response.json().keys()) == {
        "date_from",
        "date_to",
        "channel",
        "cpqc",
        "ccr",
        "avg_response_time_ms",
        "qualification_rate",
        "hyros_confirmed_purchases",
        "cost_per_purchase",
        "cost_per_conversation",
        "purchases_count",
        "conversations_count",
        "total_conversations",
        "total_conversions",
        "total_revenue",
        "funnel",
        "cpqc_trend",
        "ccr_trend",
        "purchases_over_time",
        "organic_posts",
    }

    roi_response = test_client.get("/api/analytics/roi")
    assert roi_response.status_code == 200
    assert "roas" in roi_response.json()

    ai_response = test_client.get("/api/analytics/ai-performance")
    assert ai_response.status_code == 200
    assert set(ai_response.json().keys()) == {
        "fallback_rate", "fallback_trend", "avg_response_time_ms", "total_ai_tokens", "total_ai_cost",
    }

    export_response = test_client.get("/api/analytics/export")
    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("text/csv")
    assert "date,channel,new_conversations" in export_response.text

    app.dependency_overrides.pop(get_db, None)


def test_campaign_contracts(client):
    test_client, _, _ = client
    campaign_row = SimpleNamespace(
        meta_campaign_id="cmp_1",
        meta_campaign_name="Campaign 1",
        source_type="paid",
        status="ACTIVE",
        daily_budget=None,
        spend=100.0,
        impressions=1000,
        clicks=50,
        leads=5,
        link_clicks=20,
        video_views=200,
        post_engagement=0,
        cpc=2.0,
        cpm=10.0,
        ctr=0.05,
    )
    adset_row = SimpleNamespace(
        meta_adset_id="adset_1",
        meta_adset_name="Adset 1",
        status="ACTIVE",
        spend=70.0,
        impressions=800,
        clicks=40,
        leads=4,
        link_clicks=15,
        video_views=150,
        cpc=1.75,
        cpm=8.75,
        ctr=0.05,
    )
    ad_row = SimpleNamespace(
        meta_ad_id="ad_1",
        meta_ad_name="Ad 1",
        status="ACTIVE",
        spend=35.0,
        impressions=400,
        clicks=18,
        leads=2,
        link_clicks=9,
        video_views=75,
        cpc=1.94,
        cpm=8.75,
        ctr=0.045,
    )
    breakdown_row = SimpleNamespace(breakdown_key="25-34_female", spend=50.0, impressions=400, clicks=20, leads=2)
    fake_db = QueueSession([
        FakeResult(all_rows=[campaign_row]),
        FakeResult(all_rows=[adset_row]),
        FakeResult(all_rows=[ad_row]),
        FakeResult(all_rows=[breakdown_row]),
    ])

    async def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db

    assert test_client.get("/api/campaign-metrics").json()[0]["meta_campaign_id"] == "cmp_1"
    assert test_client.get("/api/campaign-metrics/cmp_1/adsets").json()[0]["meta_adset_id"] == "adset_1"
    assert test_client.get("/api/campaign-metrics/cmp_1/adsets/adset_1/ads").json()[0]["meta_ad_id"] == "ad_1"
    assert test_client.get("/api/campaign-metrics/cmp_1/breakdowns?type=age_gender").json()[0]["breakdown_key"] == "25-34_female"

    app.dependency_overrides.pop(get_db, None)


def test_root_reporting_endpoints_ignore_olap_flag(client, monkeypatch):
    test_client, _, _ = client

    async def fake_dashboard(db, org_id):
        return {
            "cpqc": 11.0,
            "cpqc_trend": [{"date": date(2026, 4, 1), "value": 11.0}],
            "ccr": 0.22,
            "ccr_trend": [{"date": date(2026, 4, 1), "value": 0.22}],
            "active_conversations_count": 3,
            "todays_conversions": 1,
            "todays_revenue": 88.0,
            "campaign_health": [{"name": "messenger", "status": "green", "reason": "OK"}],
        }

    async def fake_analytics(
        db,
        org_id,
        date_from,
        date_to,
        channel,
        campaign_id=None,
        attora_campaign_id=None,
        source_type=None,
    ):
        return {
            "date_from": date_from,
            "date_to": date_to,
            "channel": channel,
            "cpqc": 9.0,
            "ccr": 0.15,
            "avg_response_time_ms": 320,
            "qualification_rate": 0.15,
            "hyros_confirmed_purchases": 0,
            "cost_per_purchase": None,
            "cost_per_conversation": None,
            "purchases_count": 0,
            "conversations_count": 0,
            "total_conversations": 20,
            "total_conversions": 3,
            "total_revenue": 150.0,
            "funnel": [{"name": "conversations", "volume": 20, "drop_off_rate": None}],
            "cpqc_trend": [{"date": date(2026, 4, 1), "value": 9.0}],
            "ccr_trend": [{"date": date(2026, 4, 1), "value": 0.15}],
            "purchases_over_time": [],
            "organic_posts": [],
        }

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Root APIs must not call OLAP services")

    monkeypatch.setattr(dashboard_api, "get_dashboard_overview", fake_dashboard)
    monkeypatch.setattr(analytics_api, "get_analytics", fake_analytics)
    monkeypatch.setattr(dashboard_api, "get_olap_dashboard_overview", fail_if_called, raising=False)
    monkeypatch.setattr(analytics_api, "get_olap_analytics", fail_if_called, raising=False)
    monkeypatch.setattr(analytics_api, "get_olap_roi", fail_if_called, raising=False)
    monkeypatch.setattr(analytics_api, "get_olap_ai_performance", fail_if_called, raising=False)
    monkeypatch.setattr(analytics_api, "get_olap_analytics_export_data", fail_if_called, raising=False)
    monkeypatch.setattr(campaigns_api, "list_olap_campaigns", fail_if_called, raising=False)
    monkeypatch.setattr(campaigns_api, "get_olap_campaign_detail", fail_if_called, raising=False)
    monkeypatch.setattr(campaigns_api, "list_olap_adsets", fail_if_called, raising=False)
    monkeypatch.setattr(campaigns_api, "list_olap_ads", fail_if_called, raising=False)
    monkeypatch.setattr(campaigns_api, "get_olap_campaign_breakdowns", fail_if_called, raising=False)

    async def override_db():
        yield QueueSession([FakeResult(all_rows=[])])

    app.dependency_overrides[get_db] = override_db

    dashboard_response = test_client.get("/api/dashboard")
    analytics_response = test_client.get("/api/analytics")
    campaigns_response = test_client.get("/api/campaigns")

    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["cpqc"] == 11.0
    assert analytics_response.status_code == 200
    assert analytics_response.json()["total_conversations"] == 20
    assert campaigns_response.status_code == 200
    assert campaigns_response.json() == []

    app.dependency_overrides.pop(get_db, None)


def test_conversation_contracts(client):
    test_client, _, _ = client
    subscriber = SimpleNamespace(first_name="Jane", last_name="Doe", buyer_stage=BuyerStage.AWARENESS)
    conversation = SimpleNamespace(
        id=uuid.uuid4(),
        subscriber_id=uuid.uuid4(),
        subscriber=subscriber,
        channel=ChannelType.MESSENGER,
        status=ConversationStatus.ACTIVE,
        message_count=3,
        started_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        last_activity_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    detail_message = SimpleNamespace(
        id=uuid.uuid4(),
        sender=MessageSender.AI,
        content="Hello there",
        intent_signals=["question"],
        buyer_stage_at_time=BuyerStage.CONSIDERATION,
        compliance_flags=None,
        ai_model="claude",
        ai_response_time_ms=420,
        ai_tokens_used=120,
        quick_replies=["Yes"],
        created_at=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
    )
    detail_conv = SimpleNamespace(
        id=conversation.id,
        subscriber_id=conversation.subscriber_id,
        channel=ChannelType.MESSENGER,
        status=ConversationStatus.ACTIVE,
        summary=None,
        message_count=1,
        ai_response_time_avg_ms=420,
        started_at=conversation.started_at,
        last_activity_at=conversation.last_activity_at,
        closed_at=None,
        created_at=conversation.created_at,
        updated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        subscriber=SimpleNamespace(
            id=conversation.subscriber_id,
            first_name="Jane",
            last_name="Doe",
            channel=ChannelType.MESSENGER,
            buyer_stage=BuyerStage.AWARENESS,
        ),
        messages=[detail_message],
    )
    latest_preview_row = SimpleNamespace(
        conversation_id=conversation.id,
        content="Latest message preview",
    )
    fake_db = QueueSession([
        FakeResult(scalar=1),
        FakeResult(scalars=[conversation]),
        FakeResult(all_rows=[latest_preview_row]),
        FakeResult(scalar=detail_conv),
    ])

    async def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    list_response = test_client.get("/api/conversations")
    assert list_response.status_code == 200
    assert set(list_response.json().keys()) == {"items", "total", "page", "page_size"}

    detail_response = test_client.get(f"/api/conversations/{conversation.id}")
    assert detail_response.status_code == 200
    assert "messages" in detail_response.json()
    app.dependency_overrides.pop(get_db, None)


def test_subscriber_contracts(client):
    test_client, _, _ = client
    subscriber = SimpleNamespace(
        id=uuid.uuid4(),
        first_name="Jane",
        last_name="Doe",
        channel=ChannelType.INSTAGRAM,
        buyer_stage=BuyerStage.CONSIDERATION,
        is_converted=False,
        conversion_value=None,
        total_messages=5,
        first_message_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        last_message_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        utm_source=None,
        utm_medium=None,
        utm_campaign=None,
        utm_content=None,
        hyros_purchased=False,
        hyros_product=None,
        hyros_synced_at=None,
    )
    detail_subscriber = SimpleNamespace(
        id=subscriber.id,
        manychat_subscriber_id="mc-1",
        channel=ChannelType.INSTAGRAM,
        first_name="Jane",
        last_name="Doe",
        phone=None,
        email=None,
        buyer_stage=BuyerStage.CONSIDERATION,
        interests=["glp-1"],
        objections_raised=["price"],
        conversation_summary="Summary",
        is_converted=False,
        conversion_value=None,
        converted_at=None,
        first_message_at=subscriber.first_message_at,
        last_message_at=subscriber.last_message_at,
        total_messages=5,
        created_at=subscriber.created_at,
        updated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        utm_source=None,
        utm_medium=None,
        utm_campaign=None,
        utm_content=None,
        hyros_purchased=False,
        hyros_product=None,
        hyros_purchase_date=None,
        hyros_lead_id=None,
        hyros_email=None,
        hyros_origin_source=None,
        hyros_origin_tag=None,
        hyros_traffic_source=None,
        hyros_creative_name=None,
        hyros_synced_at=None,
        conversations=[
            SimpleNamespace(
                id=uuid.uuid4(),
                channel=ChannelType.INSTAGRAM,
                status=ConversationStatus.ACTIVE,
                message_count=5,
                started_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                last_activity_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
                created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            )
        ],
    )
    fake_db = QueueSession([
        FakeResult(scalar=1),
        FakeResult(scalars=[subscriber]),
        FakeResult(scalar=detail_subscriber),
    ])

    async def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    list_response = test_client.get("/api/subscribers")
    assert list_response.status_code == 200
    assert set(list_response.json().keys()) == {"items", "total", "page", "page_size"}

    detail_response = test_client.get(f"/api/subscribers/{subscriber.id}")
    assert detail_response.status_code == 200
    assert "conversations" in detail_response.json()
    app.dependency_overrides.pop(get_db, None)


def test_product_contracts(client):
    test_client, _, org_id = client
    existing_product = Product(
        id=uuid.uuid4(),
        org_id=org_id,
        name="Starter",
        description="desc",
        price=19.0,
        currency="USD",
        checkout_url=None,
        conversion_value=19.0,
        eligibility_criteria=None,
        objection_responses=None,
        is_active=True,
        sort_order=1,
    )
    _hydrate_model(existing_product)
    fake_db = QueueSession([
        FakeResult(scalars=[existing_product]),
        FakeResult(scalar=existing_product),
        FakeResult(scalar=existing_product),
        FakeResult(scalar=existing_product),
    ])

    async def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    assert test_client.get("/api/products").status_code == 200
    create_response = test_client.post("/api/products", json={"name": "New Product", "currency": "USD"})
    assert create_response.status_code == 201
    assert create_response.json()["name"] == "New Product"
    update_response = test_client.put(f"/api/products/{existing_product.id}", json={"name": "Updated"})
    assert update_response.status_code == 200
    delete_response = test_client.delete(f"/api/products/{existing_product.id}")
    assert delete_response.status_code == 204
    app.dependency_overrides.pop(get_db, None)


def test_settings_contracts(client, monkeypatch):
    test_client, test_user, org_id = client
    organization = SimpleNamespace(
        id=org_id,
        name="Acme",
        slug="acme",
        manychat_api_key=None,
        manychat_page_id="pg_1",
        manychat_account_id="acct_1",
        meta_pixel_id="px_1",
        meta_capi_token=None,
        meta_ad_account_id="ad_1",
        meta_page_id="page_1",
        meta_business_manager_id="bm_1",
        hyros_api_key=None,
        plan="starter",
        monthly_conversation_limit=1000,
        created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
    )
    membership = SimpleNamespace(user_id=test_user.id, org_id=org_id, role=UserRole.ADMIN)
    fake_db = QueueSession([
        FakeResult(scalar=organization),
        FakeResult(scalar=membership),
        FakeResult(scalar=organization),
    ])

    monkeypatch.setattr("app.api.settings.encrypt_value", lambda value: f"enc::{value}")
    monkeypatch.setattr("app.api.settings.decrypt_value", lambda value: value.replace("enc::", ""))
    monkeypatch.setattr("app.api.settings.mask_value", lambda value: f"****{value[-4:]}")

    async def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    get_response = test_client.get("/api/settings")
    assert get_response.status_code == 200
    assert "plan" in get_response.json()
    update_response = test_client.put("/api/settings", json={"manychat_api_key": "secret-key"})
    assert update_response.status_code == 200
    assert "manychat_api_key" in update_response.json()
    app.dependency_overrides.pop(get_db, None)


def test_ai_config_contracts(client):
    test_client, _, org_id = client
    fake_db = QueueSession([
        FakeResult(scalar=None),
        FakeResult(scalar=None),
    ])

    async def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    get_response = test_client.get("/api/ai-config")
    assert get_response.status_code == 200
    assert get_response.json()["max_messages_before_handoff"] == 50

    put_response = test_client.put(
        "/api/ai-config",
        json={"persona_name": "Coach", "brand_voice": "Helpful", "max_messages_before_handoff": 25},
    )
    assert put_response.status_code == 200
    assert put_response.json()["persona_name"] == "Coach"
    app.dependency_overrides.pop(get_db, None)


def test_auth_contracts(client, monkeypatch):
    test_client, test_user, org_id = client
    fake_db = QueueSession([
        FakeResult(scalar=test_user),
        FakeResult(scalar=test_user),
        FakeResult(scalar=org_id),
    ])

    monkeypatch.setattr(auth_api, "verify_password", lambda raw, hashed: True)
    monkeypatch.setattr(auth_api, "create_access_token", lambda user_id: f"access-{user_id}")
    monkeypatch.setattr(auth_api, "create_refresh_token", lambda user_id: f"refresh-{user_id}")
    monkeypatch.setattr(auth_api, "decode_token", lambda token: {"type": "refresh", "sub": str(test_user.id)})

    async def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db

    login_response = test_client.post(
        "/api/auth/login",
        json={"email": test_user.email, "password": "password123"},
    )
    assert login_response.status_code == 200
    assert set(login_response.json().keys()) == {"access_token", "refresh_token", "token_type", "user_id", "email"}

    refresh_response = test_client.post("/api/auth/refresh", json={"refresh_token": "refresh-token"})
    assert refresh_response.status_code == 200
    assert set(refresh_response.json().keys()) == {"access_token", "refresh_token", "token_type"}

    me_response = test_client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert set(me_response.json().keys()) == {
        "id",
        "email",
        "is_active",
        "created_at",
        "org_id",
    }

    app.dependency_overrides.pop(get_db, None)