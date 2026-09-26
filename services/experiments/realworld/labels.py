"""M6.3: what the human labels say about the rules' real-world precision.

Reads a labelled worksheet (the one `worksheet` wrote, with `label` / `fp_cause` / `rationale`
filled in by people) and computes, from the labels alone:

* per-rule precision with confidence intervals, and overall precision;
* Cohen's kappa on the double-labelled rows;
* a breakdown of false-positive causes;
* for MISSING_INDEX_ON_FILTERED_FIELD, how often the index existed in the database but not in
  schema.prisma (the real-world RQ6 divergence);
* the comparison with the controlled experiment's per-rule precision.

Nothing here judges a finding. Rows the labellers left unlabelled or marked UNSURE are counted
and reported, never guessed at.

Intervals
---------
Precision is a proportion, so the Wilson score interval is the primary interval: unlike the
normal approximation it stays inside [0, 1] and behaves at small n and at 0% or 100%. But
findings inside one repository are not independent (one repo with a repeated code pattern can
yield dozens of near-identical findings), which makes the Wilson interval too narrow. A
cluster bootstrap over repositories, which resamples whole repositories, is reported next to it;
where the two disagree, the wider is the honest one. Kappa gets a bootstrap interval over rows.

Comparison with the controlled experiment
-----------------------------------------
Two independent proportions with small counts (the controlled experiment has few or no false
positives), so Fisher's exact test, Holm-corrected across the rules compared. A rule diverges
when the corrected p is below 0.05; the size of the gap is reported either way.
"""

import csv
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from scipy import stats as scipy_stats

from experiments.analysis.stats import bootstrap_ci, holm

LABELS = ("TP", "FP", "UNSURE")
FP_CAUSES = (
    "analysis_error",
    "schema_misread",
    "pattern_harmless_here",
    "not_application_code",
    "index_outside_schema",
    "other",
)
INDEX_RULE = "MISSING_INDEX_ON_FILTERED_FIELD"
SEED = 20261003
Z95 = 1.959963984540054


class LabelError(ValueError):
    """The worksheet does not follow the labelling protocol; the message lists every problem."""


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(centre - half, 0.0), min(centre + half, 1.0)


def load(worksheet: Path, key: Path | None = None, allow_partial: bool = False) -> list[dict]:
    """Rows with normalised labels; LabelError lists everything that breaks the protocol."""
    with worksheet.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    confidence: dict[str, str] = {}
    if key is not None:
        with key.open(newline="", encoding="utf-8") as handle:
            confidence = {r["finding_id"]: r["confidence"] for r in csv.DictReader(handle)}

    problems: list[str] = []
    for row in rows:
        fid = row["finding_id"]
        for suffix in ("", "_2"):
            label = row[f"label{suffix}"].strip().upper()
            cause = row[f"fp_cause{suffix}"].strip()
            why = row[f"rationale{suffix}"].strip()
            row[f"label{suffix}"], row[f"fp_cause{suffix}"] = label, cause
            if suffix == "_2" and row["double_label"] != "yes":
                if label or cause or why:
                    problems.append(f"{fid}: second label given on a row not in the double sample")
                continue
            if not label:
                if suffix == "" and not allow_partial:
                    problems.append(f"{fid}: no label")
                if suffix == "_2" and not allow_partial:
                    problems.append(f"{fid}: double-label row has no second label")
                continue
            if label not in LABELS:
                problems.append(f"{fid}: label{suffix} '{label}' is not one of {LABELS}")
            elif label == "FP" and cause not in FP_CAUSES:
                problems.append(f"{fid}: FP needs fp_cause{suffix} from {FP_CAUSES}, got '{cause}'")
            elif label != "FP" and cause:
                problems.append(f"{fid}: fp_cause{suffix} given for a {label}")
            if label == "UNSURE" and not why:
                problems.append(f"{fid}: UNSURE needs a rationale{suffix}")
        row["confidence"] = confidence.get(fid, "")
    if problems:
        raise LabelError("\n".join(problems))
    return rows


# ---- precision -------------------------------------------------------------------------


def _counts(rows: list[dict]) -> dict[str, int]:
    tally = Counter(r["label"] for r in rows if r["label"])
    return {"tp": tally["TP"], "fp": tally["FP"], "unsure": tally["UNSURE"]}


def _precision(tp: int, fp: int) -> float | None:
    return tp / (tp + fp) if tp + fp else None


def _cluster_ci(rows: list[dict], seed: int) -> tuple[float | None, float | None]:
    """Bootstrap over repositories: resample whole repos, recompute pooled precision."""
    by_repo: dict[str, tuple[int, int]] = {}
    for repo in {r["repo"] for r in rows}:
        c = _counts([r for r in rows if r["repo"] == repo])
        by_repo[repo] = (c["tp"], c["fp"])
    repos = sorted(by_repo)
    if len(repos) < 2:
        return None, None

    def draw(rng: random.Random) -> float | None:
        picked = [by_repo[repos[rng.randrange(len(repos))]] for _ in repos]
        return _precision(sum(t for t, _ in picked), sum(f for _, f in picked))

    return bootstrap_ci(draw, seed=seed)


