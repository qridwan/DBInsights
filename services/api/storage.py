"""Runtime event storage in the results database.

Operations and their statements are stored raw; nothing is aggregated at
write time. Each statement is fingerprinted on the way in (SQLGlot AST
normalization, analyzers.sql.fingerprint).
"""

import threading
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row
from pydantic.alias_generators import to_camel

from analyzers.sql import fingerprint

from .events import OperationEvent

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS operation (
  operation_id   text PRIMARY KEY,
  app            text NOT NULL,
  request_id     text,
  route          text,
  model          text,
  operation      text NOT NULL,
  started_at     timestamptz NOT NULL,
  duration_ms    double precision NOT NULL,
  rows_returned  integer,
  error          boolean NOT NULL,
  received_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS operation_request_idx ON operation (request_id);
CREATE INDEX IF NOT EXISTS operation_app_started_idx ON operation (app, started_at);

CREATE TABLE IF NOT EXISTS statement (
  operation_id   text NOT NULL REFERENCES operation (operation_id) ON DELETE CASCADE,
  position       integer NOT NULL,
  sql            text NOT NULL,
  fingerprint    text NOT NULL,
  normalized_sql text NOT NULL,
  parsed         boolean NOT NULL,
  param_count    integer NOT NULL,
  kind           text NOT NULL,
  duration_ms    double precision NOT NULL,
  rows           integer,
  PRIMARY KEY (operation_id, position)
);
CREATE INDEX IF NOT EXISTS statement_fingerprint_idx ON statement (fingerprint);
"""


class EventStore(Protocol):
    def ingest(self, events: list[OperationEvent]) -> int: ...

    def operations(
        self, *, app: str | None, request_id: str | None, route: str | None, limit: int
    ) -> list[dict[str, Any]]: ...


def _statement_rows(event: OperationEvent) -> list[dict[str, Any]]:
    rows = []
    for position, statement in enumerate(event.statements):
        fp = fingerprint(statement.sql)
        rows.append(
            {
                "operation_id": event.operation_id,
                "position": position,
                "sql": statement.sql,
                "fingerprint": fp.id,
                "normalized_sql": fp.normalized,
                "parsed": fp.parsed,
                "param_count": statement.param_count,
                "kind": statement.kind,
                "duration_ms": statement.duration_ms,
                "rows": statement.rows,
            }
        )
    return rows


def _operation_row(event: OperationEvent) -> dict[str, Any]:
    return {
        "operation_id": event.operation_id,
        "app": event.app,
        "request_id": event.request_id,
        "route": event.route,
        "model": event.model,
        "operation": event.operation,
        "started_at": event.started_at,
        "duration_ms": event.duration_ms,
        "rows_returned": event.rows_returned,
        "error": event.error,
    }


def _present(row: dict[str, Any]) -> dict[str, Any]:
    """API shape: camelCase keys, like the events that were ingested."""
    return {
        to_camel(key): [_present(s) for s in value] if key == "statements" else value
        for key, value in row.items()
    }


class PostgresEventStore:
    """Stores events in `<schema>.operation` and `<schema>.statement`."""

    def __init__(self, database_url: str, schema: str = "runtime") -> None:
        self._conn = psycopg.connect(database_url, autocommit=True, row_factory=dict_row)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            self._conn.execute(f'SET search_path TO "{schema}"')
            self._conn.execute(SCHEMA_SQL)

    def ingest(self, events: list[OperationEvent]) -> int:
        operations = [_operation_row(e) for e in events]
        statements = [row for e in events for row in _statement_rows(e)]
        with self._lock, self._conn.transaction(), self._conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO operation (operation_id, app, request_id, route, model,
                     operation, started_at, duration_ms, rows_returned, error)
                   VALUES (%(operation_id)s, %(app)s, %(request_id)s, %(route)s, %(model)s,
                     %(operation)s, %(started_at)s, %(duration_ms)s, %(rows_returned)s,
                     %(error)s)
                   ON CONFLICT (operation_id) DO NOTHING""",
                operations,
            )
            if statements:
                cursor.executemany(
                    """INSERT INTO statement (operation_id, position, sql, fingerprint,
                         normalized_sql, parsed, param_count, kind, duration_ms, rows)
                       VALUES (%(operation_id)s, %(position)s, %(sql)s, %(fingerprint)s,
                         %(normalized_sql)s, %(parsed)s, %(param_count)s, %(kind)s,
                         %(duration_ms)s, %(rows)s)
                       ON CONFLICT (operation_id, position) DO NOTHING""",
                    statements,
                )
        return len(events)

    def operations(
        self, *, app: str | None, request_id: str | None, route: str | None, limit: int
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT o.*, COALESCE(
                          json_agg(json_build_object(
                            'position', s.position, 'sql', s.sql, 'fingerprint', s.fingerprint,
                            'normalized_sql', s.normalized_sql, 'parsed', s.parsed,
                            'param_count', s.param_count, 'kind', s.kind,
                            'duration_ms', s.duration_ms, 'rows', s.rows) ORDER BY s.position)
                          FILTER (WHERE s.operation_id IS NOT NULL),
                          '[]') AS statements
                   FROM operation o LEFT JOIN statement s USING (operation_id)
                   WHERE (%(app)s::text IS NULL OR o.app = %(app)s)
                     AND (%(request_id)s::text IS NULL OR o.request_id = %(request_id)s)
                     AND (%(route)s::text IS NULL OR o.route = %(route)s)
                   GROUP BY o.operation_id
                   ORDER BY o.started_at DESC
                   LIMIT %(limit)s""",
                {"app": app, "request_id": request_id, "route": route, "limit": limit},
            ).fetchall()
        return [_present(dict(row)) for row in rows]


class MemoryEventStore:
    """In-process store with the same behaviour, for tests."""

    def __init__(self) -> None:
        self.operation_rows: dict[str, dict[str, Any]] = {}
        self.statement_rows: list[dict[str, Any]] = []

    def ingest(self, events: list[OperationEvent]) -> int:
        for event in events:
            if event.operation_id in self.operation_rows:
                continue
            self.operation_rows[event.operation_id] = _operation_row(event)
            self.statement_rows.extend(_statement_rows(event))
        return len(events)

    def operations(
        self, *, app: str | None, request_id: str | None, route: str | None, limit: int
    ) -> list[dict[str, Any]]:
        rows = [
            {
                **row,
                "statements": [
                    s for s in self.statement_rows if s["operation_id"] == row["operation_id"]
                ],
            }
            for row in self.operation_rows.values()
            if (app is None or row["app"] == app)
            and (request_id is None or row["request_id"] == request_id)
            and (route is None or row["route"] == route)
        ]
        rows.sort(key=lambda r: r["started_at"], reverse=True)
        return [_present(row) for row in rows[:limit]]
