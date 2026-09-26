"""From stored profile series to anomaly findings.

For each column: learn a range per metric from the baseline windows, judge the current
window against it with every detector, and combine the verdicts by vote. Only increases
become findings (NULL_SPIKE, DUPLICATE_SPIKE, DISTRIBUTION_SHIFT are spikes and shifts);
a decrease is still returned in the analyses, with its direction, but is not reported as one.

Data findings have no source line. Like runtime findings they name where they are:
`file` is `table:<Table>` and `line` is 0. The scorer matches them by the `table` and
`column` in their evidence. Their fingerprint is (rule, table, column, metric): stable
across windows, so a persisting problem is one problem.
"""

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from ..dataquality.models import Window
from ..finding import Evidence, Finding
from .detectors import MIN_HISTORY, Detection, Detector, default_detectors
from .series import (
    DISTRIBUTION_SHIFT,
    DUPLICATE_RATE,
    NULL_RATE,
    ColumnSeries,
    leave_one_out_distances,
    mean_shares,
    metrics_for,
    shares,
    total_variation,
    values_of,
)

Vote = Literal["any", "majority", "all"]
RULE_FOR_METRIC = {
    NULL_RATE: "NULL_SPIKE",
    DUPLICATE_RATE: "DUPLICATE_SPIKE",
    DISTRIBUTION_SHIFT: "DISTRIBUTION_SHIFT",
}
#: How many of the most-moved categories to list as an explanation.
EXPLAIN_TOP = 5


def passes_vote(fired: int, evaluated: int, vote: Vote) -> bool:
    if evaluated == 0:
        return False
    if vote == "any":
        return fired >= 1
    if vote == "all":
        return fired == evaluated
    return fired * 2 > evaluated  # strict majority of the detectors that could judge


@dataclass(frozen=True)
class MetricAnalysis:
    table: str
    column: str
    metric: str
    window: Window
    observation: float
    detections: tuple[Detection, ...]
    vote: Vote
    #: Extra context, e.g. which categories moved most for a distribution shift.
    explanation: Mapping[str, Any]

    @property
    def evaluated(self) -> int:
        return sum(d.evaluated for d in self.detections)

    @property
    def fired(self) -> int:
        return sum(d.anomalous for d in self.detections)

    @property
    def anomalous(self) -> bool:
        return passes_vote(self.fired, self.evaluated, self.vote)

    @property
    def direction(self) -> Literal["above", "below", "mixed"] | None:
        directions = {d.direction for d in self.detections if d.anomalous}
        if not directions:
            return None
        return directions.pop() if len(directions) == 1 else "mixed"  # type: ignore[return-value]


# ---- one column, one window -----------------------------------------------------------------


def _explain(current: Mapping[str, int], history: Sequence[Mapping[str, int]]) -> dict[str, Any]:
    baseline, now = mean_shares(history), shares(current)
    # Most-moved first; ties (a two-valued column moves both values equally) broken by name, so the
    # order never depends on set iteration and hence on the process's hash seed.
    moved = sorted(
        baseline.keys() | now.keys(),
        key=lambda v: (-abs(now.get(v, 0) - baseline.get(v, 0)), v),
    )
    return {
        "categories": [
            {
                "value": v,
                "baselineShare": float(baseline.get(v, 0)),
                "currentShare": float(now.get(v, 0)),
            }
            for v in moved[:EXPLAIN_TOP]
        ]
    }


def analyze_column(
    baseline: ColumnSeries,
    current: ColumnSeries,
    index: int,
    detectors: Sequence[Detector],
    vote: Vote,
) -> list[MetricAnalysis]:
    """Judges window `index` of `current` against the range learned from `baseline`."""
    analyses = []
    window = current.windows[index]
    for metric in metrics_for(baseline):
        explanation: dict[str, Any] = {}
        if metric == DISTRIBUTION_SHIFT:
            history_dists = [d for d in baseline.distributions if d is not None]
            observed = current.distributions[index]
            if observed is None or len(history_dists) < 2:
                continue
            history = leave_one_out_distances(history_dists)
            observation = total_variation(shares(observed), mean_shares(history_dists))
            explanation = _explain(observed, history_dists)
        else:
            value = values_of(current, metric)[index]
            if value is None:
                continue
            history = [v for v in values_of(baseline, metric) if v is not None]
            observation = value
        analyses.append(
            MetricAnalysis(
                table=baseline.table,
                column=baseline.column,
                metric=metric,
                window=window,
                observation=observation,
                detections=tuple(d.detect(history, observation) for d in detectors),
                vote=vote,
                explanation=explanation,
            )
        )
    return analyses


def detect_anomalies(
    baseline: Mapping[tuple[str, str], ColumnSeries],
    current: Mapping[tuple[str, str], ColumnSeries],
    *,
    window_start: datetime | None = None,
    history_before_window: bool = False,
    detectors: Sequence[Detector] | None = None,
    vote: Vote = "majority",
) -> list[MetricAnalysis]:
    """Analyzes one window (default: the latest) of every column present in both series sets.

    With `history_before_window` the baseline is cut to the windows before the one judged;
    use it when baseline and current are the same series.
    """
    chosen = list(detectors) if detectors is not None else default_detectors()
    if window_start is None:
        window_start = max(s.windows[-1].start for s in current.values() if s.windows)
    analyses: list[MetricAnalysis] = []
    for key in sorted(baseline.keys() & current.keys()):
        index = current[key].index_of(window_start)
        if index is None:
            continue
        history = baseline[key]
        if history_before_window:
            history = history.head(sum(w.start < window_start for w in history.windows))
        analyses += analyze_column(history, current[key], index, chosen, vote)
    return analyses


# ---- findings -------------------------------------------------------------------------------


