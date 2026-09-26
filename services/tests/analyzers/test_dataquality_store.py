import uuid
from datetime import UTC, datetime, timedelta

import pytest

from analyzers.dataquality import (
    CategoryFrequency,
    ColumnProfile,
    IntegrityCheck,
    ProfileRun,
    ProfileStore,
    TableProfile,
    Window,
)
from analyzers.dataquality.__main__ import _windows
from analyzers.dataquality.store import parse_time

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def make_run(*, window, null_rate, label="series", app="shop", distribution=None, integrity=()):
    run_id = str(uuid.uuid4())
    return ProfileRun(
        run_id=run_id,
        app=app,
        label=label,
        profiled_at=utc(2026, 9, 26),
        window=window,
        max_categories=50,
        time_columns={"Customer": "createdAt"} if window else {},
        skipped_tables={},
        tables=[
            TableProfile(
                table="Customer", row_count=100, time_column="createdAt" if window else None
            )
        ],
        columns=[
            ColumnProfile(
                table="Customer",
                column="phone",
                data_type="text",
                row_count=100,
                null_count=int(null_rate * 100),
                null_rate=null_rate,
                distinct_count=90,
                duplicate_rate=0.05,
            )
        ],
        categories=[
            CategoryFrequency(table="Customer", column="tier", value=v, count=n)
            for v, n in (distribution or {"gold": 60, "silver": 40}).items()
        ],
        integrity=list(integrity),
    )


@pytest.fixture
def store(temp_schema):
    profile_store = ProfileStore(temp_schema.url, schema=f"{temp_schema.name}_store")
    try:
        yield profile_store
    finally:
        profile_store.conn.execute(f'DROP SCHEMA "{profile_store.schema}" CASCADE')
        profile_store.close()


def month(n):
    return Window(start=utc(2026, n, 1), end=utc(2026, n + 1, 1))


def test_history_is_returned_in_data_time_order_whatever_the_insert_order(store):
    for m, rate in ((3, 0.60), (1, 0.04), (2, 0.05)):
        store.save(make_run(window=month(m), null_rate=rate))
    history = store.column_history("shop", "Customer", "phone")
    assert [(h["window_start"].month, h["null_rate"]) for h in history] == [
        (1, 0.04),
        (2, 0.05),
        (3, 0.60),
    ]
    assert history[0]["row_count"] == 100 and history[0]["duplicate_rate"] == 0.05


def test_profiles_accumulate_and_are_never_overwritten(store):
    store.save(make_run(window=month(1), null_rate=0.04))
    store.save(make_run(window=month(1), null_rate=0.05))  # same window observed again
    history = store.column_history("shop", "Customer", "phone")
    assert [h["null_rate"] for h in history] == [0.04, 0.05]
    assert len({h["run_id"] for h in history}) == 2


def test_history_is_scoped_by_app_and_label(store):
    store.save(make_run(window=month(1), null_rate=0.1, label="clean"))
    store.save(make_run(window=month(1), null_rate=0.9, label="injected"))
    store.save(make_run(window=month(1), null_rate=0.5, app="other"))
    assert [
        h["null_rate"] for h in store.column_history("shop", "Customer", "phone", label="clean")
    ] == [0.1]
    assert len(store.column_history("shop", "Customer", "phone")) == 2
    assert len(store.column_history("other", "Customer", "phone")) == 1


def test_snapshots_are_kept_but_are_not_part_of_windowed_history(store):
    store.save(make_run(window=None, null_rate=0.3))
    assert store.column_history("shop", "Customer", "phone") == []
    assert len(store.runs("shop")) == 1


def test_category_history_groups_distributions_per_window(store):
    store.save(make_run(window=month(2), null_rate=0, distribution={"gold": 10, "silver": 90}))
    store.save(make_run(window=month(1), null_rate=0, distribution={"gold": 60, "silver": 40}))
    history = store.category_history("shop", "Customer", "tier")
    assert [(h["window_start"].month, h["distribution"]) for h in history] == [
        (1, {"gold": 60, "silver": 40}),
        (2, {"silver": 90, "gold": 10}),
    ]


def test_nulls_round_trip_as_null(store):
    store.save(
        make_run(window=month(1), null_rate=0.0).model_copy(
            update={
                "columns": [
                    ColumnProfile(
                        table="Customer",
                        column="phone",
                        data_type="text",
                        row_count=0,
                        null_count=0,
                        null_rate=None,
                        distinct_count=0,
                        duplicate_rate=None,
                    )
                ]
            }
        )
    )
    [row] = store.column_history("shop", "Customer", "phone")
    assert (row["null_rate"], row["duplicate_rate"]) == (None, None)


def test_integrity_results_are_stored_with_their_run(store):
    run = make_run(
        window=None,
        null_rate=0.0,
        integrity=[
            IntegrityCheck(
                model="User",
                relation="team",
                table="User",
                columns=["teamId"],
                referenced_table="Team",
                referenced_columns=["id"],
                checked_rows=10,
                orphan_rows=2,
                orphan_rate=0.2,
                line=21,
            )
        ],
    )
    store.save(run)
    [row] = store.integrity(run.run_id)
    assert (row["table_name"], row["column_names"], row["orphan_rows"], row["orphan_rate"]) == (
        "User",
        ["teamId"],
        2,
        0.2,
    )


def test_an_invalid_schema_name_is_rejected(temp_schema):
    with pytest.raises(ValueError):
        ProfileStore(temp_schema.url, schema='x"; DROP SCHEMA public; --')


# ---- window options (no database) ---------------------------------------------------------


class Args:
    def __init__(self, **kw):
        self.windows = self.end = self.window_start = self.window_end = None
        self.window_days = 30
        self.__dict__.update(kw)


def test_consecutive_windows_end_at_the_given_date_oldest_first():
    windows = _windows(Args(windows=3, window_days=30, end="2026-09-01"))
    assert [(w.start.date().isoformat(), w.end.date().isoformat()) for w in windows] == [
        ("2026-06-03", "2026-07-03"),
        ("2026-07-03", "2026-08-02"),
        ("2026-08-02", "2026-09-01"),
    ]
    assert all(a.end == b.start for a, b in zip(windows, windows[1:], strict=False))


def test_no_window_options_means_a_snapshot():
    assert _windows(Args()) == [None]


def test_explicit_window_needs_both_bounds():
    with pytest.raises(SystemExit):
        _windows(Args(window_start="2026-01-01"))
    [window] = _windows(Args(window_start="2026-01-01", window_end="2026-02-01"))
    assert window.end - window.start == timedelta(days=31)


def test_dates_are_midnight_utc_and_zulu_suffix_is_accepted():
    assert parse_time("2026-09-01") == utc(2026, 9, 1)
    assert parse_time("2026-09-01T12:30:00Z") == utc(2026, 9, 1, 12, 30)
