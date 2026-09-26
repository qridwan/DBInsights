"""What is recorded for one run, per problem type. Nothing here is aggregated across runs.

A row is the scorer's counts for one problem type plus four measurements the scorer does not make:

false-positive rate
    FP / (FP + TN), where the negatives are the benchmark's *units* of that problem type that
    carry no injected problem: route handlers for the five performance types, (column, metric)
    series for the data-quality types, declared relations for orphans, indexes for the two
    divergence types. TN is whatever is left after the false positives, so FPR = FP / negatives.
    The universe is a property of the benchmark, not of a configuration.
detection latency
    Seconds from the start of a run to the first layer whose findings matched the problem,
    averaged over the problems of that type that were detected. Layers run cheapest first, so this
    is what each layer's evidence costs to wait for. A problem found only after correlation is
    credited at the end of correlation.
mean TP confidence
    LOW=1, MEDIUM=2, HIGH=3, averaged over the true positives: how strongly the evidence is stated.
    Accuracy metrics cannot show a layer that makes existing findings more certain; this can.
unmapped
    A pseudo problem type collecting false positives from rules with no ground-truth type (they
    are false positives in the aggregate, but belong to no row of a problem type).
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from analyzers.finding import Finding
from experiments.groundtruth import Manifest, ScoreReport

CONFIDENCE_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
UNMAPPED = "unmapped"


@dataclass(frozen=True)
class ResultRow:
    problem_type: str
    #: Ground-truth entries of this type in the app.
    entries: int
    tp: int
    fp: int
    fn: int
    duplicates: int
    precision: float | None
    recall: float | None
    f1: float | None
    fpr: float | None
    mean_tp_confidence: float | None
    detection_latency_s: float | None


def build_rows(
    report: ScoreReport,
    manifest: Manifest,
    findings: Sequence[Finding],
    *,
    first_detection: Mapping[str, float],
    universe: Mapping[str, int],
) -> list[ResultRow]:
    """One row per problem type present in the manifest or among the findings, plus `unmapped`."""
    entry_type = {entry.id: entry.problem_type.value for entry in manifest.entries}
    entries_of = Counter(entry_type.values())
    confidence = {f.fingerprint: CONFIDENCE_RANK[f.confidence] for f in findings}

    ranks: dict[str, list[int]] = {}
    latencies: dict[str, list[float]] = {}
    for match in report.matches:
        problem_type = entry_type[match.entry_id]
        ranks.setdefault(problem_type, []).append(confidence[match.fingerprint])
        if match.entry_id in first_detection:
            latencies.setdefault(problem_type, []).append(first_detection[match.entry_id])

    rows = []
    for score in report.per_problem_type:
        name = score.problem_type.value
        negatives = max(universe.get(name, 0) - entries_of[name], 0)
        rows.append(
            ResultRow(
                problem_type=name,
                entries=entries_of[name],
                tp=score.tp,
                fp=score.fp,
                fn=score.fn,
                duplicates=score.duplicates,
                precision=score.precision,
                recall=score.recall,
                f1=score.f1,
                fpr=min(score.fp / negatives, 1.0) if negatives else None,
                mean_tp_confidence=sum(ranks[name]) / len(ranks[name]) if name in ranks else None,
                detection_latency_s=sum(latencies[name]) / len(latencies[name])
                if name in latencies
                else None,
            )
        )
    unmapped = sum(1 for f in report.false_positives if f.problem_type is None)
    if unmapped:
        rows.append(ResultRow(UNMAPPED, 0, 0, unmapped, 0, 0, None, None, None, None, None, None))
    return sorted(rows, key=lambda r: r.problem_type)
