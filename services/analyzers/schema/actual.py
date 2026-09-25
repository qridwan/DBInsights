"""The ACTUAL schema: what PostgreSQL really has, read from its catalogs.

Tables and columns come from information_schema (portable, typed through
format_type for exact modifiers); indexes, foreign keys and constraints come
from pg_catalog, which is the only place index column order, expressions and
partial predicates are available.

This is one of two evidence sources for RQ6 and is deliberately a separate
type from `DeclaredSchema`; nothing merges the two.
"""

from typing import Any, Literal

import psycopg
from pydantic import BaseModel, ConfigDict

#: Prisma's own bookkeeping table; never application schema.
PRISMA_MIGRATIONS_TABLE = "_prisma_migrations"


class _Actual(BaseModel):
    model_config = ConfigDict(frozen=True)


class ActualColumn(_Actual):
    name: str
    #: As printed by format_type(), e.g. "timestamp(3) without time zone".
    data_type: str
    nullable: bool
    default: str | None
    position: int


class ActualIndex(_Actual):
    name: str
    #: Key columns in index order. Expression keys appear as their SQL text.
    columns: list[str]
    #: Plain table columns referenced by the keys (including inside expressions).
    referenced_columns: list[str]
    unique: bool
    primary: bool
    method: str
    #: Partial-index predicate, if any.
    predicate: str | None
    definition: str

    @property
    def kind(self) -> Literal["primary", "unique", "index"]:
        return "primary" if self.primary else "unique" if self.unique else "index"

    @property
    def has_expression(self) -> bool:
        return self.columns != self.referenced_columns


class ActualForeignKey(_Actual):
    name: str
    columns: list[str]
    referenced_table: str
    referenced_columns: list[str]
    on_delete: str
    on_update: str


class ActualConstraint(_Actual):
    name: str
    type: Literal["primary_key", "unique", "check", "foreign_key", "exclusion"]
    definition: str


class ActualTable(_Actual):
    name: str
    columns: list[ActualColumn]
    indexes: list[ActualIndex]
    foreign_keys: list[ActualForeignKey]
    constraints: list[ActualConstraint]

    def column(self, name: str) -> ActualColumn | None:
        return next((c for c in self.columns if c.name == name), None)


class ActualSchema(_Actual):
    schema_name: str
    tables: list[ActualTable]

    def table(self, name: str) -> ActualTable | None:
        return next((t for t in self.tables if t.name == name), None)


_TABLES = """
SELECT table_name
FROM information_schema.tables
WHERE table_schema = %(schema)s AND table_type = 'BASE TABLE'
ORDER BY table_name
"""

_COLUMNS = """
SELECT c.table_name, c.column_name, c.is_nullable = 'YES' AS nullable, c.column_default,
       c.ordinal_position, format_type(a.atttypid, a.atttypmod) AS data_type
FROM information_schema.columns c
JOIN pg_catalog.pg_namespace n ON n.nspname = c.table_schema
JOIN pg_catalog.pg_class t ON t.relnamespace = n.oid AND t.relname = c.table_name
JOIN pg_catalog.pg_attribute a ON a.attrelid = t.oid AND a.attname = c.column_name
WHERE c.table_schema = %(schema)s
ORDER BY c.table_name, c.ordinal_position
"""

_INDEXES = """
SELECT t.relname AS table_name, i.relname AS index_name, ix.indisunique, ix.indisprimary,
       am.amname AS method,
       pg_get_expr(ix.indpred, ix.indrelid) AS predicate,
       pg_get_indexdef(ix.indexrelid) AS definition,
       ARRAY(
         SELECT pg_get_indexdef(ix.indexrelid, k + 1, true)
         FROM generate_subscripts(ix.indkey, 1) AS k
         WHERE k < ix.indnkeyatts
         ORDER BY k
       ) AS columns,
       ARRAY(
         SELECT DISTINCT a.attname
         FROM pg_catalog.pg_attribute a
         WHERE a.attrelid = ix.indrelid AND a.attnum > 0 AND (
           a.attnum = ANY (ix.indkey::int2[])
           OR (ix.indexprs IS NOT NULL
               AND pg_get_expr(ix.indexprs, ix.indrelid) ~ ('\\m' || a.attname || '\\M'))
         )
       ) AS expression_columns
FROM pg_catalog.pg_index ix
JOIN pg_catalog.pg_class i ON i.oid = ix.indexrelid
JOIN pg_catalog.pg_class t ON t.oid = ix.indrelid
JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
JOIN pg_catalog.pg_am am ON am.oid = i.relam
WHERE n.nspname = %(schema)s
ORDER BY t.relname, i.relname
"""

