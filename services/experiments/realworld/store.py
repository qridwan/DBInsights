"""Real-world analysis results in Postgres (schema `realworld`). Raw findings, one row each."""

import json
from typing import Any

import psycopg
from psycopg.rows import dict_row

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS realworld;

CREATE TABLE IF NOT EXISTS realworld.analysis (
  analysis_id       uuid PRIMARY KEY,
  started_at        timestamptz NOT NULL DEFAULT clock_timestamp(),
  finished_at       timestamptz,
  git_commit        text,
  git_dirty         boolean,
  code_sha256       text,
  candidates_sha256 text NOT NULL,
  protocol_sha256   text NOT NULL,
  study_set         jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS realworld.repo_result (
  analysis_id   uuid NOT NULL REFERENCES realworld.analysis (analysis_id) ON DELETE CASCADE,
  repo          text NOT NULL,
  commit_sha    text NOT NULL,
  schema_path   text NOT NULL,
  status        text NOT NULL CHECK (status IN ('ok', 'failed')),
  error         text,
  duration_s    double precision NOT NULL,
  finding_count integer NOT NULL,
  PRIMARY KEY (analysis_id, repo)
);

CREATE TABLE IF NOT EXISTS realworld.finding (
  analysis_id   uuid NOT NULL REFERENCES realworld.analysis (analysis_id) ON DELETE CASCADE,
  finding_id    text NOT NULL,
  repo          text NOT NULL,
  commit_sha    text NOT NULL,
  rule_id       text NOT NULL,
  severity      text NOT NULL,
  confidence    text NOT NULL,
  file          text NOT NULL,
  line          integer NOT NULL,
  end_line      integer,
  fingerprint   text NOT NULL,
  title         text NOT NULL,
  body          text NOT NULL,
  evidence      jsonb NOT NULL,
  suggested_fix text,
  PRIMARY KEY (analysis_id, finding_id)
);
"""


class RealWorldStore:
    def __init__(self, database_url: str) -> None:
        self.conn = psycopg.connect(database_url, autocommit=True, row_factory=dict_row)
        self.conn.execute(SCHEMA_SQL)

    def close(self) -> None:
        self.conn.close()

    def start(
        self,
        analysis_id: str,
        *,
        state: dict[str, Any],
        candidates_sha256: str,
        protocol_sha256: str,
        study_set: list[str],
    ) -> None:
        self.conn.execute(
            """INSERT INTO realworld.analysis (analysis_id, git_commit, git_dirty, code_sha256,
                 candidates_sha256, protocol_sha256, study_set)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                analysis_id,
                state["commit"],
                state["dirty"],
                state["sha256"],
                candidates_sha256,
                protocol_sha256,
                json.dumps(study_set),
            ),
        )

    def finish(self, analysis_id: str) -> None:
        self.conn.execute(
            "UPDATE realworld.analysis SET finished_at = clock_timestamp() WHERE analysis_id = %s",
            (analysis_id,),
        )

    def add_repo(
        self,
        analysis_id: str,
        result: dict[str, Any],
        findings: list[dict[str, Any]],
    ) -> None:
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO realworld.repo_result (analysis_id, repo, commit_sha, schema_path,
                     status, error, duration_s, finding_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    analysis_id,
                    result["repo"],
                    result["commit_sha"],
                    result["schema_path"],
                    result["status"],
                    result["error"],
                    result["duration_s"],
                    len(findings),
                ),
            )
            cursor.executemany(
                """INSERT INTO realworld.finding (analysis_id, finding_id, repo, commit_sha,
                     rule_id, severity, confidence, file, line, end_line, fingerprint, title,
                     body, evidence, suggested_fix)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (
                        analysis_id,
                        f["finding_id"],
                        result["repo"],
                        result["commit_sha"],
                        f["ruleId"],
                        f["severity"],
                        f["confidence"],
                        f["file"],
                        f["line"],
                        f.get("endLine"),
                        f["fingerprint"],
                        f["title"],
                        f["body"],
                        json.dumps(f["evidence"]),
                        f.get("suggestedFix"),
                    )
                    for f in findings
                ],
            )

    def latest(self) -> str | None:
        row = self.conn.execute(
            "SELECT analysis_id FROM realworld.analysis ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return str(row["analysis_id"]) if row else None

    def analysis(self, analysis_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM realworld.analysis WHERE analysis_id = %s", (analysis_id,)
        ).fetchone()
        if row is None:
            raise KeyError(analysis_id)
        return row

    def repos(self, analysis_id: str) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM realworld.repo_result WHERE analysis_id = %s ORDER BY repo",
            (analysis_id,),
        ).fetchall()

    def findings(self, analysis_id: str) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM realworld.finding WHERE analysis_id = %s ORDER BY finding_id",
            (analysis_id,),
        ).fetchall()
