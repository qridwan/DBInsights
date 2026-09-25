"""Compares the declared schema (schema.prisma) with the actual one (PostgreSQL).

Takes the two as separate inputs and reports where they disagree; it never
builds a merged schema. The disagreement itself is the RQ6 measurement.

Index identity is (kind, ordered key columns, partial predicate):
- kind: primary (@id/@@id), unique (@unique/@@unique), index (@@index/@@fulltext);
- key columns in index order, using database column names (@map applied);
- expression and partial indexes can never match a declared one, because
  schema.prisma cannot express them.
Sort order, operator class and access method are not part of identity.
"""

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..finding import Evidence, Finding
from .actual import PRISMA_MIGRATIONS_TABLE, ActualIndex, ActualSchema, ActualTable
from .declared import (
    DeclaredIndex,
    DeclaredModel,
    DeclaredSchema,
    expected_column_type,
    expected_nullable,
)

IndexKind = Literal["primary", "unique", "index"]
_DECLARED_KIND: dict[str, IndexKind] = {
    "id": "primary",
    "unique": "unique",
    "index": "index",
    "fulltext": "index",
}

INDEX_NOT_DECLARED = "INDEX_NOT_DECLARED"
DECLARED_INDEX_NOT_APPLIED = "DECLARED_INDEX_NOT_APPLIED"
COLUMN_TYPE_MISMATCH = "COLUMN_TYPE_MISMATCH"
COLUMN_NULLABILITY_MISMATCH = "COLUMN_NULLABILITY_MISMATCH"
COLUMN_NOT_APPLIED = "COLUMN_NOT_APPLIED"


class _Report(BaseModel):
    model_config = ConfigDict(frozen=True)


class IndexDivergence(_Report):
    model: str
    table: str
    kind: IndexKind
    #: Key columns (database names), or expression text for expression keys.
    columns: list[str]
    #: Plain table columns the index covers.
    referenced_columns: list[str]
    predicate: str | None = None
    #: Actual index name (actual-only) or declared map/name (declared-only).
    index_name: str | None = None
    definition: str | None = None
    #: Line in schema.prisma: the declared index, or the model for actual-only indexes.
    line: int


class ColumnMismatch(_Report):
    model: str
    table: str
    column: str
    field: str
    problem: Literal["type", "nullability", "missing"]
    declared: str | None
    actual: str | None
    line: int


class ForeignKeyDivergence(_Report):
    table: str
    columns: list[str]
    referenced_table: str


class DivergenceReport(_Report):
    #: In the database, not in schema.prisma.
    indexes_not_declared: list[IndexDivergence]
    #: In schema.prisma, not in the database.
    declared_indexes_not_applied: list[IndexDivergence]
    column_mismatches: list[ColumnMismatch]
    #: Declared models with no table (report only; no finding type yet).
    tables_not_applied: list[str]
    #: Tables with no declared model, excluding Prisma's own tables (report only).
    tables_not_declared: list[str]
    #: Declared relations whose FK constraint is absent (report only).
    foreign_keys_not_applied: list[ForeignKeyDivergence]
    #: FK constraints with no declared relation (report only).
    foreign_keys_not_declared: list[ForeignKeyDivergence]


def _implicit_join_tables(declared: DeclaredSchema) -> set[str]:
    """Tables Prisma creates for implicit many-to-many relations (`_AToB` or `_Name`)."""
    tables: set[str] = set()
    for model in declared.models:
        for relation in model.relations:
            if relation.foreign_key_on == "implicit-many-to-many":
                first, second = sorted([model.name, relation.referenced_model])
                tables.add(f"_{relation.name}" if relation.name else f"_{first}To{second}")
    return tables


def _declared_columns(model: DeclaredModel, index: DeclaredIndex) -> list[str]:
    columns: list[str] = []
    for field in index.fields:
        declared = model.field(field.name)
        columns.append(declared.column if declared else field.name)
    return columns


def _actual_key(index: ActualIndex) -> tuple[str, tuple[str, ...], str | None]:
    return (index.kind, tuple(index.columns), index.predicate)


def _compare_indexes(
    model: DeclaredModel, table: ActualTable
) -> tuple[list[IndexDivergence], list[IndexDivergence]]:
    declared = {
        (_DECLARED_KIND[index.kind], tuple(_declared_columns(model, index)), None): index
        for index in model.indexes
    }
    actual = {_actual_key(index): index for index in table.indexes}

    not_declared = [
        IndexDivergence(
            model=model.name,
            table=table.name,
            kind=index.kind,
            columns=index.columns,
            referenced_columns=index.referenced_columns,
            predicate=index.predicate,
            index_name=index.name,
            definition=index.definition,
            line=model.line,
        )
        for key, index in actual.items()
        if key not in declared
    ]
    not_applied = [
        IndexDivergence(
            model=model.name,
            table=table.name,
            kind=key[0],
            columns=list(key[1]),
            referenced_columns=list(key[1]),
            index_name=index.map or index.name,
            line=index.line,
        )
        for key, index in declared.items()
        if key not in actual
    ]
    return not_declared, not_applied