def _confidence(fired: int, evaluated: int) -> Literal["LOW", "MEDIUM", "HIGH"]:
    if fired == evaluated:
        return "HIGH"
    return "MEDIUM" if fired * 2 > evaluated else "LOW"


def _range(detection: Detection) -> str:
    return f"[{detection.lower:.3f}, {detection.upper:.3f}]"


def _detector_sentence(d: Detection) -> str:
    verdict = f"{d.direction} the" if d.anomalous else "within the"
    return (
        f"{d.detector}: {d.observation:.3f} is {verdict} learned range {_range(d)} "
        f"(centre {d.center:.3f}, spread {d.spread:.3f}, {d.history_size} earlier windows)"
    )


_TITLES = {
    NULL_RATE: "{table}.{column}: NULL rate {value:.1%} is outside its learned range",
    DUPLICATE_RATE: "{table}.{column}: duplicate rate {value:.1%} is outside its learned range",
    DISTRIBUTION_SHIFT: "{table}.{column}: value distribution moved {value:.1%} from its baseline",
}


def _finding(a: MetricAnalysis) -> Finding:
    rule_id = RULE_FOR_METRIC[a.metric]
    file = f"table:{a.table}"
    where = {
        "table": a.table,
        "column": a.column,
        "metric": a.metric,
        "windowStart": a.window.start.isoformat(),
    }
    evaluated = [d for d in a.detections if d.evaluated]
    evidence = [
        Evidence(
            source="DATA_QUALITY",
            description=_detector_sentence(d),
            data={**where, **d.as_evidence()},
        )
        for d in evaluated
    ]
    if a.explanation:
        evidence.append(
            Evidence(
                source="DATA_QUALITY",
                description="Categories that moved most, baseline share to current share",
                data={**where, **a.explanation},
            )
        )
    meaning = {
        NULL_RATE: "share of rows where this column is NULL",
        DUPLICATE_RATE: "share of non-null values that repeat another value",
        DISTRIBUTION_SHIFT: "total-variation distance between this window's value shares and the "
        "mean of the baseline windows (the fraction of the distribution that moved)",
    }[a.metric]
    return Finding(
        schema_version=1,
        rule_id=rule_id,
        severity="MEDIUM",
        confidence=_confidence(a.fired, a.evaluated),
        file=file,
        line=0,
        title=_TITLES[a.metric].format(table=a.table, column=a.column, value=a.observation),
        body=(
            f"For the window starting {a.window.start:%Y-%m-%d}, the {meaning} is "
            f"{a.observation:.3f}. {a.fired} of {a.evaluated} detectors place that outside the "
            "range learned from this column's own history:\n\n"
            + "\n".join(f"- {_detector_sentence(d)}" for d in evaluated)
        ),
        evidence=evidence,
        suggested_fix=(
            f'```sql\n-- Compare recent rows with earlier ones for "{a.table}"."{a.column}":\n'
            f'SELECT count(*) AS rows, count("{a.column}") AS non_null,\n'
            f'       count(DISTINCT "{a.column}") AS distinct_values\nFROM "{a.table}";\n```'
        ),
        fingerprint=hashlib.sha256(
            "\x00".join([rule_id, file, a.column, a.metric]).encode()
        ).hexdigest()[:32],
    )


def to_findings(analyses: Sequence[MetricAnalysis]) -> list[Finding]:
    """One finding per analysis that the vote flags as an increase."""
    findings = [_finding(a) for a in analyses if a.anomalous and a.direction == "above"]
    return sorted(findings, key=lambda f: (f.file, f.rule_id, f.fingerprint))


# ---- backtest: false alarms on clean history --------------------------------------------------


def backtest(
    series: Mapping[tuple[str, str], ColumnSeries],
    *,
    detectors: Sequence[Detector] | None = None,
    vote: Vote = "majority",
    min_history: int = MIN_HISTORY,
) -> dict[str, Any]:
    """Walk-forward over history that is known to be clean: each window is judged against only
    the windows before it. Every alarm is therefore a false alarm."""
    chosen = list(detectors) if detectors is not None else default_detectors()
    per_detector: dict[str, dict[str, int]] = {
        d.name: {"evaluations": 0, "alarms": 0, "alarms_above": 0} for d in chosen
    }
    overall = {"evaluations": 0, "alarms": 0, "alarms_above": 0}
    alarms: list[dict[str, Any]] = []
    by_metric: dict[str, dict[str, int]] = defaultdict(
        lambda: {"evaluations": 0, "alarms_above": 0}
    )

    for key in sorted(series):
        full = series[key]
        for index in range(min_history, len(full.windows)):
            for a in analyze_column(full.head(index), full, index, chosen, vote):
                for d in a.detections:
                    if d.evaluated:
                        stats = per_detector[d.detector]
                        stats["evaluations"] += 1
                        stats["alarms"] += d.anomalous
                        stats["alarms_above"] += d.anomalous and d.direction == "above"
                if a.evaluated == 0:
                    continue
                overall["evaluations"] += 1
                by_metric[a.metric]["evaluations"] += 1
                if a.anomalous:
                    overall["alarms"] += 1
                    if a.direction == "above":
                        overall["alarms_above"] += 1
                        by_metric[a.metric]["alarms_above"] += 1
                    alarms.append(
                        {
                            "table": a.table,
                            "column": a.column,
                            "metric": a.metric,
                            "window_start": a.window.start.isoformat(),
                            "direction": a.direction,
                            "observation": a.observation,
                            "fired": a.fired,
                            "evaluated": a.evaluated,
                        }
                    )
    return {
        "vote": vote,
        "min_history": min_history,
        "series": len(series),
        "per_detector": per_detector,
        "vote_result": overall,
        "by_metric": dict(by_metric),
        "false_alarms": alarms,
    }
