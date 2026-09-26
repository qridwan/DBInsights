"""Per-configuration summaries and the named hypothesis comparisons. See `stats` for why each
test was chosen; this module only applies them to the data."""

import math
import random
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from .data import Dataset
from .stats import (
    bootstrap_ci,
    holm,
    mcnemar_exact,
    mean_ci,
    wilcoxon_paired,
)

SEED = 20260930


@dataclass(frozen=True)
class Comparison:
    id: str
    hypothesis: str
    question: str
    first: str
    second: str
    #: Tested in the Holm-corrected family; sensitivity comparisons are reported separately.
    primary: bool = True


COMPARISONS = (
    Comparison(
        "H5_B1_vs_B2", "H5, RQ6", "Does the declared schema improve on source alone?", "B1", "B2"
    ),
    Comparison(
        "RQ6_B2_vs_C1",
        "RQ6 (core)",
        "Does the live database's schema add to the declared one?",
        "B2",
        "C1",
    ),
    Comparison("H3_C1_vs_C2", "H3, RQ3", "Does runtime evidence strengthen detection?", "C1", "C2"),
    Comparison("H1_A_vs_C3", "H1", "Does the full hybrid beat SQL analysis alone?", "A", "C3"),
    Comparison(
        "S_Alog_vs_C3",
        "sensitivity",
        "Does the hybrid still win against the SQL baseline given the application's captured SQL?",
        "A-log",
        "C3",
        primary=False,
    ),
)


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or precision + recall == 0:
        return None if precision is None or recall is None else 0.0
    return 2 * precision * recall / (precision + recall)


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


# ---- per-configuration summaries ----------------------------------------------------------------


def _run_metrics(
    dataset: Dataset, config: str, apps: list[str] | None = None
) -> dict[int, dict[str, float | None]]:
    """Accuracy, FPR, latency and overhead of each repetition, pooled over the given apps."""
    per_rep: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"tp": 0, "fp": 0, "fn": 0, "neg": 0, "wall": 0.0, "cpu": 0.0, "lat": []}
    )
    for run in dataset.runs:
        if run.config != config or (apps and run.app not in apps):
            continue
        rep = per_rep[run.repetition]
        rep["tp"] += run.tp
        rep["fp"] += run.fp
        rep["fn"] += run.fn
        rep["neg"] += run.negatives
        rep["wall"] += run.wall_s
        rep["cpu"] += run.cpu_s
    for outcome in dataset.outcomes:
        if (
            outcome.config == config
            and (not apps or outcome.app in apps)
            and outcome.latency_s is not None
        ):
            per_rep[outcome.repetition]["lat"].append(outcome.latency_s)

    metrics = {}
    for rep, v in sorted(per_rep.items()):
        precision = _ratio(v["tp"], v["tp"] + v["fp"])
        recall = _ratio(v["tp"], v["tp"] + v["fn"])
        metrics[rep] = {
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
            "false_positive_rate": _ratio(v["fp"], v["neg"]),
            "detection_latency_s": sum(v["lat"]) / len(v["lat"]) if v["lat"] else None,
            "wall_s": v["wall"],
            "cpu_s": v["cpu"],
            "tp": v["tp"],
            "fp": v["fp"],
            "fn": v["fn"],
        }
    return metrics


METRICS = (
    "precision",
    "recall",
    "f1",
    "false_positive_rate",
    "detection_latency_s",
    "wall_s",
    "cpu_s",
)


def _summarize(per_rep: dict[int, dict[str, float | None]]) -> dict[str, Any]:
    out = {}
    for metric in METRICS:
        values = [m[metric] for m in per_rep.values() if m[metric] is not None]
        out[metric] = asdict(mean_ci(values))
    return out


