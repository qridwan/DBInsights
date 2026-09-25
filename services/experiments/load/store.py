"""Load-harness results in the results database (schema `experiments`).

Raw rows only: every request, every resource sample. Aggregation happens at
analysis time (analysis.py), never at write time.
"""

import json
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS experiments;

CREATE TABLE IF NOT EXISTS experiments.load_session (
  session_id   uuid PRIMARY KEY,
  kind         text NOT NULL,          -- 'run' | 'repeatability' | 'overhead'
  app          text NOT NULL,
  seed         integer NOT NULL,
  repetitions  integer NOT NULL,
  parameters   jsonb NOT NULL,
  git_commit   text,
  started_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
  finished_at  timestamptz
);

CREATE TABLE IF NOT EXISTS experiments.load_run (
  run_id              uuid PRIMARY KEY,
  session_id          uuid NOT NULL REFERENCES experiments.load_session (session_id),
  app                 text NOT NULL,
  block               integer NOT NULL,
  warmup              boolean NOT NULL,
  collector_enabled   boolean NOT NULL,
  -- Whether the collector's actual behaviour during the run matched collector_enabled.
  collector_verified  boolean,
  -- Run window on the database server clock (the clock the app containers share).
  window_start        timestamptz NOT NULL,
  window_end          timestamptz
);

CREATE TABLE IF NOT EXISTS experiments.load_request (
  run_id          uuid NOT NULL REFERENCES experiments.load_run (run_id) ON DELETE CASCADE,
  seq             integer NOT NULL,
  entry_id        text NOT NULL,
  method          text NOT NULL,
  path            text NOT NULL,
  route           text NOT NULL,
  status          integer NOT NULL,     -- 0 = connection failure
  latency_ms      double precision NOT NULL,
  response_bytes  integer NOT NULL,
  started_at      timestamptz NOT NULL,
  PRIMARY KEY (run_id, seq)
);

CREATE TABLE IF NOT EXISTS experiments.resource_sample (
  run_id        uuid NOT NULL REFERENCES experiments.load_run (run_id) ON DELETE CASCADE,
  sampled_at    timestamptz NOT NULL,
  service       text NOT NULL,          -- compose service, e.g. 'ecommerce', 'collector'
  cpu_percent   double precision NOT NULL,
  memory_bytes  bigint NOT NULL
);
CREATE INDEX IF NOT EXISTS resource_sample_run_idx ON experiments.resource_sample (run_id);

