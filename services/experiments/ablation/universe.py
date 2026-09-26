"""The benchmark's negative population, per problem type, for the false-positive rate.

Counted once per app from the benchmark itself and independent of any configuration, so that
every configuration's FPR is measured against the same denominator.
"""

import os
from pathlib import Path

from analyzers.anomaly.series import (
    DISTRIBUTION_SHIFT,
    DUPLICATE_RATE,
    NULL_RATE,
    ColumnSeries,
    metrics_for,
)
from analyzers.correlate.facts import route_for_file
from analyzers.schema.actual import PRISMA_MIGRATIONS_TABLE, ActualSchema
from analyzers.schema.declared import DeclaredSchema

PERFORMANCE_TYPES = (
    "n_plus_one",
    "missing_index",
    "excessive_relation_loading",
    "repeated_identical_query",
    "unpaginated_find_many",
)


def count_routes(app_dir: Path) -> int:
    """Route handlers under the app directory (Next.js App Router files)."""
    total = 0
    for root, dirs, files in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d not in {"node_modules", ".next", "generated", ".git"}]
        for name in files:
            relative = (Path(root) / name).relative_to(app_dir).as_posix()
            total += route_for_file(relative) is not None
    return total


def build_universe(
    app_dir: Path,
    declared: DeclaredSchema,
    actual: ActualSchema,
    baseline: dict[tuple[str, str], ColumnSeries],
) -> dict[str, int]:
    routes = count_routes(app_dir)
    metric_units = {NULL_RATE: 0, DUPLICATE_RATE: 0, DISTRIBUTION_SHIFT: 0}
    for series in baseline.values():
        for metric in metrics_for(series):
            metric_units[metric] += 1
    universe = {name: routes for name in PERFORMANCE_TYPES}
    universe |= {
        "null_spike": metric_units[NULL_RATE],
        "duplicate_spike": metric_units[DUPLICATE_RATE],
        "distribution_shift": metric_units[DISTRIBUTION_SHIFT],
        "orphaned_foreign_key": sum(
            relation.foreign_key_on == "self"
            for model in declared.models
            if model.block_type == "model"
            for relation in model.relations
        ),
        "index_not_declared": sum(
            len(table.indexes) for table in actual.tables if table.name != PRISMA_MIGRATIONS_TABLE
        ),
        "declared_index_not_applied": sum(
            len(model.indexes) for model in declared.models if model.block_type == "model"
        ),
    }
    return universe
