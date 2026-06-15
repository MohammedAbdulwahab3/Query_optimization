"""Database access layer.

Exposes a single :class:`Database` interface with two interchangeable
implementations (embedded ``chdb`` and remote ``clickhouse-server``). All
analytics code only depends on ``query()`` / ``command()`` and never knows
which backend is in use.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from .config import Settings, get_settings

logger = logging.getLogger("app.db")


class Database:
    """Common interface for both ClickHouse backends."""

    def query(self, sql: str) -> list[dict[str, Any]]:
        """Run a SELECT and return rows as a list of dicts."""
        raise NotImplementedError

    def command(self, sql: str) -> None:
        """Run a statement (DDL / INSERT) that returns no rows."""
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - best effort cleanup
        pass


class EmbeddedDatabase(Database):
    """In-process ClickHouse via ``chdb``.

    ``chdb`` sessions are not thread-safe, so every call is guarded by a lock.
    The app therefore runs with a single uvicorn worker in embedded mode.
    """

    def __init__(self, path: str) -> None:
        import os

        from chdb import session as chdb_session

        os.makedirs(path, exist_ok=True)
        self._session = chdb_session.Session(path)
        self._lock = threading.Lock()
        logger.info("Embedded chdb session initialised at %s", path)

    def query(self, sql: str) -> list[dict[str, Any]]:
        with self._lock:
            result = self._session.query(sql, "JSONEachRow")
        text = str(result).strip()
        if not text:
            return []
        return [json.loads(line) for line in text.splitlines()]

    def command(self, sql: str) -> None:
        with self._lock:
            self._session.query(sql)

    def close(self) -> None:  # pragma: no cover
        with self._lock:
            self._session.close()


class ServerDatabase(Database):
    """Remote ``clickhouse-server`` via the official HTTP driver."""

    def __init__(self, settings: Settings) -> None:
        import clickhouse_connect

        # We do not pin a database on the connection so that DDL can create it;
        # every query fully-qualifies table names with ``analytics.``.
        self._client = clickhouse_connect.get_client(
            host=settings.ch_host,
            port=settings.ch_port,
            username=settings.ch_user,
            password=settings.ch_password,
        )
        logger.info(
            "Connected to clickhouse-server at %s:%s", settings.ch_host, settings.ch_port
        )

    def query(self, sql: str) -> list[dict[str, Any]]:
        result = self._client.query(sql)
        columns = result.column_names
        return [dict(zip(columns, row)) for row in result.result_rows]

    def command(self, sql: str) -> None:
        self._client.command(sql)

    def close(self) -> None:  # pragma: no cover
        self._client.close()


_db: Database | None = None


def init_db(settings: Settings | None = None) -> Database:
    """Create (once) and return the process-wide database handle."""
    global _db
    if _db is not None:
        return _db

    settings = settings or get_settings()
    if settings.ch_backend == "server":
        _db = ServerDatabase(settings)
    else:
        _db = EmbeddedDatabase(settings.chdb_path)
    return _db


def get_db() -> Database:
    if _db is None:
        return init_db()
    return _db
