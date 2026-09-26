"""Scans in Postgres (schema `dashboard`).

A scan stores the correlated findings it produced, and snapshots of the query-analytics,
data-quality and schema views taken at the same moment, so every page of the dashboard describes
one scan and trends across scans are just rows.
"""

import json
from typing import Any

import psycopg
from psycopg.rows import dict_row

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS dashboard;

CREATE TABLE IF NOT EXISTS dashboard.scan (
  scan_id         uuid PRIMARY KEY,
  app             text NOT NULL,
  started_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
  finished_at     timestamptz,
  status          text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'ok', 'failed')),
  error           text,
  layers          jsonb NOT NULL,
  layer_seconds   jsonb,
  load_session    uuid,
  git_commit      text,
  git_dirty       boolean,
  query_analytics jsonb,
  data_quality    jsonb,
  schema_view     jsonb
);
CREATE INDEX IF NOT EXISTS scan_app_started_idx ON dashboard.scan (app, started_at);

CREATE TABLE IF NOT EXISTS dashboard.finding (
  scan_id       uuid NOT NULL REFERENCES dashboard.scan (scan_id) ON DELETE CASCADE,
  finding_id    text NOT NULL,
  rule_id       text NOT NULL,
  severity      text NOT NULL,
  confidence    text NOT NULL,
  file          text NOT NULL,
  line          integer NOT NULL,
  end_line      integer,
  title         text NOT NULL,
  body          text NOT NULL,
  evidence      jsonb NOT NULL,
  layers        jsonb NOT NULL,
  suggested_fix text,
  fingerprint   text NOT NULL,
  PRIMARY KEY (scan_id, finding_id)
);
"""

SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


class ScanStore:
    def __init__(self, database_url: str) -> None:
        self.conn = psycopg.connect(database_url, autocommit=True, row_factory=dict_row)
        self.conn.execute(SCHEMA_SQL)

    def close(self) -> None:
        self.conn.close()

    def start(self, scan_id: str, app: str, layers: list[str], state: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO dashboard.scan (scan_id, app, layers, git_commit, git_dirty)"
            " VALUES (%s, %s, %s, %s, %s)",
            (scan_id, app, _json(layers), state["commit"], state["dirty"]),
        )

    def fail(self, scan_id: str, error: str) -> None:
        self.conn.execute(
            "UPDATE dashboard.scan SET status = 'failed', error = %s,"
            " finished_at = clock_timestamp() WHERE scan_id = %s",
            (error[:2000], scan_id),
        )

    def finish(
        self,
        scan_id: str,
        *,
        findings: list[dict[str, Any]],
        layer_seconds: dict[str, float],
        load_session: str | None,
        query_analytics: Any,
        data_quality: Any,
        schema_view: Any,
    ) -> None:
        ordered = sorted(
            findings,
            key=lambda f: (SEVERITY_ORDER[f["severity"]], f["file"], f["line"], f["ruleId"]),
        )
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO dashboard.finding (scan_id, finding_id, rule_id, severity,
                     confidence, file, line, end_line, title, body, evidence, layers,
                     suggested_fix, fingerprint)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (
                        scan_id,
                        f"F{n:03d}",
                        f["ruleId"],
                        f["severity"],
                        f["confidence"],
                        f["file"],
                        f["line"],
                        f.get("endLine"),
                        f["title"],
                        f["body"],
                        _json(f["evidence"]),
                        _json(sorted({e["source"] for e in f["evidence"]})),
                        f.get("suggestedFix"),
                        f["fingerprint"],
                    )
                    for n, f in enumerate(ordered, 1)
                ],
            )
            cursor.execute(
                """UPDATE dashboard.scan SET status = 'ok', finished_at = clock_timestamp(),
                     layer_seconds = %s, load_session = %s, query_analytics = %s,
                     data_quality = %s, schema_view = %s WHERE scan_id = %s""",
                (
                    _json(layer_seconds),
                    load_session,
                    _json(query_analytics),
                    _json(data_quality),
                    _json(schema_view),
                    scan_id,
                ),
            )

    # ---- reads ------------------------------------------------------------

    def scans(self, app: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return self.conn.execute(
            """SELECT s.scan_id, s.app, s.started_at, s.finished_at, s.status, s.error, s.layers,
                      s.git_commit, s.git_dirty,
                      count(f.*) FILTER (WHERE f.severity = 'HIGH')   AS high,
                      count(f.*) FILTER (WHERE f.severity = 'MEDIUM') AS medium,
                      count(f.*) FILTER (WHERE f.severity = 'LOW')    AS low,
                      count(f.*)                                       AS total
               FROM dashboard.scan s LEFT JOIN dashboard.finding f USING (scan_id)
               WHERE (%s::text IS NULL OR s.app = %s)
               GROUP BY s.scan_id ORDER BY s.started_at DESC LIMIT %s""",
            (app, app, limit),
        ).fetchall()

    def scan(self, scan_id: str) -> dict[str, Any] | None:
        return self.conn.execute(
            "SELECT * FROM dashboard.scan WHERE scan_id = %s", (scan_id,)
        ).fetchone()

    def latest_scan_id(self, app: str) -> str | None:
        row = self.conn.execute(
            "SELECT scan_id FROM dashboard.scan WHERE app = %s AND status = 'ok'"
            " ORDER BY started_at DESC LIMIT 1",
            (app,),
        ).fetchone()
        return str(row["scan_id"]) if row else None

    def findings(self, scan_id: str) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM dashboard.finding WHERE scan_id = %s ORDER BY finding_id", (scan_id,)
        ).fetchall()

    def finding(self, scan_id: str, finding_id: str) -> dict[str, Any] | None:
        return self.conn.execute(
            "SELECT * FROM dashboard.finding WHERE scan_id = %s AND finding_id = %s",
            (scan_id, finding_id),
        ).fetchone()
