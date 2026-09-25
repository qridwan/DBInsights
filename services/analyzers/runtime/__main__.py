"""Runtime N+1 detection over the collector's data in the results database.

    python -m analyzers.runtime --app ecommerce [--session <load-session-uuid>] [--threshold 2]

Prints Finding[] (the scorer's input). With --session, only operations inside
that load session's measured (non-warm-up) runs are considered.
"""

import argparse
import json
import os
import sys

import psycopg
from psycopg.rows import dict_row

from .n_plus_one import DEFAULT_THRESHOLD, Operation, Statement, detect_n_plus_one

_QUERY = """
SELECT o.operation_id, o.app, o.request_id, o.route, o.model, o.operation,
       s.fingerprint, s.normalized_sql, s.position
FROM runtime.operation o LEFT JOIN runtime.statement s USING (operation_id)
WHERE o.app = %(app)s
  AND (%(session)s::uuid IS NULL OR EXISTS (
        SELECT 1 FROM experiments.load_run r
        WHERE r.session_id = %(session)s::uuid AND NOT r.warmup
          AND o.started_at BETWEEN r.window_start AND r.window_end))
ORDER BY o.operation_id, s.position
"""


def load_operations(database_url: str, app: str, session: str | None) -> list[Operation]:
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        rows = conn.execute(_QUERY, {"app": app, "session": session}).fetchall()
    grouped: dict[str, dict] = {}
    for row in rows:
        op = grouped.setdefault(row["operation_id"], {**row, "statements": []})
        if row["fingerprint"] is not None:
            op["statements"].append(Statement(row["fingerprint"], row["normalized_sql"]))
    return [
        Operation(
            app=o["app"],
            request_id=o["request_id"],
            route=o["route"],
            model=o["model"],
            operation=o["operation"],
            statements=tuple(o["statements"]),
        )
        for o in grouped.values()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m analyzers.runtime", description=__doc__)
    parser.add_argument("--app", required=True)
    parser.add_argument("--session", help="restrict to one load-harness session")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--results-database-url",
        default=os.environ.get(
            "DBINSIGHT_RESULTS_DATABASE_URL",
            "postgresql://dbinsight:dbinsight@localhost:5432/dbinsight",
        ),
    )
    args = parser.parse_args(argv)
    findings = detect_n_plus_one(
        load_operations(args.results_database_url, args.app, args.session), threshold=args.threshold
    )
    sys.stdout.write(
        json.dumps(
            [f.model_dump(mode="json", by_alias=True, exclude_none=True) for f in findings],
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
