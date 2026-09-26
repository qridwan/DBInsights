"""Builders for the findings each evidence layer emits, shaped as the real layers emit them."""

from analyzers.finding import Evidence, Finding
from tests.analyzers.conftest import actual, actual_index, column, table

TASK_FILE = "src/app/api/tasks/route.ts"
TASK_ROUTE = "/api/tasks"


def finding(rule_id, *, file, line, confidence, evidence, fingerprint, severity="HIGH", title="t"):
    return Finding(
        schema_version=1,
        rule_id=rule_id,
        severity=severity,
        confidence=confidence,
        file=file,
        line=line,
        title=title,
        body="body",
        evidence=evidence,
        suggested_fix="```ts\nfix\n```",
        fingerprint=fingerprint,
    )


def static_n_plus_one(
    *, file=TASK_FILE, line=12, confidence="MEDIUM", model="Task", fingerprint="s-n1"
):
    return finding(
        "N_PLUS_ONE_IN_LOOP",
        file=file,
        line=line,
        confidence=confidence,
        fingerprint=fingerprint,
        title=f"N+1 query: `{model}.count()` inside a loop",
        evidence=[
            Evidence(
                source="STATIC_SOURCE",
                description="runs inside a for-of loop",
                file=file,
                line=line,
                data={
                    "loopKind": "for-of",
                    "loopLine": line - 1,
                    "model": model,
                    "operation": "count",
                },
            )
        ],
    )


def static_missing_index(
    *,
    file=TASK_FILE,
    line=12,
    confidence="MEDIUM",
    model="Task",
    table_name="Task",
    columns=("assigneeId",),
    fingerprint="s-mi",
):
    return finding(
        "MISSING_INDEX_ON_FILTERED_FIELD",
        file=file,
        line=line,
        confidence=confidence,
        fingerprint=fingerprint,
        title=f"No declared index covers the filter on {model}.{columns[0]}",
        evidence=[
            Evidence(
                source="STATIC_SOURCE",
                description="filters on assigneeId",
                file=file,
                line=line,
                data={"whereFields": list(columns), "model": model, "operation": "count"},
            ),
            Evidence(
                source="DECLARED_SCHEMA",
                description=f"{model} declares no index leading with the filter",
                file="prisma/schema.prisma",
                line=40,
                data={
                    "model": model,
                    "table": table_name,
                    "columns": list(columns),
                    "indexes": ["id(id)"],
                },
            ),
        ],
    )


def runtime_n_plus_one(
    *,
    route=TASK_ROUTE,
    model="Task",
    peak=300,
    confidence="HIGH",
    fingerprint="r-n1",
    column_name="assigneeId",
):
    q = f'"public"."{model}"'
    sql = f'SELECT {q}."id" FROM {q} WHERE {q}."{column_name}" = %s'
    return finding(
        "RUNTIME_N_PLUS_ONE",
        file=f"route:{route}",
        line=0,
        confidence=confidence,
        fingerprint=fingerprint,
        title=f"N+1 at runtime: {model}.count executed up to {peak}x in one {route} request",
        evidence=[
            Evidence(
                source="RUNTIME",
                description=f"{peak} executions in one request",
                data={
                    "app": "shop",
                    "route": route,
                    "fingerprint": "abc",
                    "model": model,
                    "operation": "count",
                    "threshold": 2,
                    "maxExecutionsPerRequest": peak,
                    "medianExecutionsPerRequest": peak,
                    "requestsAffected": 5,
                    "requestsObserved": 5,
                },
            ),
            Evidence(
                source="SQL", description="Normalized query shape", data={"normalizedSql": sql}
            ),
        ],
    )


def orphan_finding(
    *,
    table_name="Order",
    columns=("customerId",),
    referenced="Customer",
    confidence="HIGH",
    fingerprint="d-orphan",
):
    return finding(
        "ORPHANED_FOREIGN_KEY",
        file="prisma/schema.prisma",
        line=21,
        confidence=confidence,
        fingerprint=fingerprint,
        severity="MEDIUM",
        title=f"339 orphaned {table_name} rows",
        evidence=[
            Evidence(
                source="DATA_QUALITY",
                description="339 of 19746 keys have no parent",
                data={
                    "table": table_name,
                    "column": columns[0],
                    "columns": list(columns),
                    "referencedTable": referenced,
                    "orphanRows": 339,
                    "checkedRows": 19746,
                },
            ),
            Evidence(
                source="DECLARED_SCHEMA",
                description=f"{table_name}.rel references {referenced}",
                file="prisma/schema.prisma",
                line=21,
                data={"model": table_name, "table": table_name, "column": columns[0]},
            ),
        ],
    )


def actual_task_schema(*, indexed: bool, partial: bool = False):
    columns = [column("id", "integer"), column("assigneeId", "integer", position=2)]
    indexes = [actual_index("Task_pkey", "id", primary=True)]
    if indexed:
        extra = {"predicate": '("assigneeId" IS NOT NULL)'} if partial else {}
        indexes.append(actual_index("Task_assigneeId_idx", "assigneeId", **extra))
    return actual(table("Task", columns, indexes))
