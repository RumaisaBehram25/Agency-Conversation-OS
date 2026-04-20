"""Query adapters for historical OLAP reads."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from queue import Empty, Full, LifoQueue
from threading import Lock
from typing import Any

from app.config import Settings


@dataclass(frozen=True, slots=True)
class QueryResult:
    """Normalized result returned by OLAP query adapters."""

    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    row_count: int


class QueryAdapter(ABC):
    """Provider-agnostic interface for OLAP query engines."""

    provider: str

    def __init__(self, settings: Settings):
        self.settings = settings

    @abstractmethod
    async def execute(self, sql: str) -> QueryResult:
        """Execute a SQL query against the configured OLAP engine."""

    async def execute_many(self, sql_statements: tuple[str, ...]) -> tuple[QueryResult, ...]:
        """Execute multiple SQL statements against the configured OLAP engine."""
        results = []
        for sql in sql_statements:
            results.append(await self.execute(sql))
        return tuple(results)


class DisabledQueryAdapter(QueryAdapter):
    """Placeholder adapter used when no query engine is configured."""

    provider = "none"

    async def execute(self, sql: str) -> QueryResult:
        raise RuntimeError("OLAP query engine is disabled")


class TrinoQueryAdapter(QueryAdapter):
    """Trino query adapter for self-hosted historical analytics."""

    provider = "trino"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        pool_size = max(1, settings.trino_connection_pool_size)
        self._connection_pool: LifoQueue[Any] = LifoQueue(maxsize=pool_size)
        self._pool_size = pool_size
        self._connection_count = 0
        self._pool_lock = Lock()

    async def execute(self, sql: str) -> QueryResult:
        return await asyncio.to_thread(self._execute_blocking, sql)

    async def execute_many(self, sql_statements: tuple[str, ...]) -> tuple[QueryResult, ...]:
        return await asyncio.to_thread(self._execute_many_blocking, sql_statements)

    def _execute_blocking(self, sql: str) -> QueryResult:
        return self._execute_many_blocking((sql,))[0]

    def _execute_many_blocking(self, sql_statements: tuple[str, ...]) -> tuple[QueryResult, ...]:
        connection = self._acquire_connection()
        should_discard = False
        try:
            return self._execute_many_with_connection(connection, sql_statements)
        except Exception:
            should_discard = True
            raise
        finally:
            if should_discard:
                self._discard_connection(connection)
            else:
                self._release_connection(connection)

    def _execute_many_with_connection(self, connection: Any, sql_statements: tuple[str, ...]) -> tuple[QueryResult, ...]:
        cursor = connection.cursor()
        try:
            results = []
            for sql in sql_statements:
                cursor.execute(sql)
                columns = tuple(description[0] for description in (cursor.description or []))
                rows = cursor.fetchall() if columns else []
                normalized_rows = tuple(dict(zip(columns, row, strict=False)) for row in rows)
                results.append(
                    QueryResult(
                        columns=columns,
                        rows=normalized_rows,
                        row_count=len(normalized_rows),
                    )
                )
            return tuple(results)
        finally:
            cursor.close()

    def _acquire_connection(self) -> Any:
        try:
            return self._connection_pool.get_nowait()
        except Empty:
            pass

        with self._pool_lock:
            if self._connection_count < self._pool_size:
                self._connection_count += 1
                try:
                    return self._create_connection()
                except Exception:
                    self._connection_count -= 1
                    raise

        return self._connection_pool.get()

    def _release_connection(self, connection: Any) -> None:
        try:
            self._connection_pool.put_nowait(connection)
        except Full:
            self._discard_connection(connection)

    def _discard_connection(self, connection: Any) -> None:
        try:
            connection.close()
        finally:
            with self._pool_lock:
                if self._connection_count > 0:
                    self._connection_count -= 1

    def _create_connection(self) -> Any:
        import trino

        return trino.dbapi.connect(
            host=self.settings.trino_host,
            port=self.settings.trino_port,
            user=self.settings.trino_user,
            catalog=self.settings.trino_catalog,
            schema=self.settings.trino_schema,
            http_scheme=self.settings.trino_http_scheme,
        )


class AthenaQueryAdapter(QueryAdapter):
    """Athena adapter placeholder for the later AWS cutover."""

    provider = "athena"

    async def execute(self, sql: str) -> QueryResult:
        raise NotImplementedError(
            "Athena query execution is not wired into serving paths in phase 1"
        )