"""The non-finding views, as JSON-ready snapshots taken during a scan.

Query analytics come from the runtime events the collector recorded during the scan's load run.
Data quality shows each column's current value beside the range learned from its own history.
The schema view keeps the declared and actual schemas as two separate structures, side by side,
and never merges them; their divergence is the comparator's report (RQ6).
"""

from typing import Any

import psycopg
from psycopg.rows import dict_row

from analyzers.anomaly.pipeline import MetricAnalysis
from analyzers.dataquality.models import ColumnProfile
from analyzers.schema.actual import ActualSchema
from analyzers.schema.declared import DeclaredSchema
from analyzers.schema.divergence import DivergenceReport

TOP = 12

_SESSION = """(%(session)s::uuid IS NULL OR EXISTS (
        SELECT 1 FROM experiments.load_run r
        WHERE r.session_id = %(session)s::uuid AND NOT r.warmup
          AND o.started_at BETWEEN r.window_start AND r.window_end))"""

_BY_FINGERPRINT = f"""
SELECT s.fingerprint, min(s.normalized_sql) AS sql, count(*) AS executions,
       avg(s.duration_ms) AS mean_ms,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY s.duration_ms) AS p95_ms,
       max(s.duration_ms) AS max_ms, sum(s.duration_ms) AS total_ms,
       array_agg(DISTINCT o.route) FILTER (WHERE o.route IS NOT NULL) AS routes
FROM runtime.operation o JOIN runtime.statement s USING (operation_id)
WHERE o.app = %(app)s AND {_SESSION}
GROUP BY s.fingerprint
"""

_BY_ROUTE = f"""
WITH per_request AS (
  SELECT o.route, o.request_id, s.fingerprint, count(*) AS n, min(s.normalized_sql) AS sql
  FROM runtime.operation o JOIN runtime.statement s USING (operation_id)
  WHERE o.app = %(app)s AND o.route IS NOT NULL AND o.request_id IS NOT NULL AND {_SESSION}
  GROUP BY o.route, o.request_id, s.fingerprint
), worst AS (
  SELECT DISTINCT ON (route, request_id) route, request_id, fingerprint, n, sql
  FROM per_request ORDER BY route, request_id, n DESC
)
SELECT route, count(*) AS requests, avg(n) AS mean_repeats, max(n) AS max_repeats,
       (array_agg(sql ORDER BY n DESC))[1] AS repeated_sql
FROM worst GROUP BY route ORDER BY max_repeats DESC, route
"""


def _floats(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: (float(v) if hasattr(v, "as_tuple") else v) for k, v in r.items()} for r in rows]


def query_analytics(results_url: str, app: str, session: str | None) -> dict[str, Any]:
    params = {"app": app, "session": session}
    with psycopg.connect(results_url, row_factory=dict_row) as conn:
        by_fingerprint = _floats(conn.execute(_BY_FINGERPRINT, params).fetchall())
        by_route = _floats(conn.execute(_BY_ROUTE, params).fetchall())
    return {
        "statements": sum(r["executions"] for r in by_fingerprint),
        "distinct_fingerprints": len(by_fingerprint),
        "slowest": sorted(by_fingerprint, key=lambda r: -(r["p95_ms"] or 0))[:TOP],
        "most_frequent": sorted(by_fingerprint, key=lambda r: -r["executions"])[:TOP],
        "endpoint_repetition": by_route,
    }


def data_quality(
    analyses: list[MetricAnalysis], columns: list[ColumnProfile]
) -> list[dict[str, Any]]:
    """Per column: the current profile, and per metric the observation with each detector's
    learned range."""
    profile = {(c.table, c.column): c for c in columns}
    grouped: dict[tuple[str, str], list[MetricAnalysis]] = {}
    for a in analyses:
        grouped.setdefault((a.table, a.column), []).append(a)
    out = []
    for (table, column), items in sorted(grouped.items()):
        current = profile.get((table, column))
        out.append(
            {
                "table": table,
                "column": column,
                "rows": current.row_count if current else None,
                "null_rate": current.null_rate if current else None,
                "duplicate_rate": current.duplicate_rate if current else None,
                "distinct": current.distinct_count if current else None,
                "metrics": [
                    {
                        "metric": a.metric,
                        "observation": a.observation,
                        "anomalous": a.anomalous,
                        "direction": a.direction,
                        "fired": a.fired,
                        "evaluated": a.evaluated,
                        "detections": [
                            {
                                "detector": d.detector,
                                "evaluated": d.evaluated,
                                "anomalous": d.anomalous,
                                "lower": d.lower,
                                "upper": d.upper,
                                "center": d.center,
                            }
                            for d in a.detections
                        ],
                        "explanation": dict(a.explanation),
                    }
                    for a in sorted(items, key=lambda a: a.metric)
                ],
            }
        )
    return out


def declared_models(declared: DeclaredSchema) -> list[dict[str, Any]]:
    return [
        {
            "model": m.name,
            "table": m.table,
            "fields": [
                {"name": f.name, "column": f.column, "type": f.type, "optional": f.optional}
                for f in m.fields
                if f.kind == "scalar"
            ],
            "indexes": [
                {"kind": i.kind, "columns": [f.name for f in i.fields], "line": i.line}
                for i in m.indexes
            ],
        }
        for m in declared.models
        if m.block_type == "model"
    ]


def declared_only_view(declared: DeclaredSchema | None) -> dict[str, Any]:
    """A scanned project has no database of ours: only the declared schema exists to show."""
    return {
        "declared": declared_models(declared) if declared else [],
        "actual": None,
        "divergence": None,
    }


def schema_view(
    declared: DeclaredSchema, actual: ActualSchema, divergence: DivergenceReport
) -> dict[str, Any]:
    """The two schemas as separate structures, plus their divergence. Never merged."""
    return {
        "declared": declared_models(declared),
        "actual": [
            {
                "table": t.name,
                "columns": [
                    {"name": c.name, "type": c.data_type, "nullable": c.nullable} for c in t.columns
                ],
                "indexes": [
                    {"name": i.name, "columns": list(i.columns), "kind": i.kind} for i in t.indexes
                ],
            }
            for t in actual.tables
        ],
        "divergence": divergence.model_dump(mode="json", by_alias=True),
    }
