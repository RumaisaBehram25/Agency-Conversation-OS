import uuid

from sqlalchemy import select

from app.api.conversations import _apply_conversation_filters
from app.models.conversation import Conversation


def _sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def test_paid_source_type_filters_to_subscribers_with_campaign_id() -> None:
    stmt = _apply_conversation_filters(
        select(Conversation),
        org_id=uuid.uuid4(),
        status_filter=None,
        channel=None,
        date_from=None,
        date_to=None,
        is_test=None,
        source_type="paid",
        keywords=[],
        campaign_id=None,
        attora_campaign_id=None,
    )
    sql = _sql(stmt)
    assert "subscribers.campaign_id IS NOT NULL" in sql


def test_specific_campaign_id_filter_is_applied() -> None:
    stmt = _apply_conversation_filters(
        select(Conversation),
        org_id=uuid.uuid4(),
        status_filter=None,
        channel=None,
        date_from=None,
        date_to=None,
        is_test=None,
        source_type="paid",
        keywords=[],
        campaign_id="120044445555",
        attora_campaign_id=None,
    )
    sql = _sql(stmt)
    assert "subscribers.campaign_id = '120044445555'" in sql

