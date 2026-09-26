from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from analyzers.dataquality import Window, detect_time_column, profile_database
from analyzers.schema.actual import connect, read_actual_schema
from tests.analyzers.conftest import column, table

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


# ---- pure ---------------------------------------------------------------------------------


def col(name, data_type="text", default=None, position=1):
    return column(name, data_type, position=position).model_copy(update={"default": default})


def test_creation_time_column_is_the_timestamp_defaulting_to_now():
    columns = [
        col("id", "integer", position=1),
        col("updatedAt", "timestamp(3) without time zone", position=2),
        col("createdAt", "timestamp(3) without time zone", "CURRENT_TIMESTAMP", position=3),
        col("seenAt", "timestamp with time zone", "now()", position=4),
    ]
    assert detect_time_column(table("T", columns, [])) == "createdAt"


@pytest.mark.parametrize(
    "columns",
    [
        [col("id", "integer")],
        [col("at", "timestamp(3) without time zone")],  # no default
        [col("at", "text", "CURRENT_TIMESTAMP")],  # not a timestamp
        [
            col("at", "timestamp(3) without time zone", "'2000-01-01'::timestamp")
        ],  # constant default
    ],
)
def test_no_creation_time_column_when_nothing_qualifies(columns):
    assert detect_time_column(table("T", columns, [])) is None


def test_window_must_be_ordered_and_timezone_aware():
    with pytest.raises(ValidationError):
        Window(start=utc(2026, 2, 1), end=utc(2026, 1, 1))
    with pytest.raises(ValidationError):
        Window(start=datetime(2026, 1, 1), end=datetime(2026, 2, 1))


# ---- against PostgreSQL --------------------------------------------------------------------

JAN = Window(start=utc(2026, 1, 1), end=utc(2026, 2, 1))
FEB = Window(start=utc(2026, 2, 1), end=utc(2026, 3, 1))
DEC = Window(start=utc(2025, 12, 1), end=utc(2026, 1, 1))


@pytest.fixture
def db(temp_schema):
    c = temp_schema.conn
    c.execute(
        'CREATE TABLE "Customer" ("id" integer PRIMARY KEY, "phone" text, "tier" text NOT NULL, '
        '"email" text NOT NULL, "createdAt" timestamp(3) NOT NULL DEFAULT CURRENT_TIMESTAMP, '
        "\"updatedAt\" timestamp(3) NOT NULL DEFAULT '2000-01-01')"
    )
    c.execute(
        """INSERT INTO "Customer" ("id", "phone", "tier", "email", "createdAt") VALUES
           (1, '111', 'gold',   'a@x', '2026-01-05'),
           (2, NULL,  'gold',   'b@x', '2026-01-10'),
           (3, '333', 'silver', 'c@x', '2026-01-15'),
           (4, '333', 'silver', 'd@x', '2026-01-20'),
           (5, NULL,  'gold',   'e@x', '2026-01-31 23:59:59'),
           (6, '666', 'gold',   'f@x', '2026-02-01'),
           (7, '777', 'silver', 'g@x', '2026-02-10'),
           (8, '888', 'bronze', 'h@x', '2026-02-15'),
           (9, '999', 'bronze', 'i@x', '2026-02-28')"""
    )
    # No creation-time column, and Prisma's bookkeeping table.
    c.execute('CREATE TABLE "Note" ("id" integer PRIMARY KEY, "body" text)')
    c.execute("INSERT INTO \"Note\" VALUES (1, 'x'), (2, 'x')")
    c.execute('CREATE TABLE "_prisma_migrations" ("id" text PRIMARY KEY)')
    # timestamptz creation column, and an undefaulted timestamp needing an override.
    c.execute(
        'CREATE TABLE "Log" ("id" integer PRIMARY KEY, "at" timestamptz NOT NULL DEFAULT now())'
    )
    c.execute(
        "INSERT INTO \"Log\" VALUES (1, '2026-01-10 12:00:00+00'), (2, '2026-02-10 12:00:00+00')"
    )
    c.execute('CREATE TABLE "Event" ("id" integer PRIMARY KEY, "happenedAt" timestamp NOT NULL)')
    c.execute(
        "INSERT INTO \"Event\" VALUES (1, '2026-01-02'), (2, '2026-01-03'), (3, '2026-02-02')"
    )
    with connect(temp_schema.url) as conn:
        yield conn, read_actual_schema(conn, temp_schema.name)


def columns_of(profile, table_name):
    return {c.column: c for c in profile.columns if c.table == table_name}


def categories_of(profile, table_name, column_name):
    return {
        c.value: c.count
        for c in profile.categories
        if (c.table, c.column) == (table_name, column_name)
    }


