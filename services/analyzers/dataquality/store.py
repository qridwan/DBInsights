"""Profile storage in the results database (schema `dataquality`).

Every profile is an immutable `profile_run`; observations accumulate and are
never overwritten. The read methods return a column's history in data-time
order, which is what the anomaly detector learns its baselines from.
"""

import json
import re
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .models import ProfileRun

_SCHEMA_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS profile_run (
  run_id          uuid PRIMARY KEY,
  app             text NOT NULL,
  label           text,
  profiled_at     timestamptz NOT NULL,
  window_start    timestamptz,
  window_end      timestamptz,
  max_categories  integer NOT NULL,
  time_columns    jsonb NOT NULL,
  skipped_tables  jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS profile_run_app_window_idx ON profile_run (app, window_start);

CREATE TABLE IF NOT EXISTS table_profile (
  run_id       uuid NOT NULL REFERENCES profile_run (run_id) ON DELETE CASCADE,
  table_name   text NOT NULL,
  row_count    bigint NOT NULL,
  time_column  text,
  PRIMARY KEY (run_id, table_name)
);

CREATE TABLE IF NOT EXISTS column_profile (
  run_id          uuid NOT NULL REFERENCES profile_run (run_id) ON DELETE CASCADE,
  table_name      text NOT NULL,
  column_name     text NOT NULL,
  data_type       text NOT NULL,
  row_count       bigint NOT NULL,
  null_count      bigint NOT NULL,
  null_rate       double precision,
  distinct_count  bigint NOT NULL,
  duplicate_rate  double precision,
  PRIMARY KEY (run_id, table_name, column_name)
);

CREATE TABLE IF NOT EXISTS category_frequency (
  run_id       uuid NOT NULL REFERENCES profile_run (run_id) ON DELETE CASCADE,
  table_name   text NOT NULL,
  column_name  text NOT NULL,
  value        text NOT NULL,
  count        bigint NOT NULL,
  PRIMARY KEY (run_id, table_name, column_name, value)
);

CREATE TABLE IF NOT EXISTS integrity_check (
  run_id              uuid NOT NULL REFERENCES profile_run (run_id) ON DELETE CASCADE,
  model               text NOT NULL,
  relation            text NOT NULL,
  table_name          text NOT NULL,
  column_names        text[] NOT NULL,
  referenced_table    text NOT NULL,
  referenced_columns  text[] NOT NULL,
  checked_rows        bigint NOT NULL,
  orphan_rows         bigint NOT NULL,
  orphan_rate         double precision,
  line                integer NOT NULL,
  PRIMARY KEY (run_id, model, relation)
);
"""


class ProfileStore:
    def __init__(self, database_url: str, schema: str = "dataquality") -> None:
        if not _SCHEMA_NAME.match(schema):
            raise ValueError(f"invalid schema name {schema!r}")
        self.schema = schema
        self.conn = psycopg.connect(database_url, autocommit=True, row_factory=dict_row)
        self.conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        self.conn.execute(f'SET search_path TO "{schema}"')
        self.conn.execute(SCHEMA_SQL)

    def close(self) -> None:
        self.conn.close()

    def save(self, run: ProfileRun) -> None:
        window = run.window
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO profile_run (run_id, app, label, profiled_at, window_start,
                     window_end, max_categories, time_columns, skipped_tables)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    run.run_id,
                    run.app,
                    run.label,
                    run.profiled_at,
                    window.start if window else None,
                    window.end if window else None,
                    run.max_categories,
                    json.dumps(run.time_columns),
                    json.dumps(run.skipped_tables),
                ),
            )
            cursor.executemany(
                "INSERT INTO table_profile (run_id, table_name, row_count, time_column) "
                "VALUES (%s, %s, %s, %s)",
                [(run.run_id, t.table, t.row_count, t.time_column) for t in run.tables],
            )
            cursor.executemany(
                """INSERT INTO column_profile (run_id, table_name, column_name, data_type,
                     row_count, null_count, null_rate, distinct_count, duplicate_rate)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (
                        run.run_id,
                        c.table,
                        c.column,
                        c.data_type,
                        c.row_count,
                        c.null_count,
                        c.null_rate,
                        c.distinct_count,
                        c.duplicate_rate,
                    )
                    for c in run.columns
                ],
            )
            cursor.executemany(
                """INSERT INTO category_frequency (run_id, table_name, column_name, value, count)
                   VALUES (%s, %s, %s, %s, %s)""",
                [(run.run_id, c.table, c.column, c.value, c.count) for c in run.categories],
            )
            cursor.executemany(
                """INSERT INTO integrity_check (run_id, model, relation, table_name, column_names,
                     referenced_table, referenced_columns, checked_rows, orphan_rows,
                     orphan_rate, line)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (
                        run.run_id,
                        i.model,
                        i.relation,
                        i.table,
                        i.columns,
                        i.referenced_table,
                        i.referenced_columns,
                        i.checked_rows,
                        i.orphan_rows,
                        i.orphan_rate,
                        i.line,
                    )
                    for i in run.integrity
                ],
            )

    # ---- reads -----------------------------------------------------------

    def runs(self, app: str, label: str | None = None) -> list[dict[str, Any]]:
        return self.conn.execute(
            """SELECT run_id, app, label, profiled_at, window_start, window_end,
                      (SELECT count(*) FROM column_profile c WHERE c.run_id = r.run_id) AS columns
               FROM profile_run r
               WHERE app = %s AND (%s::text IS NULL OR label = %s)
               ORDER BY window_start NULLS LAST, profiled_at""",
            (app, label, label),
        ).fetchall()

    def column_history(
        self, app: str, table: str, column: str, *, label: str | None = None
    ) -> list[dict[str, Any]]:
        """One row per windowed profile of the column, oldest window first."""
        return self.conn.execute(
            """SELECT r.run_id, r.label, r.window_start, r.window_end, r.profiled_at,
                      c.row_count, c.null_count, c.null_rate, c.distinct_count, c.duplicate_rate
               FROM profile_run r JOIN column_profile c USING (run_id)
               WHERE r.app = %s AND c.table_name = %s AND c.column_name = %s
                 AND r.window_start IS NOT NULL AND (%s::text IS NULL OR r.label = %s)
               ORDER BY r.window_start""",
            (app, table, column, label, label),
        ).fetchall()

    def category_history(
        self, app: str, table: str, column: str, *, label: str | None = None
    ) -> list[dict[str, Any]]:
        """Per windowed profile: the column's value -> count distribution, oldest first."""
        rows = self.conn.execute(
            """SELECT r.run_id, r.window_start, r.window_end, f.value, f.count
               FROM profile_run r JOIN category_frequency f USING (run_id)
               WHERE r.app = %s AND f.table_name = %s AND f.column_name = %s
                 AND r.window_start IS NOT NULL AND (%s::text IS NULL OR r.label = %s)
               ORDER BY r.window_start, f.count DESC, f.value""",
            (app, table, column, label, label),
        ).fetchall()
        history: dict[str, dict[str, Any]] = {}
        for row in rows:
            entry = history.setdefault(
                str(row["run_id"]),
                {
                    "run_id": row["run_id"],
                    "window_start": row["window_start"],
                    "window_end": row["window_end"],
                    "distribution": {},
                },
            )
            entry["distribution"][row["value"]] = row["count"]
        return list(history.values())

    def integrity(self, run_id: str) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM integrity_check WHERE run_id = %s ORDER BY table_name, relation",
            (run_id,),
        ).fetchall()


def parse_time(value: str) -> datetime:
    """ISO date or datetime; a date means midnight UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