_FOREIGN_KEYS = """
SELECT t.relname AS table_name, c.conname,
       ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(attnum, ord)
             JOIN pg_catalog.pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
             ORDER BY k.ord) AS columns,
       rt.relname AS referenced_table,
       ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(attnum, ord)
             JOIN pg_catalog.pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.attnum
             ORDER BY k.ord) AS referenced_columns,
       c.confdeltype, c.confupdtype
FROM pg_catalog.pg_constraint c
JOIN pg_catalog.pg_class t ON t.oid = c.conrelid
JOIN pg_catalog.pg_class rt ON rt.oid = c.confrelid
JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
WHERE c.contype = 'f' AND n.nspname = %(schema)s
ORDER BY t.relname, c.conname
"""

_CONSTRAINTS = """
SELECT t.relname AS table_name, c.conname, c.contype, pg_get_constraintdef(c.oid) AS definition
FROM pg_catalog.pg_constraint c
JOIN pg_catalog.pg_class t ON t.oid = c.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = %(schema)s
ORDER BY t.relname, c.conname
"""

_ACTIONS = {"a": "NO ACTION", "r": "RESTRICT", "c": "CASCADE", "n": "SET NULL", "d": "SET DEFAULT"}
_CONSTRAINT_TYPES = {
    "p": "primary_key",
    "u": "unique",
    "c": "check",
    "f": "foreign_key",
    "x": "exclusion",
}


def _rows(conn: psycopg.Connection[Any], query: str, schema: str) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
        cursor.execute(query, {"schema": schema})
        return list(cursor.fetchall())


def _strip_schema(data_type: str, schema: str) -> str:
    """format_type() qualifies types from a schema outside search_path; drop our own schema."""
    for prefix in (f'"{schema}".', f"{schema}."):
        if data_type.startswith(prefix):
            return data_type[len(prefix) :]
    return data_type


def _unquote(identifier: str) -> str:
    return (
        identifier[1:-1].replace('""', '"')
        if identifier.startswith('"') and identifier.endswith('"')
        else identifier
    )


def read_actual_schema(conn: psycopg.Connection[Any], schema: str = "public") -> ActualSchema:
    """Reads the live schema. Read-only; never modifies the database."""
    names = [row["table_name"] for row in _rows(conn, _TABLES, schema)]
    columns: dict[str, list[ActualColumn]] = {name: [] for name in names}
    indexes: dict[str, list[ActualIndex]] = {name: [] for name in names}
    foreign_keys: dict[str, list[ActualForeignKey]] = {name: [] for name in names}
    constraints: dict[str, list[ActualConstraint]] = {name: [] for name in names}

    for row in _rows(conn, _COLUMNS, schema):
        if row["table_name"] in columns:
            columns[row["table_name"]].append(
                ActualColumn(
                    name=row["column_name"],
                    data_type=_strip_schema(row["data_type"], schema),
                    nullable=row["nullable"],
                    default=row["column_default"],
                    position=row["ordinal_position"],
                )
            )

    for row in _rows(conn, _INDEXES, schema):
        if row["table_name"] in indexes:
            keys = [_unquote(key) for key in row["columns"]]
            table_columns = {c.name for c in columns[row["table_name"]]}
            plain = [key for key in keys if key in table_columns]
            referenced = plain if len(plain) == len(keys) else sorted(row["expression_columns"])
            indexes[row["table_name"]].append(
                ActualIndex(
                    name=row["index_name"],
                    columns=keys,
                    referenced_columns=referenced,
                    unique=row["indisunique"],
                    primary=row["indisprimary"],
                    method=row["method"],
                    predicate=row["predicate"],
                    definition=row["definition"],
                )
            )

    for row in _rows(conn, _FOREIGN_KEYS, schema):
        if row["table_name"] in foreign_keys:
            foreign_keys[row["table_name"]].append(
                ActualForeignKey(
                    name=row["conname"],
                    columns=list(row["columns"]),
                    referenced_table=row["referenced_table"],
                    referenced_columns=list(row["referenced_columns"]),
                    on_delete=_ACTIONS.get(row["confdeltype"], row["confdeltype"]),
                    on_update=_ACTIONS.get(row["confupdtype"], row["confupdtype"]),
                )
            )

    for row in _rows(conn, _CONSTRAINTS, schema):
        if row["table_name"] in constraints and row["contype"] in _CONSTRAINT_TYPES:
            constraints[row["table_name"]].append(
                ActualConstraint(
                    name=row["conname"],
                    type=_CONSTRAINT_TYPES[row["contype"]],
                    definition=row["definition"],
                )
            )

    return ActualSchema(
        schema_name=schema,
        tables=[
            ActualTable(
                name=name,
                columns=columns[name],
                indexes=indexes[name],
                foreign_keys=foreign_keys[name],
                constraints=constraints[name],
            )
            for name in names
        ],
    )


def connect(database_url: str) -> psycopg.Connection[Any]:
    """A read-only connection for schema inspection."""
    conn = psycopg.connect(database_url, autocommit=True)
    conn.execute("SET default_transaction_read_only = on")
    return conn
