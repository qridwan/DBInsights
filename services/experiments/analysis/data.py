"""Turns the stored raw rows of one experiment into per-problem outcomes ready for statistics.

The results table holds counts per problem type. Paired tests need to know *which* problem each
configuration detected, so outcomes are recomputed by re-scoring the findings stored with each
run (`ablation.run_findings`) against the ground-truth manifest. The recomputed counts are
checked against the stored ones, so a drift between the scorer and the stored results cannot go
unnoticed.
"""

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from experiments.groundtruth import Manifest, load_manifest, parse_findings, score

CONFIDENCE_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


@dataclass(frozen=True)
class Outcome:
    """One ground-truth problem in one run."""

    config: str
    app: str
    repetition: int
    entry_id: str
    problem_type: str
    detected: bool
    #: Confidence rank (1 LOW .. 3 HIGH) of the finding that matched; None when missed.
    confidence: int | None
    #: Seconds until the first layer whose findings matched; None when missed.
    latency_s: float | None


@dataclass(frozen=True)
class RunRecord:
    config: str
    app: str
    repetition: int
    sensitivity: bool
    wall_s: float
    cpu_s: float
    tp: int
    fp: int
    fn: int
    #: Total negatives in the app's universe, across problem types (for the pooled FPR).
    negatives: int
    #: One entry per scored finding: True for a true positive, False for a false positive.
    finding_labels: tuple[bool, ...]


@dataclass
class Dataset:
    experiment_id: str
    provenance: dict[str, Any]
    runs: list[RunRecord] = field(default_factory=list)
    outcomes: list[Outcome] = field(default_factory=list)
    #: Stored per-problem-type result rows, exactly as written by the harness.
    result_rows: list[dict[str, Any]] = field(default_factory=list)
    entries: dict[str, list[str]] = field(default_factory=dict)  # app -> entry ids
    problem_types: dict[str, str] = field(default_factory=dict)  # entry id -> problem type

    def configs(self) -> list[str]:
        seen: dict[str, None] = {}
        for run in self.runs:
            seen.setdefault(run.config)
        return list(seen)

    def repetitions(self, config: str) -> list[int]:
        return sorted({r.repetition for r in self.runs if r.config == config})

    def apps(self) -> list[str]:
        return sorted({r.app for r in self.runs})


def _negatives(universe: dict[str, int], entries_of: dict[str, int]) -> int:
    return sum(max(count - entries_of.get(name, 0), 0) for name, count in universe.items())


def load_dataset(store: Any, experiment_id: str, manifests_dir: Path) -> Dataset:
    experiment = next(
        (e for e in store.experiments() if str(e["experiment_id"]) == experiment_id), None
    )
    if experiment is None:
        raise KeyError(f"no experiment {experiment_id}")
    dataset = Dataset(
        experiment_id=experiment_id,
        provenance={
            key: (str(experiment[key]) if key.endswith("_at") else experiment[key])
            for key in (
                "git_commit",
                "git_dirty",
                "code_sha256",
                "repetitions",
                "seed",
                "apps",
                "configurations",
                "universe",
                "parameters",
                "started_at",
                "finished_at",
            )
            if key in experiment
        },
    )

    manifests: dict[str, Manifest] = {
        app: load_manifest(manifests_dir / f"{app}.json") for app in experiment["apps"]
    }
    for app, manifest in manifests.items():
        dataset.entries[app] = [e.id for e in manifest.entries]
        for entry in manifest.entries:
            dataset.problem_types[entry.id] = entry.problem_type.value
    entries_of = {
        app: {
            name: sum(e.problem_type.value == name for e in manifest.entries)
            for name in {e.problem_type.value for e in manifest.entries}
        }
        for app, manifest in manifests.items()
    }

    dataset.result_rows = store.results(experiment_id)
    stored = defaultdict(lambda: [0, 0, 0])
    for row in dataset.result_rows:
        counts = stored[(row["config"], row["app"], row["repetition"])]
        counts[0] += row["tp"]
        counts[1] += row["fp"]
        counts[2] += row["fn"]

    for run in store.runs(experiment_id):
        run_id = run["run_id"]
        stages = {
            r["stage"]: r["findings"]
            for r in store.conn.execute(
                "SELECT stage, findings FROM ablation.run_findings WHERE run_id = %s", (run_id,)
            ).fetchall()
        }
        manifest = manifests[run["app"]]
        report = score(parse_findings(_as_list(stages["correlated"])), manifest)
        available = _as_dict(run["layer_available_s"])

        first_seen: dict[str, float] = {}
        for stage, raw in stages.items():
            if stage == "correlated" or not raw:
                continue
            for match in score(parse_findings(_as_list(raw)), manifest).matches:
                first_seen[match.entry_id] = min(
                    first_seen.get(match.entry_id, math.inf), available[stage]
                )

        confidence_of = {
            f["fingerprint"]: CONFIDENCE_RANK[f["confidence"]]
            for f in _as_list(stages["correlated"])
        }
        matched = {m.entry_id: m for m in report.matches}
        for entry in manifest.entries:
            match = matched.get(entry.id)
            latency = None
            if match is not None:
                # Found only by combining layers: available once the whole run had finished.
                latency = first_seen.get(entry.id, run["wall_s"])
            dataset.outcomes.append(
                Outcome(
                    config=run["config"],
                    app=run["app"],
                    repetition=run["repetition"],
                    entry_id=entry.id,
                    problem_type=entry.problem_type.value,
                    detected=match is not None,
                    confidence=confidence_of[match.fingerprint] if match else None,
                    latency_s=latency,
                )
            )

        key = (run["config"], run["app"], run["repetition"])
        recomputed = [report.aggregate.tp, report.aggregate.fp, report.aggregate.fn]
        if stored[key] != recomputed:
            raise AssertionError(
                f"re-scoring {key} gave TP/FP/FN {recomputed}, stored rows say {stored[key]}"
            )

        universe = experiment["universe"][run["app"]]
        dataset.runs.append(
            RunRecord(
                config=run["config"],
                app=run["app"],
                repetition=run["repetition"],
                sensitivity=run["sensitivity"],
                wall_s=run["wall_s"],
                cpu_s=run["cpu_s"],
                tp=report.aggregate.tp,
                fp=report.aggregate.fp,
                fn=report.aggregate.fn,
                negatives=_negatives(universe, entries_of[run["app"]]),
                finding_labels=(True,) * report.aggregate.tp + (False,) * report.aggregate.fp,
            )
        )
    return dataset


def _as_list(value: Any) -> list[dict[str, Any]]:
    return json.loads(value) if isinstance(value, str) else value


def _as_dict(value: Any) -> dict[str, float]:
    return json.loads(value) if isinstance(value, str) else value