def _compare_columns(
    model: DeclaredModel, table: ActualTable, declared: DeclaredSchema
) -> list[ColumnMismatch]:
    mismatches: list[ColumnMismatch] = []
    for field in model.fields:
        if field.kind not in ("scalar", "enum"):
            continue
        base = {
            "model": model.name,
            "table": table.name,
            "column": field.column,
            "field": field.name,
        }
        column = table.column(field.column)
        if column is None:
            mismatches.append(
                ColumnMismatch(
                    **base, problem="missing", declared=field.type, actual=None, line=field.line
                )
            )
            continue
        expected = expected_column_type(field, declared)
        actual_type = column.data_type.replace('"', "")
        if expected is not None and expected != actual_type:
            mismatches.append(
                ColumnMismatch(
                    **base, problem="type", declared=expected, actual=actual_type, line=field.line
                )
            )
        nullable = expected_nullable(field)
        if nullable != column.nullable:
            mismatches.append(
                ColumnMismatch(
                    **base,
                    problem="nullability",
                    declared="NULL" if nullable else "NOT NULL",
                    actual="NULL" if column.nullable else "NOT NULL",
                    line=field.line,
                )
            )
    return mismatches


def compare(declared: DeclaredSchema, actual: ActualSchema) -> DivergenceReport:
    ignored = _implicit_join_tables(declared) | {PRISMA_MIGRATIONS_TABLE}
    models = [model for model in declared.models if model.block_type == "model"]
    tables_by_model = {model.table: model for model in models}

    not_declared: list[IndexDivergence] = []
    not_applied: list[IndexDivergence] = []
    columns: list[ColumnMismatch] = []
    fk_not_applied: list[ForeignKeyDivergence] = []
    fk_not_declared: list[ForeignKeyDivergence] = []
    missing_tables: list[str] = []

    for model in models:
        table = actual.table(model.table)
        if table is None:
            missing_tables.append(model.table)
            continue
        extra, missing = _compare_indexes(model, table)
        not_declared += extra
        not_applied += missing
        columns += _compare_columns(model, table, declared)

        declared_fks = {
            (
                tuple(model.field(f).column if model.field(f) else f for f in relation.fields),
                target.table
                if (target := declared.model(relation.referenced_model))
                else relation.referenced_model,
            )
            for relation in model.relations
            if relation.foreign_key_on == "self"
        }
        actual_fks = {(tuple(fk.columns), fk.referenced_table) for fk in table.foreign_keys}
        fk_not_applied += [
            ForeignKeyDivergence(table=table.name, columns=list(cols), referenced_table=ref)
            for cols, ref in sorted(declared_fks - actual_fks)
        ]
        fk_not_declared += [
            ForeignKeyDivergence(table=table.name, columns=list(cols), referenced_table=ref)
            for cols, ref in sorted(actual_fks - declared_fks)
        ]

    return DivergenceReport(
        indexes_not_declared=not_declared,
        declared_indexes_not_applied=not_applied,
        column_mismatches=columns,
        tables_not_applied=missing_tables,
        tables_not_declared=[
            t.name for t in actual.tables if t.name not in tables_by_model and t.name not in ignored
        ],
        foreign_keys_not_applied=fk_not_applied,
        foreign_keys_not_declared=fk_not_declared,
    )


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


def _fingerprint(rule_id: str, file: str, *parts: str) -> str:
    return hashlib.sha256("\x00".join([rule_id, file, *parts]).encode()).hexdigest()[:32]


def _signature(divergence: IndexDivergence) -> str:
    where = f" WHERE {divergence.predicate}" if divergence.predicate else ""
    return f"{divergence.kind}({','.join(divergence.columns)}){where}"


def _location(divergence: IndexDivergence) -> dict[str, object]:
    return {
        "table": divergence.table,
        "column": divergence.referenced_columns[0] if divergence.referenced_columns else None,
        "columns": divergence.referenced_columns,
    }


def _index_not_declared(divergence: IndexDivergence, schema_file: str) -> Finding:
    expressible = (
        divergence.predicate is None and divergence.columns == divergence.referenced_columns
    )
    attribute = {"primary": "@@id", "unique": "@@unique", "index": "@@index"}[divergence.kind]
    columns = ", ".join(divergence.columns)
    fix = (
        f"```prisma\nmodel {divergence.model} {{\n  // ...\n  {attribute}([{columns}])\n}}\n```"
        if expressible
        else "```sql\n-- schema.prisma cannot express this index; record it in a migration\n"
        f"-- and keep it under review:\n{divergence.definition};\n```"
    )
    return Finding(
        schema_version=1,
        rule_id=INDEX_NOT_DECLARED,
        severity="MEDIUM",
        confidence="HIGH",
        file=schema_file,
        line=divergence.line,
        title=f"Index {divergence.index_name} exists in the database but not in schema.prisma",
        body=(
            f"`{divergence.table}` has `{divergence.definition}`, which model "
            f"`{divergence.model}` does not declare. Tools and reviewers reading schema.prisma "
            "will not know it exists, and `prisma migrate dev` "
            "will try to drop it."
        ),
        evidence=[
            Evidence(
                source="ACTUAL_SCHEMA",
                description=f"pg_catalog lists {divergence.definition}",
                data={
                    **_location(divergence),
                    "index": divergence.index_name,
                    "predicate": divergence.predicate,
                },
            ),
            Evidence(
                source="DECLARED_SCHEMA",
                description=f"Model {divergence.model} declares no {_signature(divergence)}",
                file=schema_file,
                line=divergence.line,
                data={"model": divergence.model, **_location(divergence)},
            ),
        ],
        suggested_fix=fix,
        fingerprint=_fingerprint(
            INDEX_NOT_DECLARED, schema_file, divergence.table, _signature(divergence)
        ),
    )


