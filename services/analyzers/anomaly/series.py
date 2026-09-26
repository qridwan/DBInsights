"""Metric series built from stored data-quality profiles.

A `ColumnSeries` is one column's history: one entry per profile window, oldest first.
From it three metrics are derived, all rates or distances that do not depend on how
many rows a window happens to hold:

- `null_rate`: share of rows that are NULL. Every column.
- `duplicate_rate`: share of non-null values repeating another. Only columns whose values
  are meant to be (near-)unique: those that never carry a category distribution. In a
  column with few distinct values, repeats are the norm and the rate merely tracks the
  window's row count.
- `distribution_shift`: total-variation distance between a window's category shares and
  the mean shares of the other windows. Only columns that carry a distribution. What
  counts as a normal distance is learned from the history itself: each historical window is
  compared with the mean of the others (leave-one-out), so the distances are
  measured exactly the way the current window will be.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from typing import Any

from ..dataquality.models import Window
from ..dataquality.profile import DataProfile
from ..dataquality.store import ProfileStore

NULL_RATE = "null_rate"
DUPLICATE_RATE = "duplicate_rate"
DISTRIBUTION_SHIFT = "distribution_shift"


@dataclass(frozen=True)
class ColumnSeries:
    table: str
    column: str
    #: Profile windows, oldest first; every other tuple is aligned with this one.
    windows: tuple[Window, ...]
    row_counts: tuple[int, ...]
    #: None where the window had no rows (or no non-null values, for duplicate_rate).
    null_rates: tuple[float | None, ...]
    duplicate_rates: tuple[float | None, ...]
    #: value -> count per window; None where the profiler stored no distribution.
    distributions: tuple[Mapping[str, int] | None, ...]

    @property
    def key(self) -> tuple[str, str]:
        return (self.table, self.column)

    @property
    def is_categorical(self) -> bool:
        """Whether the column ever carried a distribution, i.e. has few distinct values."""
        return any(d is not None for d in self.distributions)

    def index_of(self, window_start: datetime) -> int | None:
        return next((i for i, w in enumerate(self.windows) if w.start == window_start), None)

    def head(self, n: int) -> "ColumnSeries":
        return ColumnSeries(
            self.table,
            self.column,
            self.windows[:n],
            self.row_counts[:n],
            self.null_rates[:n],
            self.duplicate_rates[:n],
            self.distributions[:n],
        )


def metrics_for(series: ColumnSeries) -> list[str]:
    """Which metrics are meaningful for this column."""
    return [NULL_RATE, DISTRIBUTION_SHIFT if series.is_categorical else DUPLICATE_RATE]


def load_series(store: ProfileStore, app: str, label: str) -> dict[tuple[str, str], ColumnSeries]:
    columns: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in store.windowed_columns(app, label):
        columns[(row["table_name"], row["column_name"])].append(row)

    categories: dict[tuple[str, str, datetime], dict[str, int]] = defaultdict(dict)
    for row in store.windowed_categories(app, label):
        categories[(row["table_name"], row["column_name"], row["window_start"])][row["value"]] = (
            row["count"]
        )

    series: dict[tuple[str, str], ColumnSeries] = {}
    for (table, column), rows in columns.items():
        rows.sort(key=lambda r: r["window_start"])
        series[(table, column)] = ColumnSeries(
            table=table,
            column=column,
            windows=tuple(Window(start=r["window_start"], end=r["window_end"]) for r in rows),
            row_counts=tuple(int(r["row_count"]) for r in rows),
            null_rates=tuple(r["null_rate"] for r in rows),
            duplicate_rates=tuple(r["duplicate_rate"] for r in rows),
            distributions=tuple(categories.get((table, column, r["window_start"])) for r in rows),
        )
    return series


def series_from_profile(
    profile: "DataProfile", window: Window
) -> dict[tuple[str, str], ColumnSeries]:
    """One-window series from an in-memory profile, keyed like `load_series`; no store."""
    distributions: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for category in profile.categories:
        distributions[(category.table, category.column)][category.value] = category.count
    return {
        (c.table, c.column): ColumnSeries(
            table=c.table,
            column=c.column,
            windows=(window,),
            row_counts=(c.row_count,),
            null_rates=(c.null_rate,),
            duplicate_rates=(c.duplicate_rate,),
            distributions=(distributions.get((c.table, c.column)),),
        )
        for c in profile.columns
    }


# ---- distribution distance ------------------------------------------------------------------
#
# Shares are exact rationals. With floats, windows holding the very same distribution come out
# a rounding error apart (1/10 summed ten times is not 1), and a learned range that has
# collapsed to zero width then flags the noise. Exact arithmetic keeps "identical" at exactly 0.

Share = Fraction | float


def shares(counts: Mapping[str, int]) -> dict[str, Fraction]:
    total = sum(counts.values())
    return {value: Fraction(n, total) for value, n in counts.items()} if total else {}


def mean_shares(distributions: Sequence[Mapping[str, int]]) -> dict[str, Fraction]:
    """Each window weighs the same, whatever its row count."""
    accumulated: dict[str, Fraction] = defaultdict(Fraction)
    for counts in distributions:
        for value, share in shares(counts).items():
            accumulated[value] += share / len(distributions)
    return dict(accumulated)


def total_variation(p: Mapping[str, Share], q: Mapping[str, Share]) -> float:
    """Half the L1 distance: the share that has moved (0 = same, 1 = disjoint)."""
    return float(Fraction(1, 2) * sum(abs(p.get(v, 0) - q.get(v, 0)) for v in p.keys() | q.keys()))


def leave_one_out_distances(distributions: Sequence[Mapping[str, int]]) -> list[float]:
    """Distance of each window from the mean of all the others."""
    if len(distributions) < 2:
        return []
    return [
        total_variation(shares(d), mean_shares([o for j, o in enumerate(distributions) if j != i]))
        for i, d in enumerate(distributions)
    ]


def values_of(series: ColumnSeries, metric: str) -> list[float | None]:
    """Per-window values of a scalar metric (not for distribution_shift)."""
    if metric == NULL_RATE:
        return list(series.null_rates)
    if metric == DUPLICATE_RATE:
        return list(series.duplicate_rates)
    raise ValueError(f"{metric} is not a scalar metric")
