"""Statistical profiling of a live PostgreSQL database.

For every table and column: row count, NULL count and rate, distinct count,
duplicate rate, and (for columns with few distinct values) the frequency of
each value. Profiles can be restricted to a time window over each table's
creation-time column, so consecutive windows build the history that the
anomaly detector (M4.2) learns baselines from.

Nothing here decides what is anomalous, and there are no detection
thresholds. Duplicate rate is computed for every column; which columns
matter is for the detector to learn from their own history. The single
cutoff, `max_categories`, bounds how many categories are *stored* for a
column; it is a storage limit, not a judgement about the data. A column in
which every value is unique has no distribution and stores no categories.

Reads only. Tables and columns come from the actual schema (the live
database), never from schema.prisma.
"""

import re
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg import sql

from ..schema.actual import PRISMA_MIGRATIONS_TABLE, ActualColumn, ActualSchema, ActualTable
from .models import CategoryFrequency, ColumnProfile, TableProfile, Window

DEFAULT_MAX_CATEGORIES = 50

# Prisma's @default(now()) becomes DEFAULT CURRENT_TIMESTAMP.
_CREATION_DEFAULT = re.compile(r"CURRENT_TIMESTAMP|\bnow\(\)", re.IGNORECASE)


class DataProfile:
    """The result of profiling one database at one point in data time."""

    def __init__(self) -> None:
        self.tables: list[TableProfile] = []
        self.columns: list[ColumnProfile] = []
        self.categories: list[CategoryFrequency] = []
        self.time_columns: dict[str, str] = {}
        self.skipped_tables: dict[str, str] = {}


def detect_time_column(table: ActualTable) -> str | None:
    """The creation-time column: the first timestamp column that defaults to the current time."""
    for column in sorted(table.columns, key=lambda c: c.position):
        if column.data_type.startswith("timestamp") and column.default:
            if _CREATION_DEFAULT.search(column.default):
                return column.name
    return None


def _bound(value: datetime, data_type: str) -> datetime:
    """Window bounds in UTC, naive for `timestamp without time zone` columns."""
    utc = value.astimezone(UTC)
    return utc.replace(tzinfo=None) if "without time zone" in data_type else utc


def _where(
    time_column: ActualColumn | None,
    window: Window | None,
    extra: list[sql.Composable],
) -> tuple[sql.Composable, list[Any]]:
    conditions: list[sql.Composable] = list(extra)
    params: list[Any] = []
    if window is not None and time_column is not None:
        ident = sql.Identifier(time_column.name)
        conditions += [sql.SQL("{} >= %s").format(ident), sql.SQL("{} < %s").format(ident)]
        params += [
            _bound(window.start, time_column.data_type),
            _bound(window.end, time_column.data_type),
        ]
    if not conditions:
        return sql.SQL(""), params
    return sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions), params


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def profile_table(
    conn: psycopg.Connection[Any],
    schema: str,
    table: ActualTable,
    *,
    time_column: ActualColumn | None,
    window: Window | None,
    max_categories: int,
) -> tuple[TableProfile, list[ColumnProfile], list[CategoryFrequency]]:
    relation = sql.Identifier(schema, table.name)
    where, params = _where(time_column, window, [])

    # One scan: row count plus, per column, non-null and distinct counts. Values are
    # compared as text so every column type (uuid, enum, array, json...) is handled alike.
    select = [sql.SQL("count(*)")]
    for column in table.columns:
        ident = sql.Identifier(column.name)
        select += [
            sql.SQL("count({})").format(ident),
            sql.SQL("count(DISTINCT {}::text)").format(ident),
        ]
    query = sql.SQL("SELECT {} FROM {}{}").format(sql.SQL(", ").join(select), relation, where)
    row = conn.execute(query, params).fetchone()
    assert row is not None
    row_count = int(row[0])

    columns: list[ColumnProfile] = []
    categories: list[CategoryFrequency] = []
    for index, column in enumerate(table.columns):
        non_null, distinct = int(row[1 + 2 * index]), int(row[2 + 2 * index])
        null_count = row_count - non_null
        columns.append(
            ColumnProfile(
                table=table.name,
                column=column.name,
                data_type=column.data_type,
                row_count=row_count,
                null_count=null_count,
                null_rate=_ratio(null_count, row_count),
                distinct_count=distinct,
                duplicate_rate=_ratio(non_null - distinct, non_null),
            )
        )
        if non_null > 0 and distinct <= max_categories and distinct < non_null:
            categories += _category_frequencies(conn, relation, table, column, time_column, window)

    profile = TableProfile(
        table=table.name,
        row_count=row_count,
        time_column=time_column.name if window and time_column else None,
    )
    return profile, columns, categories


def _category_frequencies(
    conn: psycopg.Connection[Any],
    relation: sql.Composable,
    table: ActualTable,
    column: ActualColumn,
    time_column: ActualColumn | None,
    window: Window | None,
) -> list[CategoryFrequency]:
    ident = sql.Identifier(column.name)
    where, params = _where(time_column, window, [sql.SQL("{} IS NOT NULL").format(ident)])
    query = sql.SQL(
        "SELECT {}::text AS value, count(*) AS n FROM {}{} GROUP BY 1 ORDER BY n DESC, value"
    ).format(ident, relation, where)
    return [
        CategoryFrequency(table=table.name, column=column.name, value=value, count=int(count))
        for value, count in conn.execute(query, params).fetchall()
    ]


def profile_database(
    conn: psycopg.Connection[Any],
    actual: ActualSchema,
    *,
    window: Window | None = None,
    time_columns: dict[str, str] | None = None,
    max_categories: int = DEFAULT_MAX_CATEGORIES,
) -> DataProfile:
    """Profiles every table of `actual`. With a window, tables lacking a creation-time
    column are skipped: their rows cannot be attributed to a window."""
    if max_categories < 1:
        raise ValueError("max_categories must be at least 1")
    overrides = time_columns or {}
    result = DataProfile()

    for table in actual.tables:
        if table.name == PRISMA_MIGRATIONS_TABLE:
            continue
        name = overrides.get(table.name) or detect_time_column(table)
        time_column = table.column(name) if name else None
        if name and time_column is None:
            raise ValueError(f"table {table.name!r} has no column {name!r} to window on")

        if window is not None and time_column is None:
            result.skipped_tables[table.name] = "no creation-time column to window on"
            continue
        if window is not None and time_column is not None:
            result.time_columns[table.name] = time_column.name

        profile, columns, categories = profile_table(
            conn,
            actual.schema_name,
            table,
            time_column=time_column,
            window=window,
            max_categories=max_categories,
        )
        result.tables.append(profile)
        result.columns += columns
        result.categories += categories
    return result
