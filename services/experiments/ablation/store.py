"""Ablation results in Postgres (schema `ablation`). Raw rows only, nothing aggregated at write.

One `result` row per (run, problem type), and a run is one (configuration, app, repetition), so the
table has one row per (config, app, repetition, problemType). Means, intervals and tests are
computed at analysis time from these rows.
"""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .layers import Configuration
from .pipeline import RunResult

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS ablation;

CREATE TABLE IF NOT EXISTS ablation.experiment (
  experiment_id  uuid PRIMARY KEY,
  started_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
  finished_at    timestamptz,
  git_commit     text,
  git_dirty      boolean,
  -- Hash of `git status` + `git diff HEAD`: names the code under test even when uncommitted.
  code_sha256    text,
  repetitions    integer NOT NULL,
  seed           integer NOT NULL,
  apps           text[] NOT NULL,
  configurations jsonb NOT NULL,
  universe       jsonb NOT NULL,
  parameters     jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS ablation.run (
  run_id             uuid PRIMARY KEY,
  experiment_id      uuid NOT NULL REFERENCES ablation.experiment (experiment_id) ON DELETE CASCADE,
  config             text NOT NULL,
  app                text NOT NULL,
  repetition         integer NOT NULL,
  sensitivity        boolean NOT NULL,
  started_at         timestamptz NOT NULL DEFAULT clock_timestamp(),
  wall_s             double precision NOT NULL,
  cpu_s              double precision NOT NULL,
  correlation_wall_s double precision NOT NULL,
  layer_available_s  jsonb NOT NULL,
  layer_wall_s       jsonb NOT NULL,
  layer_cpu_s        jsonb NOT NULL,
  finding_count      integer NOT NULL,
  raw_finding_count  integer NOT NULL,
  load_session       uuid,
  UNIQUE (experiment_id, config, app, repetition)
);

CREATE TABLE IF NOT EXISTS ablation.result (
  run_id              uuid NOT NULL REFERENCES ablation.run (run_id) ON DELETE CASCADE,
  problem_type        text NOT NULL,
  entries             integer NOT NULL,
  tp                  integer NOT NULL,
  fp                  integer NOT NULL,
  fn                  integer NOT NULL,
  duplicates          integer NOT NULL,
  precision           double precision,
  recall              double precision,
  f1                  double precision,
  fpr                 double precision,
  mean_tp_confidence  double precision,
  detection_latency_s double precision,
  PRIMARY KEY (run_id, problem_type)
);

-- The findings behind every run, so a number can always be traced to what produced it.
CREATE TABLE IF NOT EXISTS ablation.run_findings (
  run_id    uuid NOT NULL REFERENCES ablation.run (run_id) ON DELETE CASCADE,
  stage     text NOT NULL,      -- a layer name, or 'correlated'
  findings  jsonb NOT NULL,
  PRIMARY KEY (run_id, stage)
);
"""

REPO_ROOT = Path(__file__).resolve().parents[3]


def code_state() -> dict[str, Any]:
    """Which code produced these results: commit, whether it was clean, hash of any changes."""

    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
        )
        return done.stdout if done.returncode == 0 else ""

    commit = git("rev-parse", "--short", "HEAD").strip() or None
    status = git("status", "--porcelain")
    untracked = "".join(
        (REPO_ROOT / line[3:]).read_text(errors="ignore")
        if (REPO_ROOT / line[3:]).is_file()
        else ""
        for line in status.splitlines()
        if line.startswith("??")
    )
    digest = hashlib.sha256((status + git("diff", "HEAD") + untracked).encode()).hexdigest()
    return {"commit": commit, "dirty": bool(status.strip()), "sha256": digest}


class AblationStore:
    def __init__(self, database_url: str) -> None:
        self.conn = psycopg.connect(database_url, autocommit=True, row_factory=dict_row)
        self.conn.execute(SCHEMA_SQL)

    def close(self) -> None:
        self.conn.close()

    def start_experiment(
        self,
        experiment_id: str,
        *,
        repetitions: int,
        seed: int,
        apps: list[str],
        configurations: dict[str, Configuration],
        universe: dict[str, dict[str, int]],
        parameters: dict[str, Any],
    ) -> None:
        state = code_state()
        snapshot = {
            name: {
                "layers": [layer.value for layer in c.ordered_layers()],
                "description": c.description,
                "sensitivity": c.sensitivity,
                "sql_source": c.sql_source,
            }
            for name, c in configurations.items()
        }
        self.conn.execute(
            """INSERT INTO ablation.experiment (experiment_id, git_commit, git_dirty,
                 code_sha256, repetitions, seed, apps, configurations, universe, parameters)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                experiment_id,
                state["commit"],
                state["dirty"],
                state["sha256"],
                repetitions,
                seed,
                apps,
                json.dumps(snapshot),
                json.dumps(universe),
                json.dumps(parameters),
            ),
        )

    def finish_experiment(self, experiment_id: str) -> None:
        self.conn.execute(
            "UPDATE ablation.experiment SET finished_at = clock_timestamp() "
            "WHERE experiment_id = %s",
            (experiment_id,),
        )

    def add_run(
        self, experiment_id: str, run_id: str, result: RunResult, *, sensitivity: bool
    ) -> None:
        raw = sum(len(f) for f in result.layer_findings.values())
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO ablation.run (run_id, experiment_id, config, app, repetition,
                     sensitivity, wall_s, cpu_s, correlation_wall_s, layer_available_s,
                     layer_wall_s, layer_cpu_s, finding_count, raw_finding_count, load_session)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    run_id,
                    experiment_id,
                    result.config,
                    result.app,
                    result.repetition,
                    sensitivity,
                    result.wall_s,
                    result.cpu_s,
                    result.correlation_wall_s,
                    json.dumps(result.available_at),
                    json.dumps(result.layer_wall_s),
                    json.dumps(result.layer_cpu_s),
                    len(result.findings),
                    raw,
                    result.load_session,
                ),
            )
            cursor.executemany(
                """INSERT INTO ablation.result (run_id, problem_type, entries, tp, fp, fn,
                     duplicates, precision, recall, f1, fpr, mean_tp_confidence,
                     detection_latency_s)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (
                        run_id,
                        r.problem_type,
                        r.entries,
                        r.tp,
                        r.fp,
                        r.fn,
                        r.duplicates,
                        r.precision,
                        r.recall,
                        r.f1,
                        r.fpr,
                        r.mean_tp_confidence,
                        r.detection_latency_s,
                    )
                    for r in result.rows
                ],
            )
            stages = {**result.layer_findings, "correlated": result.findings}
            cursor.executemany(
                "INSERT INTO ablation.run_findings (run_id, stage, findings) VALUES (%s, %s, %s)",
                [
                    (
                        run_id,
                        stage,
                        json.dumps(
                            [
                                f.model_dump(mode="json", by_alias=True, exclude_none=True)
                                for f in findings
                            ]
                        ),
                    )
                    for stage, findings in stages.items()
                ],
            )

    # ---- reads -----------------------------------------------------------

    def experiments(self) -> list[dict[str, Any]]:
        return self.conn.execute(
            """SELECT e.*,
                      (SELECT count(*) FROM ablation.run r
                       WHERE r.experiment_id = e.experiment_id) AS runs
               FROM ablation.experiment e ORDER BY started_at DESC"""
        ).fetchall()

    def latest_experiment(self) -> str | None:
        row = self.conn.execute(
            "SELECT experiment_id FROM ablation.experiment ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return str(row["experiment_id"]) if row else None

    def results(self, experiment_id: str) -> list[dict[str, Any]]:
        """Every result row with its run's identifying columns: the input to analysis."""
        return self.conn.execute(
            """SELECT r.config, r.app, r.repetition, r.sensitivity, r.wall_s, r.cpu_s, x.*
               FROM ablation.run r JOIN ablation.result x USING (run_id)
               WHERE r.experiment_id = %s ORDER BY r.config, r.app, r.repetition, x.problem_type""",
            (experiment_id,),
        ).fetchall()

    def runs(self, experiment_id: str) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM ablation.run WHERE experiment_id = %s ORDER BY config, app, repetition",
            (experiment_id,),
        ).fetchall()