def test_snapshot_statistics_are_exact(db):
    conn, actual = db
    profile = profile_database(conn, actual)
    customer = columns_of(profile, "Customer")

    assert {t.table: t.row_count for t in profile.tables}["Customer"] == 9
    phone = customer["phone"]
    assert (phone.null_count, phone.distinct_count) == (2, 6)
    assert phone.null_rate == pytest.approx(2 / 9)
    assert phone.duplicate_rate == pytest.approx(1 / 7), "(non-null 7 - distinct 6) / 7"
    assert customer["id"].duplicate_rate == 0
    assert customer["email"].null_rate == 0
    assert all(t.time_column is None for t in profile.tables), "snapshot runs are not windowed"


def test_prisma_bookkeeping_table_is_never_profiled(db):
    conn, actual = db
    assert "_prisma_migrations" not in {t.table for t in profile_database(conn, actual).tables}


def test_category_frequencies_cover_low_cardinality_columns_only(db):
    conn, actual = db
    profile = profile_database(conn, actual)
    assert categories_of(profile, "Customer", "tier") == {"gold": 4, "silver": 3, "bronze": 2}
    # Every value unique: no distribution to store.
    assert categories_of(profile, "Customer", "id") == {}
    assert categories_of(profile, "Customer", "email") == {}


def test_max_categories_bounds_storage_not_the_statistics(db):
    conn, actual = db
    profile = profile_database(conn, actual, max_categories=2)
    assert categories_of(profile, "Customer", "tier") == {}
    assert columns_of(profile, "Customer")["tier"].distinct_count == 3


def test_max_categories_must_be_positive(db):
    conn, actual = db
    with pytest.raises(ValueError):
        profile_database(conn, actual, max_categories=0)


def test_windows_partition_the_rows_by_creation_time_half_open(db):
    conn, actual = db
    jan = profile_database(conn, actual, window=JAN)
    feb = profile_database(conn, actual, window=FEB)
    counts = lambda p: {t.table: t.row_count for t in p.tables}  # noqa: E731
    # 2026-02-01 00:00:00 belongs to February, 2026-01-31 23:59:59 to January.
    assert counts(jan)["Customer"] == 5
    assert counts(feb)["Customer"] == 4

    phone_jan, phone_feb = (
        columns_of(jan, "Customer")["phone"],
        columns_of(feb, "Customer")["phone"],
    )
    assert (phone_jan.null_count, phone_jan.distinct_count) == (2, 2)
    assert phone_jan.duplicate_rate == pytest.approx(1 / 3)
    assert (phone_feb.null_count, phone_feb.duplicate_rate) == (0, 0)
    assert categories_of(jan, "Customer", "tier") == {"gold": 3, "silver": 2}
    assert categories_of(feb, "Customer", "tier") == {"bronze": 2, "gold": 1, "silver": 1}


def test_empty_window_yields_rows_of_zero_with_undefined_rates(db):
    conn, actual = db
    empty = profile_database(conn, actual, window=DEC)
    assert {t.table: t.row_count for t in empty.tables}["Customer"] == 0
    phone = columns_of(empty, "Customer")["phone"]
    assert (phone.null_rate, phone.duplicate_rate, phone.distinct_count) == (None, None, 0)
    assert empty.categories == []


def test_windowed_runs_skip_tables_that_cannot_be_windowed(db):
    conn, actual = db
    windowed = profile_database(conn, actual, window=JAN)
    assert windowed.skipped_tables == {
        "Note": "no creation-time column to window on",
        "Event": "no creation-time column to window on",
    }
    assert "Note" not in {t.table for t in windowed.tables}
    assert windowed.time_columns["Customer"] == "createdAt"
    assert "Note" in {t.table for t in profile_database(conn, actual).tables}, "snapshot keeps it"


def test_timestamptz_creation_columns_are_windowed_too(db):
    conn, actual = db
    assert {t.table: t.row_count for t in profile_database(conn, actual, window=JAN).tables}[
        "Log"
    ] == 1
    assert {t.table: t.row_count for t in profile_database(conn, actual, window=FEB).tables}[
        "Log"
    ] == 1


def test_time_column_override_windows_a_table_with_no_default(db):
    conn, actual = db
    jan = profile_database(conn, actual, window=JAN, time_columns={"Event": "happenedAt"})
    assert {t.table: t.row_count for t in jan.tables}["Event"] == 2
    assert jan.time_columns["Event"] == "happenedAt"
    assert "Event" not in jan.skipped_tables


def test_override_naming_a_missing_column_fails_loudly(db):
    conn, actual = db
    with pytest.raises(ValueError, match="nope"):
        profile_database(conn, actual, window=JAN, time_columns={"Event": "nope"})


def test_profiling_never_modifies_the_database(db):
    conn, actual = db
    profile_database(conn, actual, window=JAN)
    assert (
        conn.execute(f'SELECT count(*) FROM "{actual.schema_name}"."Customer"').fetchone()[0] == 9
    )