-- cgroup v2 counters read immediately before ('start') and after ('end') a run.
CREATE TABLE IF NOT EXISTS experiments.resource_counter (
  run_id                uuid NOT NULL REFERENCES experiments.load_run (run_id) ON DELETE CASCADE,
  service               text NOT NULL,
  phase                 text NOT NULL CHECK (phase IN ('start', 'end')),
  cpu_usage_usec        bigint NOT NULL,   -- cumulative since container start
  memory_current_bytes  bigint NOT NULL,
  memory_peak_bytes     bigint NOT NULL,   -- high-water mark since container start
  PRIMARY KEY (run_id, service, phase)
);
"""


class ResultsStore:
    def __init__(self, database_url: str) -> None:
        self.conn = psycopg.connect(database_url, autocommit=True, row_factory=dict_row)
        self.conn.execute(SCHEMA_SQL)

    def close(self) -> None:
        self.conn.close()

    def db_now(self) -> datetime:
        return self.conn.execute("SELECT clock_timestamp() AS now").fetchone()["now"]

    def start_session(
        self,
        session_id: str,
        *,
        kind: str,
        app: str,
        seed: int,
        repetitions: int,
        parameters: dict[str, Any],
        git_commit: str | None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO experiments.load_session
                 (session_id, kind, app, seed, repetitions, parameters, git_commit)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (session_id, kind, app, seed, repetitions, json.dumps(parameters), git_commit),
        )

    def finish_session(self, session_id: str) -> None:
        self.conn.execute(
            "UPDATE experiments.load_session SET finished_at = clock_timestamp() "
            "WHERE session_id = %s",
            (session_id,),
        )

    def start_run(
        self,
        run_id: str,
        *,
        session_id: str,
        app: str,
        block: int,
        warmup: bool,
        collector_enabled: bool,
    ) -> None:
        self.conn.execute(
            """INSERT INTO experiments.load_run
                 (run_id, session_id, app, block, warmup, collector_enabled, window_start)
               VALUES (%s, %s, %s, %s, %s, %s, clock_timestamp())""",
            (run_id, session_id, app, block, warmup, collector_enabled),
        )

    def finish_run(self, run_id: str) -> None:
        self.conn.execute(
            "UPDATE experiments.load_run SET window_end = clock_timestamp() WHERE run_id = %s",
            (run_id,),
        )

    def set_verified(self, run_id: str, verified: bool) -> None:
        self.conn.execute(
            "UPDATE experiments.load_run SET collector_verified = %s WHERE run_id = %s",
            (verified, run_id),
        )

    def add_requests(self, run_id: str, rows: list[dict[str, Any]]) -> None:
        with self.conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO experiments.load_request
                     (run_id, seq, entry_id, method, path, route, status, latency_ms,
                      response_bytes, started_at)
                   VALUES (%(run_id)s, %(seq)s, %(entry_id)s, %(method)s, %(path)s, %(route)s,
                     %(status)s, %(latency_ms)s, %(response_bytes)s, %(started_at)s)""",
                [{**row, "run_id": run_id} for row in rows],
            )

    def add_samples(self, run_id: str, rows: list[dict[str, Any]]) -> None:
        with self.conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO experiments.resource_sample
                     (run_id, sampled_at, service, cpu_percent, memory_bytes)
                   VALUES (%(run_id)s, %(sampled_at)s, %(service)s, %(cpu_percent)s,
                     %(memory_bytes)s)""",
                [{**row, "run_id": run_id} for row in rows],
            )

    def add_counters(self, run_id: str, phase: str, counters: dict[str, dict[str, int]]) -> None:
        with self.conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO experiments.resource_counter
                     (run_id, service, phase, cpu_usage_usec, memory_current_bytes,
                      memory_peak_bytes)
                   VALUES (%(run_id)s, %(service)s, %(phase)s, %(cpu_usage_usec)s,
                     %(memory_current_bytes)s, %(memory_peak_bytes)s)""",
                [
                    {"run_id": run_id, "service": service, "phase": phase, **values}
                    for service, values in counters.items()
                ],
            )

    # ---- reads -----------------------------------------------------------

    def runs(self, session_id: str) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM experiments.load_run WHERE session_id = %s ORDER BY window_start",
            (session_id,),
        ).fetchall()

    def requests(self, session_id: str) -> list[dict[str, Any]]:
        return self.conn.execute(
            """SELECT r.*, run.collector_enabled, run.warmup, run.block
               FROM experiments.load_request r JOIN experiments.load_run run USING (run_id)
               WHERE run.session_id = %s ORDER BY run.window_start, r.seq""",
            (session_id,),
        ).fetchall()

    def samples(self, session_id: str) -> list[dict[str, Any]]:
        return self.conn.execute(
            """SELECT s.*, run.collector_enabled, run.warmup
               FROM experiments.resource_sample s JOIN experiments.load_run run USING (run_id)
               WHERE run.session_id = %s""",
            (session_id,),
        ).fetchall()

    def counters(self, session_id: str) -> list[dict[str, Any]]:
        """One row per (run, service): counter deltas, end memory, and the run's request count."""
        return self.conn.execute(
            """SELECT run.run_id, run.collector_enabled, run.warmup, s.service,
                      e.cpu_usage_usec - s.cpu_usage_usec AS cpu_usec,
                      e.memory_current_bytes AS memory_end_bytes,
                      e.memory_peak_bytes AS memory_peak_bytes,
                      (SELECT count(*) FROM experiments.load_request q
                        WHERE q.run_id = run.run_id AND q.status = 200) AS requests
               FROM experiments.load_run run
               JOIN experiments.resource_counter s ON s.run_id = run.run_id AND s.phase = 'start'
               JOIN experiments.resource_counter e
                 ON e.run_id = run.run_id AND e.service = s.service AND e.phase = 'end'
               WHERE run.session_id = %s""",
            (session_id,),
        ).fetchall()

    def runtime_counts(self, app: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Operations and statements the collector recorded per route inside a window."""
        exists = self.conn.execute(
            "SELECT to_regclass('runtime.operation') IS NOT NULL AS ok"
        ).fetchone()["ok"]
        if not exists:
            return []
        return self.conn.execute(
            """SELECT o.route, count(DISTINCT o.operation_id) AS operations,
                      count(s.operation_id) AS statements
               FROM runtime.operation o LEFT JOIN runtime.statement s USING (operation_id)
               WHERE o.app = %s AND o.started_at >= %s AND o.started_at <= %s
               GROUP BY o.route ORDER BY o.route""",
            (app, start, end),
        ).fetchall()