def per_problem_type(dataset: Dataset, config: str) -> dict[str, Any]:
    """Recall, precision and false-positive rate per problem type, mean and CI over repetitions."""
    rows = [r for r in dataset.result_rows if r["config"] == config]
    by_type: dict[str, dict[int, dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "entries": 0, "negatives": 0})
    )
    universe = dataset.provenance["universe"]
    for row in rows:
        cell = by_type[row["problem_type"]][row["repetition"]]
        cell["tp"] += row["tp"]
        cell["fp"] += row["fp"]
        cell["fn"] += row["fn"]
        cell["entries"] += row["entries"]
        cell["negatives"] += max(
            universe[row["app"]].get(row["problem_type"], 0) - row["entries"], 0
        )
    out = {}
    for name, reps in sorted(by_type.items()):
        precision, recall, fpr = [], [], []
        for cell in reps.values():
            if cell["tp"] + cell["fp"]:
                precision.append(cell["tp"] / (cell["tp"] + cell["fp"]))
            if cell["tp"] + cell["fn"]:
                recall.append(cell["tp"] / (cell["tp"] + cell["fn"]))
            if cell["negatives"]:
                fpr.append(cell["fp"] / cell["negatives"])
        any_rep = next(iter(reps.values()))
        out[name] = {
            "entries": any_rep["entries"],
            "recall": asdict(mean_ci(recall)),
            "precision": asdict(mean_ci(precision)),
            "false_positive_rate": asdict(mean_ci(fpr)),
            "tp": asdict(mean_ci([c["tp"] for c in reps.values()])),
            "fp": asdict(mean_ci([c["fp"] for c in reps.values()])),
            "fn": asdict(mean_ci([c["fn"] for c in reps.values()])),
        }
    return out


def _stability(dataset: Dataset, config: str) -> dict[str, Any]:
    """Whether every repetition detected exactly the same problems (deterministic accuracy)."""
    sets: dict[tuple[str, int], set[str]] = defaultdict(set)
    fps: dict[tuple[str, int], int] = defaultdict(int)
    for o in dataset.outcomes:
        if o.config == config and o.detected:
            sets[(o.app, o.repetition)].add(o.entry_id)
    for r in dataset.runs:
        if r.config == config:
            sets.setdefault((r.app, r.repetition), set())
            fps[(r.app, r.repetition)] = r.fp
    per_app: dict[str, list[frozenset[str]]] = defaultdict(list)
    for (app, _rep), found in sets.items():
        per_app[app].append(frozenset(found))
    identical = all(len(set(v)) == 1 for v in per_app.values())
    return {
        "identical_detections_across_repetitions": identical,
        "identical_false_positive_counts_across_repetitions": all(
            len({fps[(a, r)] for r in dataset.repetitions(config)}) == 1 for a in dataset.apps()
        ),
    }


def summarize(dataset: Dataset) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for config in dataset.configs():
        overall = _run_metrics(dataset, config)
        out[config] = {
            "repetitions": len(overall),
            "pooled_over_apps": _summarize(overall),
            "per_app": {a: _summarize(_run_metrics(dataset, config, [a])) for a in dataset.apps()},
            "per_problem_type": per_problem_type(dataset, config),
            "stability": _stability(dataset, config),
            "problem_bootstrap": _problem_bootstrap(dataset, config),
        }
    return out


# ---- canonical outcomes (what a configuration detects, and how) ---------------------------


def canonical_detection(dataset: Dataset, config: str) -> dict[tuple[str, str], bool]:
    """Per problem: detected in more than half of the repetitions. With deterministic accuracy this
    is just what every repetition found; it keeps the paired tests one row per problem."""
    seen: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for o in dataset.outcomes:
        if o.config == config:
            seen[(o.app, o.entry_id)].append(o.detected)
    return {key: sum(v) * 2 > len(v) for key, v in seen.items()}


def _mean_confidence(dataset: Dataset, config: str) -> dict[tuple[str, str], float]:
    seen: dict[tuple[str, str], list[int]] = defaultdict(list)
    for o in dataset.outcomes:
        if o.config == config and o.confidence is not None:
            seen[(o.app, o.entry_id)].append(o.confidence)
    return {key: sum(v) / len(v) for key, v in seen.items()}


def _typical_labels(dataset: Dataset, config: str) -> list[bool]:
    """The false/true positives of a typical run of this configuration, both apps together."""
    tp, fp, reps = 0, 0, 0
    per_app: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for r in dataset.runs:
        if r.config == config:
            per_app[r.app].append((r.tp, r.fp))
    for runs in per_app.values():
        reps = len(runs)
        tp += round(sum(t for t, _ in runs) / reps)
        fp += round(sum(f for _, f in runs) / reps)
    return [True] * tp + [False] * fp


