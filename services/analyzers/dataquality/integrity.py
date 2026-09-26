"""Referential-integrity checks against the DECLARED relations.

For every relation in schema.prisma whose foreign-key fields live on this
model, count child rows whose (fully non-null) key matches no parent row.
The relations come from the declared schema and the rows from the live
database; the two are never merged into one schema. Whether the database
also enforces the constraint is a different question (RQ6), answered by the
schema comparison, not here.

Rows with a NULL in any key column are exempt, exactly as PostgreSQL treats
them (MATCH SIMPLE). Implicit many-to-many relations have no key fields on
either model and are not checked.
"""

import hashlib
from typing import Any

import psycopg
from psycopg import sql

from ..finding import Evidence, Finding
from ..schema.actual import ActualSchema
from ..schema.declared import DeclaredSchema
from .models import IntegrityCheck

ORPHANED_FOREIGN_KEY = "ORPHANED_FOREIGN_KEY"


def _has_columns(actual: ActualSchema, table: str, columns: list[str]) -> bool:
    found = actual.table(table)
    return found is not None and all(found.column(column) is not None for column in columns)


def check_integrity(
    conn: psycopg.Connection[Any], declared: DeclaredSchema, actual: ActualSchema
) -> tuple[list[IntegrityCheck], dict[str, str]]:
    """Returns (checks, skipped): `skipped` maps 'Model.relation' to why it was not checkable."""
    checks: list[IntegrityCheck] = []
    skipped: dict[str, str] = {}

    for model in declared.models:
        if model.block_type != "model":
            continue
        for relation in model.relations:
            if relation.foreign_key_on != "self":
                continue
            label = f"{model.name}.{relation.field}"
            parent = declared.model(relation.referenced_model)
            if parent is None:
                skipped[label] = f"referenced model {relation.referenced_model} is not declared"
                continue

            child_columns = [_column(model, name) for name in relation.fields]
            parent_columns = [_column(parent, name) for name in relation.references]
            if len(child_columns) != len(parent_columns) or not child_columns:
                skipped[label] = "relation has no matching fields/references"
                continue
            if not _has_columns(actual, model.table, child_columns) or not _has_columns(
                actual, parent.table, parent_columns
            ):
                skipped[label] = "table or columns missing from the database"
                continue

            checked, orphans = _count(
                conn, actual.schema_name, model.table, child_columns, parent.table, parent_columns
            )
            checks.append(
                IntegrityCheck(
                    model=model.name,
                    relation=relation.field,
                    table=model.table,
                    columns=child_columns,
                    referenced_table=parent.table,
                    referenced_columns=parent_columns,
                    checked_rows=checked,
                    orphan_rows=orphans,
                    orphan_rate=(orphans / checked) if checked else None,
                    line=relation.line,
                )
            )
    return checks, skipped


def _column(model: Any, field_name: str) -> str:
    field = model.field(field_name)
    return field.column if field else field_name


def _count(
    conn: psycopg.Connection[Any],
    schema: str,
    table: str,
    columns: list[str],
    parent_table: str,
    parent_columns: list[str],
) -> tuple[int, int]:
    match = sql.SQL(" AND ").join(
        sql.SQL("p.{} = c.{}").format(sql.Identifier(p), sql.Identifier(c))
        for c, p in zip(columns, parent_columns, strict=True)
    )
    not_null = sql.SQL(" AND ").join(
        sql.SQL("c.{} IS NOT NULL").format(sql.Identifier(c)) for c in columns
    )
    query = sql.SQL(
        "SELECT count(*), "
        "count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM {parent} p WHERE {match})) "
        "FROM {child} c WHERE {not_null}"
    ).format(
        parent=sql.Identifier(schema, parent_table),
        match=match,
        child=sql.Identifier(schema, table),
        not_null=not_null,
    )
    row = conn.execute(query).fetchone()
    assert row is not None
    return int(row[0]), int(row[1])


def to_findings(checks: list[IntegrityCheck], schema_file: str) -> list[Finding]:
    """One finding per relation with at least one orphaned row."""
    findings = []
    for check in checks:
        if check.orphan_rows == 0:
            continue
        key = ", ".join(check.columns)
        target = f"{check.referenced_table}({', '.join(check.referenced_columns)})"
        data = {
            "table": check.table,
            "column": check.columns[0],
            "columns": check.columns,
            "referencedTable": check.referenced_table,
            "orphanRows": check.orphan_rows,
            "checkedRows": check.checked_rows,
            "orphanRate": check.orphan_rate,
        }
        findings.append(
            Finding(
                schema_version=1,
                rule_id=ORPHANED_FOREIGN_KEY,
                severity="MEDIUM",
                confidence="HIGH",
                file=schema_file,
                line=check.line,
                title=(
                    f"{check.orphan_rows} orphaned {check.table}({key}) rows "
                    f"reference no {check.referenced_table}"
                ),
                body=(
                    f"Relation `{check.model}.{check.relation}` declares that `{check.table}` "
                    f"({key}) references {target}, but {check.orphan_rows} of {check.checked_rows} "
                    "rows have a key with no matching parent. Queries that join through the "
                    "relation silently lose or null out "
                    "these rows."
                ),
                evidence=[
                    Evidence(
                        source="DATA_QUALITY",
                        description=(
                            f"{check.orphan_rows} of {check.checked_rows} non-null keys "
                            "have no parent row"
                        ),
                        data=data,
                    ),
                    Evidence(
                        source="DECLARED_SCHEMA",
                        description=f"{check.model}.{check.relation} references {target}",
                        file=schema_file,
                        line=check.line,
                        data={
                            "model": check.model,
                            "table": check.table,
                            "column": check.columns[0],
                        },
                    ),
                ],
                suggested_fix=(
                    "```sql\n-- Find the orphans, repair or remove them, then restore the FK:\n"
                    f'SELECT c.* FROM "{check.table}" c\n'
                    f'WHERE c."{check.columns[0]}" IS NOT NULL AND NOT EXISTS (\n'
                    f'  SELECT 1 FROM "{check.referenced_table}" p\n'
                    f'  WHERE p."{check.referenced_columns[0]}" = c."{check.columns[0]}");\n```'
                ),
                fingerprint=hashlib.sha256(
                    "\x00".join([ORPHANED_FOREIGN_KEY, schema_file, check.table, key]).encode()
                ).hexdigest()[:32],
            )
        )
    return sorted(findings, key=lambda f: (f.file, f.line, f.fingerprint))