def _declared_index_not_applied(divergence: IndexDivergence, schema_file: str) -> Finding:
    name = divergence.index_name or f"{divergence.table}_{'_'.join(divergence.columns)}_idx"
    unique = "UNIQUE " if divergence.kind != "index" else ""
    quoted = ", ".join(f'"{column}"' for column in divergence.columns)
    listed = ", ".join(divergence.columns)
    return Finding(
        schema_version=1,
        rule_id=DECLARED_INDEX_NOT_APPLIED,
        severity="MEDIUM",
        confidence="HIGH",
        file=schema_file,
        line=divergence.line,
        title=f"Declared {divergence.kind} on {divergence.table}({listed}) missing in the database",
        body=(
            f"Model `{divergence.model}` declares a {divergence.kind} on ({listed}) at line "
            f"{divergence.line}, but no matching index exists on `{divergence.table}`. "
            "Static analysis that trusts "
            "schema.prisma will assume queries on these columns are indexed."
        ),
        evidence=[
            Evidence(
                source="DECLARED_SCHEMA",
                description=f"schema.prisma declares {_signature(divergence)}",
                file=schema_file,
                line=divergence.line,
                data={"model": divergence.model, **_location(divergence)},
            ),
            Evidence(
                source="ACTUAL_SCHEMA",
                description=f"pg_catalog has no {divergence.kind} on {divergence.table}({listed})",
                data=_location(divergence),
            ),
        ],
        suggested_fix=(
            f'```sql\nCREATE {unique}INDEX "{name}" ON "{divergence.table}" ({quoted});\n```'
        ),
        fingerprint=_fingerprint(
            DECLARED_INDEX_NOT_APPLIED, schema_file, divergence.table, _signature(divergence)
        ),
    )


_COLUMN_RULES = {
    "type": COLUMN_TYPE_MISMATCH,
    "nullability": COLUMN_NULLABILITY_MISMATCH,
    "missing": COLUMN_NOT_APPLIED,
}


def _column_finding(mismatch: ColumnMismatch, schema_file: str) -> Finding:
    rule_id = _COLUMN_RULES[mismatch.problem]
    what = {
        "type": f"declared type {mismatch.declared}, actual {mismatch.actual}",
        "nullability": f"declared {mismatch.declared}, actual {mismatch.actual}",
        "missing": "declared but absent from the table",
    }[mismatch.problem]
    location = {"table": mismatch.table, "column": mismatch.column}
    return Finding(
        schema_version=1,
        rule_id=rule_id,
        severity="MEDIUM",
        confidence="HIGH",
        file=schema_file,
        line=mismatch.line,
        title=f"{mismatch.table}.{mismatch.column}: {what}",
        body=(
            f"Field `{mismatch.model}.{mismatch.field}` maps to column "
            f"`{mismatch.table}.{mismatch.column}`: {what}."
        ),
        evidence=[
            Evidence(
                source="DECLARED_SCHEMA",
                description=f"{mismatch.model}.{mismatch.field}: {mismatch.declared}",
                file=schema_file,
                line=mismatch.line,
                data=location,
            ),
            Evidence(
                source="ACTUAL_SCHEMA",
                description=f"{mismatch.table}.{mismatch.column}: {mismatch.actual or 'absent'}",
                data=location,
            ),
        ],
        suggested_fix=(
            "```bash\n# Create a migration that reconciles the two, e.g.:\n"
            "npx prisma migrate dev --create-only\n```"
        ),
        fingerprint=_fingerprint(rule_id, schema_file, mismatch.table, mismatch.column),
    )


def to_findings(report: DivergenceReport, schema_file: str) -> list[Finding]:
    """Findings for the divergence categories RQ6 measures (indexes and columns)."""
    findings = [_index_not_declared(d, schema_file) for d in report.indexes_not_declared]
    findings += [
        _declared_index_not_applied(d, schema_file) for d in report.declared_indexes_not_applied
    ]
    findings += [_column_finding(m, schema_file) for m in report.column_mismatches]
    return sorted(findings, key=lambda f: (f.file, f.line, f.rule_id, f.fingerprint))