def _draw_f1(
    recall_units: list[float], labels: list[bool], rng: random.Random, indices: list[int]
) -> tuple[float | None, float | None, float | None]:
    recall = sum(recall_units[i] for i in indices) / len(indices)
    if not labels:
        return None, recall, None
    sample = [labels[rng.randrange(len(labels))] for _ in labels]
    precision = sum(sample) / len(sample)
    return precision, recall, _f1(precision, recall)


def _problem_bootstrap(dataset: Dataset, config: str) -> dict[str, Any]:
    """Interval for recall, precision and F1 over the benchmark's own problems and findings."""
    detected = canonical_detection(dataset, config)
    keys = sorted(detected)
    units = [1.0 if detected[k] else 0.0 for k in keys]
    labels = _typical_labels(dataset, config)

    def statistic(which: int):
        def draw(rng: random.Random) -> float | None:
            indices = [rng.randrange(len(units)) for _ in units]
            return _draw_f1(units, labels, rng, indices)[which]

        return draw

    result = {}
    for name, which in (("precision", 0), ("recall", 1), ("f1", 2)):
        low, high = bootstrap_ci(statistic(which), seed=SEED + which)
        result[name] = {"low": low, "high": high}
    result["problems"] = len(units)
    result["scored_findings"] = len(labels)
    return result


# ---- the named comparisons ---------------------------------------------------------------


def _paired_timing(dataset: Dataset, first: str, second: str) -> dict[str, Any]:
    """Wilcoxon signed-rank on per-(app, repetition) wall time, CPU time and latency."""
    runs = {(r.config, r.app, r.repetition): r for r in dataset.runs}
    pairs = sorted((a, rep) for (c, a, rep) in runs if c == first and (second, a, rep) in runs)
    wall = (
        [runs[(first, a, r)].wall_s for a, r in pairs],
        [runs[(second, a, r)].wall_s for a, r in pairs],
    )
    cpu = (
        [runs[(first, a, r)].cpu_s for a, r in pairs],
        [runs[(second, a, r)].cpu_s for a, r in pairs],
    )

    shared = {
        k
        for k, v in canonical_detection(dataset, first).items()
        if v and canonical_detection(dataset, second).get(k)
    }
    latency: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    for o in dataset.outcomes:
        if (
            o.config in (first, second)
            and (o.app, o.entry_id) in shared
            and o.latency_s is not None
        ):
            latency[(o.config, o.app, o.repetition)].append(o.latency_s)
    lat_pairs = [
        (a, r) for a, r in pairs if latency.get((first, a, r)) and latency.get((second, a, r))
    ]
    lat = (
        [sum(latency[(first, a, r)]) / len(latency[(first, a, r)]) for a, r in lat_pairs],
        [sum(latency[(second, a, r)]) / len(latency[(second, a, r)]) for a, r in lat_pairs],
    )
    return {
        "wall_s": {
            **asdict(wilcoxon_paired(*wall)),
            "first_mean": _mean(wall[0]),
            "second_mean": _mean(wall[1]),
        },
        "cpu_s": {
            **asdict(wilcoxon_paired(*cpu)),
            "first_mean": _mean(cpu[0]),
            "second_mean": _mean(cpu[1]),
        },
        "detection_latency_s": {
            **asdict(wilcoxon_paired(*lat)),
            "first_mean": _mean(lat[0]),
            "second_mean": _mean(lat[1]),
            "restricted_to": f"{len(shared)} problems detected by both configurations",
        },
    }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _delta_bootstrap(dataset: Dataset, first: str, second: str) -> dict[str, Any]:
    """Interval for second - first in precision, recall and F1, resampling the same problems for
    both configurations (they are paired) and each configuration's findings independently."""
    d1, d2 = canonical_detection(dataset, first), canonical_detection(dataset, second)
    keys = sorted(d1.keys() & d2.keys())
    u1 = [1.0 if d1[k] else 0.0 for k in keys]
    u2 = [1.0 if d2[k] else 0.0 for k in keys]
    l1, l2 = _typical_labels(dataset, first), _typical_labels(dataset, second)

    def delta(which: int):
        def draw(rng: random.Random) -> float | None:
            indices = [rng.randrange(len(keys)) for _ in keys]
            a = _draw_f1(u1, l1, rng, indices)[which]
            b = _draw_f1(u2, l2, rng, indices)[which]
            return None if a is None or b is None else b - a

        return draw

    def point(units: list[float], labels: list[bool]) -> dict[str, float | None]:
        precision = sum(labels) / len(labels) if labels else None
        recall = sum(units) / len(units) if units else None
        return {"precision": precision, "recall": recall, "f1": _f1(precision, recall)}

    p1, p2 = point(u1, l1), point(u2, l2)
    out: dict[str, Any] = {}
    for name, which in (("precision", 0), ("recall", 1), ("f1", 2)):
        low, high = bootstrap_ci(delta(which), seed=SEED + 10 + which)
        a, b = p1[name], p2[name]
        out[name] = {
            "first": a,
            "second": b,
            "difference": None if a is None or b is None else b - a,
            "ci_low": low,
            "ci_high": high,
            "excludes_zero": low is not None and high is not None and (low > 0 or high < 0),
        }
    return out


