import uuid

from app.services.analytics_service import (
    _conversion_event_campaign_clause,
    _subscriber_campaign_clause,
)


def _sql(expr) -> str:
    return str(expr.compile(compile_kwargs={"literal_binds": True}))


def test_paid_subscriber_scope_is_strict_campaign_only() -> None:
    expr = _subscriber_campaign_clause("meta_123", None)
    sql = _sql(expr)
    assert "subscribers.campaign_id = 'meta_123'" in sql
    assert "subscribers.campaign_id IS NULL" not in sql


def test_paid_conversion_scope_is_strict_campaign_only() -> None:
    expr = _conversion_event_campaign_clause("meta_123", None)
    sql = _sql(expr)
    assert "conversion_events.meta_campaign_id = 'meta_123'" in sql
    assert "conversion_events.meta_campaign_id IS NULL" not in sql


def test_source_type_scope_uses_campaign_subquery() -> None:
    org_id = uuid.uuid4()
    expr = _subscriber_campaign_clause(None, None, org_id=org_id, source_type="paid")
    sql = _sql(expr)
    assert "IN (SELECT ad_campaigns.id" in sql
    assert "ad_campaigns.source_type = 'paid'" in sql

