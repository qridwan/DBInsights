"""Runtime N+1 detection.

Within one request, the same query shape (fingerprint) executing more than
`threshold` times is an N+1. The shape comes from SQLGlot AST normalization,
so `IN ($1)` and `IN ($1,...,$50)` count as the same query.

Why the default threshold is 2 (i.e. 3+ executions): a query repeated exactly
twice in a request is the *repeated identical query* pattern, a different
problem type; per-row fan-out starts at three. The threshold is explicit and
reported in each finding's evidence.

Findings are aggregated per (app, route, fingerprint) across all requests
observed, with the per-request counts as evidence. Runtime findings have no
source line: `file` is `route:<pattern>` and `line` is 0; the scorer matches
them to ground truth by the `route` in their evidence.
"""

import hashlib
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from ..finding import Evidence, Finding

RUNTIME_N_PLUS_ONE = "RUNTIME_N_PLUS_ONE"
DEFAULT_THRESHOLD = 2
#: At or above this many executions in one request, confidence is HIGH.
HIGH_CONFIDENCE_EXECUTIONS = 10


@dataclass(frozen=True)
class Statement:
    fingerprint: str
    normalized_sql: str


@dataclass(frozen=True)
class Operation:
    app: str
    request_id: str | None
    route: str | None
    model: str | None
    operation: str
    statements: tuple[Statement, ...]


def detect_n_plus_one(
    operations: Iterable[Operation], *, threshold: int = DEFAULT_THRESHOLD
) -> list[Finding]:
    if threshold < 1:
        raise ValueError("threshold must be at least 1")

    # (app, route, request) -> fingerprint -> executions
    per_request: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    shape: dict[str, tuple[str, str | None, str]] = {}
    for op in operations:
        if op.request_id is None or op.route is None:
            continue  # outside a request (scripts, startup): no request to fan out in
        key = (op.app, op.route, op.request_id)
        per_request[key]  # count requests even when they execute nothing
        for statement in op.statements:
            per_request[key][statement.fingerprint] += 1
            shape.setdefault(
                statement.fingerprint, (statement.normalized_sql, op.model, op.operation)
            )

    # (app, route) -> fingerprint -> executions in each affected request
    affected: dict[tuple[str, str], dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    observed: Counter[tuple[str, str]] = Counter()
    for (app, route, _request), counts in per_request.items():
        observed[(app, route)] += 1
        for fp, executions in counts.items():
            if executions > threshold:
                affected[(app, route)][fp].append(executions)

    findings = []
    for (app, route), shapes in sorted(affected.items()):
        for fp, counts in sorted(shapes.items()):
            normalized_sql, model, operation = shape[fp]
            findings.append(
                _finding(
                    app,
                    route,
                    fp,
                    counts,
                    observed[(app, route)],
                    normalized_sql,
                    model,
                    operation,
                    threshold,
                )
            )
    return findings


def _finding(
    app: str,
    route: str,
    fp: str,
    counts: list[int],
    requests_observed: int,
    normalized_sql: str,
    model: str | None,
    operation: str,
    threshold: int,
) -> Finding:
    peak = max(counts)
    label = f"{model}.{operation}" if model else operation
    return Finding(
        schema_version=1,
        rule_id=RUNTIME_N_PLUS_ONE,
        severity="HIGH",
        confidence="HIGH" if peak >= HIGH_CONFIDENCE_EXECUTIONS else "MEDIUM",
        file=f"route:{route}",
        line=0,
        title=f"N+1 at runtime: {label} executed up to {peak}x in one {route} request",
        body=(
            f"One query shape (`{label}`, fingerprint `{fp}`) ran more than {threshold} times "
            f"within a single request to `{route}` in {len(counts)} of {requests_observed} "
            "observed requests "
            f"(up to {peak} executions per request). The number of queries grows with the data the "
            "request iterates over."
        ),
        evidence=[
            Evidence(
                source="RUNTIME",
                description=f"{peak} executions of fingerprint {fp} in one request to {route}",
                data={
                    "app": app,
                    "route": route,
                    "fingerprint": fp,
                    "model": model,
                    "operation": operation,
                    "threshold": threshold,
                    "maxExecutionsPerRequest": peak,
                    "medianExecutionsPerRequest": statistics.median(counts),
                    "requestsAffected": len(counts),
                    "requestsObserved": requests_observed,
                },
            ),
            Evidence(
                source="SQL",
                description="Normalized query shape",
                data={"normalizedSql": normalized_sql},
            ),
        ],
        suggested_fix=(
            "```ts\n// Load the related rows with the parent query instead of once per row:\n"
            "//   include: { <relation>: true }\n"
            "// or collect the keys and fetch them in one query:\n"
            "//   prisma.<model>.findMany({ where: { id: { in: ids } } })\n```"
        ),
        fingerprint=hashlib.sha256(
            f"{RUNTIME_N_PLUS_ONE}\x00{app}\x00{route}\x00{fp}".encode()
        ).hexdigest()[:32],
    )
