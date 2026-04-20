import sys
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.olap.query import TrinoQueryAdapter


class FakeCursor:
    def __init__(self):
        self.description = (("value",),)
        self.closed = False

    def execute(self, sql: str) -> None:
        self.description = (("value",),)

    def fetchall(self):
        return [(1,)]

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self):
        self.close_calls = 0
        self.cursor_calls = 0

    def cursor(self) -> FakeCursor:
        self.cursor_calls += 1
        return FakeCursor()

    def close(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio
async def test_trino_query_adapter_reuses_pooled_connections(monkeypatch):
    created_connections: list[FakeConnection] = []

    def fake_connect(**kwargs):
        connection = FakeConnection()
        created_connections.append(connection)
        return connection

    monkeypatch.setitem(sys.modules, "trino", SimpleNamespace(dbapi=SimpleNamespace(connect=fake_connect)))

    adapter = TrinoQueryAdapter(
        Settings(
            trino_host="trino",
            trino_port=8080,
            trino_user="attora",
            trino_catalog="lakehouse",
            trino_schema="default",
            trino_http_scheme="http",
            trino_connection_pool_size=2,
        )
    )

    first = await adapter.execute("SELECT 1")
    second = await adapter.execute("SELECT 1")

    assert first.rows == ({"value": 1},)
    assert second.rows == ({"value": 1},)
    assert len(created_connections) == 1
    assert created_connections[0].close_calls == 0
    assert created_connections[0].cursor_calls == 2