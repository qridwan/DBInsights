"""What the correlation engine knows about the schemas and the framework, kept honest.

The declared schema (schema.prisma) and the actual schema (PostgreSQL) stay separate types
here as everywhere: each is asked its own question and each contributes its own evidence.
Either may be absent; a missing layer gives no opinion, never a guess.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from ..schema.actual import ActualForeignKey, ActualIndex, ActualSchema
from ..schema.declared import DeclaredSchema

_ROUTE_FILE = re.compile(r"^route\.(?:[cm]?[jt]sx?)$")


def route_for_file(file: str) -> str | None:
    """The URL route a Next.js App Router handler file serves, or None if it is not one.

    `<...>/app/orders/[id]/invoice/route.ts` -> `/orders/[id]/invoice`. Route groups `(x)` and
    parallel-route slots `@x` do not appear in the URL. Runtime findings report the same
    pattern, which is how a static finding and a runtime finding are recognised as being
    about the same request.
    """
    parts = file.replace("\\", "/").split("/")
    if not _ROUTE_FILE.match(parts[-1]) or "app" not in parts[:-1]:
        return None
    candidates = [i for i, part in enumerate(parts[:-1]) if part == "app"]
    # The router root is the app/ directory under src/ if there is one, else the first app/.
    # (A route folder that is itself called "app", e.g. /app/dashboard, sits below the root.)
    start = next((i for i in candidates if i > 0 and parts[i - 1] == "src"), candidates[0])
    segments = [
        p
        for p in parts[start + 1 : -1]
        if not (p.startswith("(") and p.endswith(")")) and not p.startswith("@")
    ]
    return "/" + "/".join(segments)


def sql_filter_columns(normalized_sql: str) -> list[str]:
    """Names of the columns a query's WHERE clause filters on, in order of first appearance."""
    try:
        tree = sqlglot.parse_one(normalized_sql, read="postgres")
    except SqlglotError:
        return []
    where = tree.find(exp.Where)
    if where is None:
        return []
    seen: list[str] = []
    for column in where.find_all(exp.Column):
        if column.name not in seen:
            seen.append(column.name)
    return seen


@dataclass(frozen=True)
class SchemaFacts:
    declared: DeclaredSchema | None = None
    actual: ActualSchema | None = None

    def table_of(self, model: str) -> str:
        """The database table of a Prisma model (@@map applied), from the declared schema."""
        found = self.declared.model(model) if self.declared else None
        return found.table if found else model

    def actual_has_table(self, table: str) -> bool:
        return self.actual is not None and self.actual.table(table) is not None

    def actual_index_covering(self, table: str, columns: Sequence[str]) -> ActualIndex | None:
        """A plain, full-table index of the database whose leading key is one of `columns`.

        Partial and expression indexes are not counted: they serve only some queries.
        """
        found = self.actual.table(table) if self.actual else None
        if found is None:
            return None
        wanted = set(columns)
        for index in sorted(found.indexes, key=lambda i: i.name):
            if index.predicate is None and not index.has_expression and index.columns[0] in wanted:
                return index
        return None

    def actual_foreign_key(
        self, table: str, columns: Sequence[str], referenced_table: str
    ) -> ActualForeignKey | None:
        found = self.actual.table(table) if self.actual else None
        if found is None:
            return None
        return next(
            (
                fk
                for fk in found.foreign_keys
                if fk.columns == list(columns) and fk.referenced_table == referenced_table
            ),
            None,
        )