def summarize(rows: list[dict]) -> dict[str, Any]:
    labelled = [r for r in rows if r["label"]]

    def block(subset: list[dict], seed: int) -> dict[str, Any]:
        c = _counts(subset)
        low, high = wilson(c["tp"], c["tp"] + c["fp"])
        cluster_low, cluster_high = _cluster_ci(subset, seed)
        return {
            "findings": len(subset),
            "labelled": sum(bool(r["label"]) for r in subset),
            **c,
            "precision": _precision(c["tp"], c["fp"]),
            "wilson_95": {"low": low, "high": high},
            "repo_cluster_bootstrap_95": {"low": cluster_low, "high": cluster_high},
            "repos": len({r["repo"] for r in subset if r["label"]}),
            # If every UNSURE were a false / true positive: the range precision could lie in.
            "precision_if_unsure_all_fp": _precision(c["tp"], c["fp"] + c["unsure"]),
            "precision_if_unsure_all_tp": _precision(c["tp"] + c["unsure"], c["fp"]),
        }

    rules = sorted({r["rule_id"] for r in rows})
    per_rule = {
        rule: block([r for r in rows if r["rule_id"] == rule], SEED + i)
        for i, rule in enumerate(rules)
    }
    macro = [v["precision"] for v in per_rule.values() if v["precision"] is not None]
    return {
        "per_rule": per_rule,
        "overall": {
            **block(rows, SEED + 99),
            "macro_average_precision": sum(macro) / len(macro) if macro else None,
        },
        "label_coverage": {
            "findings": len(rows),
            "labelled": len(labelled),
            "unlabelled": len(rows) - len(labelled),
        },
        "precision_by_confidence": _by_confidence(rows),
    }


def _by_confidence(rows: list[dict]) -> dict[str, Any]:
    """Extra: does the analyzer's own confidence track precision? (Hidden while labelling.)"""
    out: dict[str, Any] = {}
    for rule in sorted({r["rule_id"] for r in rows}):
        out[rule] = {}
        for level in ("HIGH", "MEDIUM", "LOW"):
            subset = [r for r in rows if r["rule_id"] == rule and r["confidence"] == level]
            c = _counts(subset)
            if c["tp"] + c["fp"]:
                low, high = wilson(c["tp"], c["tp"] + c["fp"])
                out[rule][level] = {
                    **c,
                    "precision": _precision(c["tp"], c["fp"]),
                    "wilson_95": [low, high],
                }
    return out


# ---- agreement -------------------------------------------------------------------------


def cohens_kappa(first: list[str], second: list[str]) -> float | None:
    """Cohen's kappa for two raters over the same items; None when chance agreement is total."""
    n = len(first)
    if n == 0:
        return None
    observed = sum(a == b for a, b in zip(first, second, strict=True)) / n
    a_counts, b_counts = Counter(first), Counter(second)
    expected = sum(a_counts[k] * b_counts[k] for k in a_counts.keys() | b_counts.keys()) / (n * n)
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)


def agreement(rows: list[dict]) -> dict[str, Any]:
    pairs = [
        (r["label"], r["label_2"])
        for r in rows
        if r["double_label"] == "yes" and r["label"] and r["label_2"]
    ]
    binary = [(a, b) for a, b in pairs if "UNSURE" not in (a, b)]

    def kappa_ci(items: list[tuple[str, str]]) -> tuple[float | None, float | None]:
        def draw(rng: random.Random) -> float | None:
            sample = [items[rng.randrange(len(items))] for _ in items]
            return cohens_kappa([a for a, _ in sample], [b for _, b in sample])

        return bootstrap_ci(draw, seed=SEED + 200) if len(items) >= 2 else (None, None)

    def block(items: list[tuple[str, str]]) -> dict[str, Any]:
        k = cohens_kappa([a for a, _ in items], [b for _, b in items])
        low, high = kappa_ci(items)
        return {
            "n": len(items),
            "percent_agreement": sum(a == b for a, b in items) / len(items) if items else None,
            "kappa": k,
            "kappa_bootstrap_95": {"low": low, "high": high},
        }

    return {
        "double_labelled_rows": sum(r["double_label"] == "yes" for r in rows),
        "with_both_labels": len(pairs),
        "three_way_TP_FP_UNSURE": block(pairs),
        "binary_TP_FP_excluding_UNSURE": block(binary),
        "disagreements": [
            {
                "finding_id": r["finding_id"],
                "rule_id": r["rule_id"],
                "first": r["label"],
                "second": r["label_2"],
            }
            for r in rows
            if r["double_label"] == "yes"
            and r["label"]
            and r["label_2"]
            and r["label"] != r["label_2"]
        ],
        "note": "Both labels are kept as given; nothing was adjudicated.",
    }


# ---- false-positive causes and the index divergence ------------------------------------


