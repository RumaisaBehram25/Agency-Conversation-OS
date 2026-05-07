from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

import pytest

from app.api.conversations import list_conversations
from app.services.analytics_service import (
    get_analytics,
)


class _Scalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _Result:
    def __init__(self, *, scalar=None, row=None, scalars=None, all_rows=None):
        self._scalar = scalar
        self._row = row
        self._scalars = scalars if scalars is not None else []
        self._all_rows = all_rows if all_rows is not None else []

    def scalar(self):
        return self._scalar

    def one(self):
        return self._row

    def scalars(self):
        return _Scalars(self._scalars)

    def all(self):
        return self._all_rows


class _ParitySession:
    """
    Lightweight SQL-driven fake session returning deterministic conversation counts.

    Counts are intentionally different across is_test modes so parity assertions
    fail if analytics and conversations endpoints diverge in filter semantics.
    """

    @staticmethod
    def _conversation_count_for_sql(sql: str) -> int:
        lower = sql.lower()
        if "manychat_subscriber_id" in lower and " not like " in lower:
            return 71  # real-only
        if "manychat_subscriber_id" in lower and " like " in lower:
            return 10  # test-only
        return 81  # all

    async def execute(self, query):
        sql = str(query)
        lower = sql.lower()

        if "sum(daily_analytics.new_conversations)" in lower:
            return _Result(
                row=SimpleNamespace(
                    total_conversations=0,
                    total_conversions=0,
                    total_revenue=0,
                    total_ad_spend=0,
                    avg_response_time_ms=None,
                )
            )

        if "count(distinct(conversations.subscriber_id))" in lower:
            return _Result(scalar=0)

        if "from subscribers" in lower and "count(*)" in lower:
            return _Result(scalar=0)

        if "from conversations" in lower and "count(" in lower:
            return _Result(scalar=self._conversation_count_for_sql(sql))

        if "select conversations.id" in lower:
            return _Result(scalars=[])

        return _Result(scalar=0, scalars=[], all_rows=[])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "is_test,expected_total",
    [
        (None, 81),
        (False, 71),
        (True, 10),
    ],
)
async def test_analytics_total_matches_conversations_total_for_same_is_test_mode(
    is_test: bool | None, expected_total: int
) -> None:
    db = _ParitySession()
    org_id = uuid.uuid4()
    dt = date(2026, 5, 7)

    analytics = await get_analytics(
        db,
        org_id,
        dt,
        dt,
        channel=None,
        campaign_id=None,
        attora_campaign_id=None,
        source_type=None,
        is_test=is_test,
    )

    conversations = await list_conversations(
        current_user=SimpleNamespace(id=uuid.uuid4()),
        org_id=org_id,
        db=db,
        status_filter=None,
        channel=None,
        date_from=dt,
        date_to=dt,
        is_test=is_test,
        source_type=None,
        keywords=None,
        campaign_id=None,
        attora_campaign_id=None,
        page=1,
        page_size=20,
    )

    assert analytics.total_conversations == expected_total
    assert conversations.total == expected_total
    assert analytics.total_conversations == conversations.total