def _confidence_test(dataset: Dataset, first: str, second: str) -> dict[str, Any]:
    c1, c2 = _mean_confidence(dataset, first), _mean_confidence(dataset, second)
    shared = sorted(c1.keys() & c2.keys())
    result = wilcoxon_paired([c1[k] for k in shared], [c2[k] for k in shared])
    return {
        **asdict(result),
        "first_mean": _mean([c1[k] for k in shared]),
        "second_mean": _mean([c2[k] for k in shared]),
        "scale": "confidence rank of the matching finding: 1 LOW, 2 MEDIUM, 3 HIGH",
        "restricted_to": f"{len(shared)} problems detected by both configurations",
    }


def _verdict(p_adjusted: float, risk_difference: float, primary: bool) -> str:
    if not primary:
        return "not part of the corrected family"
    if p_adjusted < 0.05:
        return (
            "supported: significantly more problems detected"
            if risk_difference > 0
            else ("CONTRADICTED: significantly fewer problems detected")
        )
    return "not supported: no significant difference in detection"


def compare(dataset: Dataset) -> list[dict[str, Any]]:
    available = set(dataset.configs())
    chosen = [c for c in COMPARISONS if c.first in available and c.second in available]
    results = []
    for comparison in chosen:
        first, second = comparison.first, comparison.second
        d1, d2 = canonical_detection(dataset, first), canonical_detection(dataset, second)
        keys = sorted(d1.keys() & d2.keys())

        def paired(subset, d1=d1, d2=d2):
            return mcnemar_exact([d1[k] for k in subset], [d2[k] for k in subset])

        detection = paired(keys)
        per_app = {a: asdict(paired([k for k in keys if k[0] == a])) for a in dataset.apps()}
        types = sorted({dataset.problem_types[e] for _, e in keys})
        per_type = {
            t: asdict(paired([k for k in keys if dataset.problem_types[k[1]] == t])) for t in types
        }
        results.append(
            {
                "id": comparison.id,
                "hypothesis": comparison.hypothesis,
                "question": comparison.question,
                "first": first,
                "second": second,
                "primary": comparison.primary,
                "problems": len(keys),
                "detection_mcnemar_exact": asdict(detection),
                "detection_per_app": per_app,
                "detection_per_problem_type": per_type,
                "accuracy_difference_bootstrap": _delta_bootstrap(dataset, first, second),
                "timing_wilcoxon": _paired_timing(dataset, first, second),
                "confidence_wilcoxon": _confidence_test(dataset, first, second),
            }
        )
    primary = [r for r in results if r["primary"]]
    adjusted = holm([r["detection_mcnemar_exact"]["p_value"] for r in primary])
    for result, p in zip(primary, adjusted, strict=True):
        result["detection_p_holm"] = p
    for result in results:
        result.setdefault("detection_p_holm", None)
        result["verdict"] = _verdict(
            result["detection_p_holm"] if result["detection_p_holm"] is not None else math.nan,
            result["detection_mcnemar_exact"]["risk_difference"],
            result["primary"],
        )
    return results
