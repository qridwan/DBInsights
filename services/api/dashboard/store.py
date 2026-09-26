"""Scans in Postgres (schema `dashboard`).

A scan stores the correlated findings it produced, and snapshots of the query-analytics,
data-quality and schema views taken at the same moment, so every page of the dashboard describes
one scan and trends across scans are just rows.
"""

import json
from typing import Any

from api.dbconn import ReconnectingConnection

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
ALTER TABLE dashboard.scan ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'app';
ALTER TABLE dashboard.scan ADD COLUMN IF NOT EXISTS source jsonb;
ALTER TABLE dashboard.scan ADD COLUMN IF NOT EXISTS owner_id uuid;
CREATE INDEX IF NOT EXISTS scan_owner_idx ON dashboard.scan (owner_id, app, started_at);
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

# Who may see a scan. A scanned project is private to whoever scanned it. A scan of a built-in app
# is visible to the person who ran it, plus older scans that predate accounts (no owner), which
# stay visible to everyone as shared samples.
VISIBLE = "(s.owner_id = %(viewer)s::uuid OR (s.owner_id IS NULL AND s.kind = 'app'))"


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


class ScanStore:
    def __init__(self, database_url: str) -> None:
        self.conn = ReconnectingConnection(database_url)
        self.conn.execute(SCHEMA_SQL)

    def close(self) -> None:
        self.conn.close()

    def start(
        self,
        scan_id: str,
        app: str,
        layers: list[str],
        state: dict[str, Any],
        kind: str = "app",
        source: dict[str, Any] | None = None,
        owner_id: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO dashboard.scan"
            " (scan_id, app, layers, git_commit, git_dirty, kind, source, owner_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                scan_id,
                app,
                _json(layers),
                state["commit"],
                state["dirty"],
                kind,
                _json(source) if source is not None else None,
                owner_id,
            ),
        )

    def set_source(self, scan_id: str, source: dict[str, Any]) -> None:
        self.conn.execute(
            "UPDATE dashboard.scan SET source = %s WHERE scan_id = %s", (_json(source), scan_id)
        )

    def projects(self, viewer: str) -> list[dict[str, Any]]:
        """The latest scan of each project this user has scanned. Projects are never shared."""
        return self.conn.execute(
            """SELECT DISTINCT ON (app) app, scan_id, source, started_at
               FROM dashboard.scan WHERE kind = 'project' AND owner_id = %s::uuid
               ORDER BY app, started_at DESC""",
            (viewer,),
        ).fetchall()

    def claim_legacy_projects(self, owner_id: str) -> int:
        """Give the projects scanned before accounts existed to the first account (the operator)."""
        return self.conn.execute(
            "UPDATE dashboard.scan SET owner_id = %s::uuid"
            " WHERE kind = 'project' AND owner_id IS NULL",
            (owner_id,),
        ).rowcount

    def delete_project(self, owner_id: str, name: str) -> int:
        return self.conn.execute(
            "DELETE FROM dashboard.scan"
            " WHERE kind = 'project' AND owner_id = %s::uuid AND app = %s",
            (owner_id, name),
        ).rowcount

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
        live = self.conn.live()
        with live.transaction(), live.cursor() as cursor:
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

    def scans(
        self, app: str | None = None, limit: int = 50, *, viewer: str
    ) -> list[dict[str, Any]]:
        return self.conn.execute(
            f"""SELECT s.scan_id, s.app, s.started_at, s.finished_at, s.status, s.error, s.layers,
                      s.git_commit, s.git_dirty, s.kind,
                      count(f.*) FILTER (WHERE f.severity = 'HIGH')   AS high,
                      count(f.*) FILTER (WHERE f.severity = 'MEDIUM') AS medium,
                      count(f.*) FILTER (WHERE f.severity = 'LOW')    AS low,
                      count(f.*)                                       AS total
               FROM dashboard.scan s LEFT JOIN dashboard.finding f USING (scan_id)
               WHERE (%(app)s::text IS NULL OR s.app = %(app)s) AND {VISIBLE}
               GROUP BY s.scan_id ORDER BY s.started_at DESC LIMIT %(limit)s""",
            {"app": app, "limit": limit, "viewer": viewer},
        ).fetchall()

    def scan(self, scan_id: str, *, viewer: str) -> dict[str, Any] | None:
        """The scan, or None if it does not exist or is not this user's to see."""
        return self.conn.execute(
            f"SELECT s.* FROM dashboard.scan s WHERE s.scan_id = %(id)s::uuid AND {VISIBLE}",
            {"id": scan_id, "viewer": viewer},
        ).fetchone()

    def latest_scan_id(self, app: str, *, viewer: str) -> str | None:
        row = self.conn.execute(
            "SELECT s.scan_id FROM dashboard.scan s"
            f" WHERE s.app = %(app)s AND s.status = 'ok' AND {VISIBLE}"
            " ORDER BY s.started_at DESC LIMIT 1",
            {"app": app, "viewer": viewer},
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