def fp_causes(rows: list[dict]) -> dict[str, Any]:
    fps = [r for r in rows if r["label"] == "FP"]
    total = Counter(r["fp_cause"] for r in fps)
    by_rule: dict[str, Counter] = defaultdict(Counter)
    for r in fps:
        by_rule[r["rule_id"]][r["fp_cause"]] += 1
    return {
        "false_positives": len(fps),
        "by_cause": {c: total[c] for c in FP_CAUSES},
        "share_by_cause": {c: (total[c] / len(fps) if fps else None) for c in FP_CAUSES},
        "by_rule_and_cause": {
            rule: {c: by_rule[rule][c] for c in FP_CAUSES} for rule in sorted(by_rule)
        },
    }


def index_divergence(rows: list[dict]) -> dict[str, Any]:
    """How often an index existed in the database but was absent from schema.prisma."""
    r2 = [r for r in rows if r["rule_id"] == INDEX_RULE and r["label"] in ("TP", "FP")]
    outside = sum(r["label"] == "FP" and r["fp_cause"] == "index_outside_schema" for r in r2)
    low, high = wilson(outside, len(r2))
    repos = sorted({r["repo"] for r in r2 if r["fp_cause"] == "index_outside_schema"})
    return {
        "rule": INDEX_RULE,
        "labelled_findings": len(r2),
        "index_in_database_not_in_schema": outside,
        "rate": outside / len(r2) if r2 else None,
        "wilson_95": {"low": low, "high": high},
        "repos_with_divergence": repos,
        "caveat": "Establishable only for projects whose migrations or SQL are in the repository; "
        "for the rest the true rate cannot be measured, so this is a lower bound.",
    }


# ---- against the controlled experiment -------------------------------------------------


def controlled_precision(config: str = "B2") -> tuple[dict[str, dict[str, int]], str | None]:
    """Per-rule TP/FP of the controlled experiment's Approach B configuration, from Postgres."""
    from experiments.ablation.experiment import _urls
    from experiments.ablation.store import AblationStore
    from experiments.groundtruth.problems import RULE_PROBLEM_TYPES

    store = AblationStore(_urls("blog")[1])
    try:
        experiment = store.latest_experiment()
        if experiment is None:
            return {}, None
        rows = [r for r in store.results(experiment) if r["config"] == config]
    finally:
        store.close()
    per_type: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        per_type[r["problem_type"]].append(r)
    reps = max((r["repetition"] for r in rows), default=1)
    out = {}
    for rule, problem_type in RULE_PROBLEM_TYPES.items():
        if rule not in ("N_PLUS_ONE_IN_LOOP", INDEX_RULE, "MISSING_PAGINATION"):
            continue
        cells = per_type.get(problem_type.value, [])
        if cells:
            # Accuracy is deterministic across repetitions; the mean over them is the value.
            out[rule] = {
                "tp": round(sum(c["tp"] for c in cells) / reps),
                "fp": round(sum(c["fp"] for c in cells) / reps),
            }
    return out, experiment


def compare_with_controlled(
    summary: dict[str, Any], controlled: dict[str, dict[str, int]]
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    testable: list[str] = []
    p_values: list[float] = []
    for rule, real in summary["per_rule"].items():
        if rule not in controlled:
            results[rule] = {
                "comparable": False,
                "reason": "the controlled experiment has no injected problems for this rule",
            }
            continue
        c = controlled[rule]
        if real["tp"] + real["fp"] == 0 or c["tp"] + c["fp"] == 0:
            results[rule] = {"comparable": False, "reason": "no labelled findings on one side"}
            continue
        p = float(scipy_stats.fisher_exact([[real["tp"], real["fp"]], [c["tp"], c["fp"]]]).pvalue)
        results[rule] = {
            "comparable": True,
            "real_world": {
                "tp": real["tp"],
                "fp": real["fp"],
                "precision": real["precision"],
                "wilson_95": real["wilson_95"],
            },
            "controlled": {**c, "precision": _precision(c["tp"], c["fp"])},
            "difference": real["precision"] - _precision(c["tp"], c["fp"]),
            "fisher_p": p,
        }
        testable.append(rule)
        p_values.append(p)
    for rule, adjusted in zip(testable, holm(p_values), strict=True):
        results[rule]["fisher_p_holm"] = adjusted
        results[rule]["diverges"] = adjusted < 0.05
    return results


def analyze(
    worksheet: Path, key: Path | None, allow_partial: bool = False, with_controlled: bool = True
) -> dict[str, Any]:
    rows = load(worksheet, key, allow_partial)
    summary = summarize(rows)
    result: dict[str, Any] = {
        "worksheet": str(worksheet),
        **summary,
        "agreement": agreement(rows),
        "false_positive_causes": fp_causes(rows),
        "index_divergence": index_divergence(rows),
    }
    if with_controlled:
        controlled, experiment = controlled_precision()
        result["controlled_experiment"] = experiment
        result["real_world_vs_controlled"] = compare_with_controlled(summary, controlled)
    return result
