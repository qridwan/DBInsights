"""Renders the results chapter from a template and the stored results.

    python -m experiments.writeup.build            # -> docs/thesis/results.md

The prose lives in `results_chapter.template.md`. Every number in it is a `{{placeholder}}` that is
looked up in the stored results, formatted, and recorded with its source in an appendix, so a
claim cannot quote a number the results do not contain: an unknown placeholder is an error.

Placeholders:  {{path.to.value}}  or  {{path.to.value|format}}
Blocks (tables): {{block:name}}
Formats: pct0 pct1 pct2 f1 f2 f3 int p ci (proportion with interval) cis (seconds with interval) raw
"""

import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SERVICES = Path(__file__).resolve().parents[2]
REPO = SERVICES.parent
RESULTS = SERVICES / "experiments" / "results"
TEMPLATE = Path(__file__).with_name("results_chapter.template.md")
DEFAULT_OUT = REPO / "docs" / "thesis" / "results.md"

ORDER = ["A", "A-log", "B1", "B2", "C1", "C2", "C3"]
ABLATION = ["A", "B1", "B2", "C1", "C2", "C3"]


class TemplateError(KeyError):
    """A placeholder names a number the results do not contain."""


@dataclass(frozen=True)
class Val:
    value: Any
    source: str


def pct(v: float, digits: int = 1) -> str:
    return f"{v * 100:.{digits}f}%"


def fmt_p(p: float) -> str:
    return f"{p:.1e}" if p < 0.001 else f"{p:.3f}"


FORMATS: dict[str, Callable[[Any], str]] = {
    "pct1": lambda v: pct(v, 1),
    "pct0": lambda v: pct(v, 0),
    "pct2": lambda v: pct(v, 2),
    "f1": lambda v: f"{v:.1f}",
    "f2": lambda v: f"{v:.2f}",
    "f3": lambda v: f"{v:.3f}",
    "int": lambda v: str(int(round(v))),
    "p": fmt_p,
    "raw": str,
    "ci": lambda t: f"{pct(t[0])} (95% CI {pct(t[1])} to {pct(t[2])})",
    "cis": lambda t: f"{t[0]:.2f} s (95% CI {t[1]:.2f} to {t[2]:.2f})",
}


def load(name: str) -> Any:
    path = RESULTS / name
    return json.loads(path.read_text()) if path.exists() else None


def _ci(mean: float | None, low: float | None, high: float | None):
    return None if mean is None or low is None or high is None else (mean, low, high)


def namespace(
    results: dict[str, Any],
    backtests: dict[str, dict[str, Any]],
    overhead: dict[str, Any],
    summary: dict[str, Any],
    coverage: dict[str, Any],
    labels: dict[str, Any] | None,
) -> dict[str, Any]:
    R = "results.json"
    ns: dict[str, Any] = {"cfg": {}, "typ": {}, "cmp": {}}

    for name, config in results["configurations"].items():
        pooled, boot = config["pooled_over_apps"], config["problem_bootstrap"]
        problems, scored = boot["problems"], boot["scored_findings"]
        recall = pooled["recall"]["mean"]
        detected = round(recall * problems)
        base = f"{R}:configurations.{name}"
        entry: dict[str, Any] = {
            "problems": Val(problems, f"{base}.problem_bootstrap.problems"),
            "scored": Val(scored, f"{base}.problem_bootstrap.scored_findings"),
            "detected": Val(detected, f"{base}.pooled_over_apps.recall.mean x problems"),
            "missed": Val(problems - detected, f"{base}: problems - detected"),
            "fp": Val(scored - detected, f"{base}: scored_findings - detected"),
        }
        for metric, key in (("precision", "precision"), ("recall", "recall"), ("f1", "f1")):
            m = pooled[key]["mean"]
            if m is not None:
                entry[metric] = Val(m, f"{base}.pooled_over_apps.{key}.mean")
                entry[f"{metric}_ci"] = Val(
                    _ci(m, boot[key]["low"], boot[key]["high"]),
                    f"{base}.pooled_over_apps.{key}.mean, {base}.problem_bootstrap.{key}",
                )
        fpr = pooled["false_positive_rate"]["mean"]
        entry["fpr"] = Val(fpr, f"{base}.pooled_over_apps.false_positive_rate.mean")
        for metric in ("cpu_s", "wall_s", "detection_latency_s"):
            ci = pooled[metric]
            if ci["mean"] is not None:
                entry[metric] = Val(ci["mean"], f"{base}.pooled_over_apps.{metric}.mean")
                entry[f"{metric}_ci"] = Val(
                    _ci(ci["mean"], ci["low"], ci["high"]), f"{base}.pooled_over_apps.{metric}"
                )
        ns["cfg"][name] = entry
        ns["typ"][name] = {
            t: {
                "recall": Val(v["recall"]["mean"], f"{base}.per_problem_type.{t}.recall.mean"),
                "entries": Val(v["entries"], f"{base}.per_problem_type.{t}.entries"),
                "precision": Val(
                    v["precision"]["mean"], f"{base}.per_problem_type.{t}.precision.mean"
                ),
                "tp": Val(v["tp"]["mean"], f"{base}.per_problem_type.{t}.tp.mean"),
                "fp": Val(v["fp"]["mean"], f"{base}.per_problem_type.{t}.fp.mean"),
                "fn": Val(v["fn"]["mean"], f"{base}.per_problem_type.{t}.fn.mean"),
            }
            for t, v in config["per_problem_type"].items()
        }

    for c in results["comparisons"]:
        d, acc = c["detection_mcnemar_exact"], c["accuracy_difference_bootstrap"]
        cpu, conf = c["timing_wilcoxon"]["cpu_s"], c["confidence_wilcoxon"]
        base = f"{R}:comparisons[{c['id']}]"
        e: dict[str, Any] = {
            "first": Val(c["first"], f"{base}.first"),
            "second": Val(c["second"], f"{base}.second"),
            "only_second": Val(d["only_second"], f"{base}.detection_mcnemar_exact.only_second"),
            "only_first": Val(d["only_first"], f"{base}.detection_mcnemar_exact.only_first"),
            "both": Val(d["both"], f"{base}.detection_mcnemar_exact.both"),
            "p": Val(d["p_value"], f"{base}.detection_mcnemar_exact.p_value"),
            "rd": Val(d["risk_difference"], f"{base}.detection_mcnemar_exact.risk_difference"),
            "cpu_first": Val(cpu["first_mean"], f"{base}.timing_wilcoxon.cpu_s.first_mean"),
            "cpu_second": Val(cpu["second_mean"], f"{base}.timing_wilcoxon.cpu_s.second_mean"),
            "cpu_p": Val(cpu["p_value"], f"{base}.timing_wilcoxon.cpu_s.p_value"),
            "cpu_cliffs": Val(cpu["cliffs_delta"], f"{base}.timing_wilcoxon.cpu_s.cliffs_delta"),
            "conf_n": Val(conf["n"], f"{base}.confidence_wilcoxon.n"),
            "verdict": Val(c["verdict"], f"{base}.verdict"),
        }
        if c["detection_p_holm"] is not None:
            e["p_holm"] = Val(c["detection_p_holm"], f"{base}.detection_p_holm")
        if conf["first_mean"] is not None:
            e["conf_first"] = Val(conf["first_mean"], f"{base}.confidence_wilcoxon.first_mean")
            e["conf_second"] = Val(conf["second_mean"], f"{base}.confidence_wilcoxon.second_mean")
            e["conf_p"] = Val(conf["p_value"], f"{base}.confidence_wilcoxon.p_value")
        for metric in ("recall", "f1", "precision"):
            a = acc[metric]
            if a["difference"] is not None:
                e[f"{metric}_diff"] = Val(
                    (a["difference"], a["ci_low"], a["ci_high"]),
                    f"{base}.accuracy_difference_bootstrap.{metric}",
                )
        ns["cmp"][c["id"]] = e

    h5 = results["h5_index_share"]
    hb = f"{R}:h5_index_share"
    ns["h5"] = {
        "share": Val(h5["share"], f"{hb}.share"),
        "share_ci": Val(
            (h5["share"], h5["wilson_95"]["low"], h5["wilson_95"]["high"]),
            f"{hb}.share, {hb}.wilson_95",
        ),
        "obtainable": Val(h5["obtainable_with_database"], f"{hb}.obtainable_with_database"),
        "also": Val(h5["also_from_declared_schema_alone"], f"{hb}.also_from_declared_schema_alone"),
        "in_benchmark": Val(h5["index_problems_in_benchmark"], f"{hb}.index_problems_in_benchmark"),
        **{
            t: {k: Val(v, f"{hb}.per_type.{t}.{k}") for k, v in row.items()}
            for t, row in h5["per_type"].items()
        },
    }

    evaluations = sum(b["vote_result"]["evaluations"] for b in backtests.values())
    alarms = sum(b["vote_result"]["alarms_above"] for b in backtests.values())
    bt: dict[str, Any] = {
        "evaluations": Val(evaluations, "anomaly_backtest_*.json: sum of vote_result.evaluations"),
        "alarms": Val(alarms, "anomaly_backtest_*.json: sum of vote_result.alarms_above"),
        "rate": Val(alarms / evaluations, "alarms / evaluations"),
    }
    for app, b in backtests.items():
        bt[app] = {
            "evaluations": Val(
                b["vote_result"]["evaluations"],
                f"anomaly_backtest_{app}.json:vote_result.evaluations",
            ),
            "alarms": Val(
                b["vote_result"]["alarms_above"],
                f"anomaly_backtest_{app}.json:vote_result.alarms_above",
            ),
            "series": Val(b["series"], f"anomaly_backtest_{app}.json:series"),
        }
    detectors = ("zscore", "iqr", "moving_average")
    bt["detector"] = {
        d: Val(
            sum(b["per_detector"][d]["alarms_above"] for b in backtests.values()),
            f"anomaly_backtest_*.json: sum of per_detector.{d}.alarms_above",
        )
        for d in detectors
    }
    ns["bt"] = bt

    sessions = overhead["sessions"]
    oh: dict[str, Any] = {"sessions": Val(len(sessions), "collector_overhead.json:sessions")}
    for app in sorted({s["app"] for s in sessions}):
        mine = [s for s in sessions if s["app"] == app]
        ms = [s["median_overhead_ms"] for s in mine]
        ratio = [s["median_overhead_ratio"] for s in mine]
        src = f"collector_overhead.json: {app} sessions"
        oh[app] = {
            "n": Val(len(mine), src),
            "ms_min": Val(min(ms), src),
            "ms_max": Val(max(ms), src),
            "ratio_min": Val(min(ratio), src),
            "ratio_max": Val(max(ratio), src),
        }
    ns["oh"] = oh

    s = summary
    ns["rw"] = {
        k: Val(s[k], f"realworld_summary.json:{k}")
        for k in (
            "pool_size",
            "evaluated",
            "eligible",
            "study_repositories",
            "findings",
            "repositories_analyzed_ok",
            "repositories_failed",
            "repositories_with_zero_findings",
        )
    } | {
        "rule": {
            r: Val(n, f"realworld_summary.json:findings_by_rule.{r}")
            for r, n in s["findings_by_rule"].items()
        },
        "confidence": {
            r: Val(n, f"realworld_summary.json:findings_by_confidence.{r}")
            for r, n in s["findings_by_confidence"].items()
        },
    }
    ns["cov"] = {
        "zero": Val(
            len(coverage["with_zero_located_operations"]),
            "realworld_coverage.json:with_zero_located_operations",
        ),
        "zero_lookalikes": Val(
            len(coverage["zero_located_but_text_lookalikes_ge_10"]),
            "realworld_coverage.json:zero_located_but_text_lookalikes_ge_10",
        ),
    }
    prov = results["provenance"]
    ns["prov"] = {
        "repetitions": Val(prov["repetitions"], f"{R}:provenance.repetitions"),
        "commit": Val(prov["git_commit"], f"{R}:provenance.git_commit"),
        "sha": Val(str(prov["code_sha256"])[:12], f"{R}:provenance.code_sha256"),
    }
    return ns


# ---- tables ----------------------------------------------------------------------------------


def table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def block_accuracy(ns, ctx) -> tuple[str, str]:
    rows = []
    for c in ORDER:
        e = ns["cfg"][c]
        rows.append(
            [
                c if c != "A-log" else "A-log (sensitivity)",
                FORMATS["ci"](e["precision_ci"].value) if "precision_ci" in e else "no findings",
                FORMATS["ci"](e["recall_ci"].value),
                FORMATS["ci"](e["f1_ci"].value) if "f1_ci" in e else "undefined",
                pct(e["fpr"].value, 2),
                f"{e['detected'].value} of {e['problems'].value}",
                str(e["scored"].value),
            ]
        )
    return (
        table(
            [
                "Config",
                "Precision",
                "Recall",
                "F1",
                "False-positive rate",
                "Problems found",
                "Scored findings",
            ],
            rows,
        ),
        "results.json:configurations.*.pooled_over_apps.{precision,recall,f1,false_positive_rate}, problem_bootstrap.*",
    )


def block_types(ns, ctx) -> tuple[str, str]:
    types = sorted(ns["typ"]["C3"])
    rows = []
    for t in types:
        n = ns["typ"]["C3"][t]["entries"].value
        rows.append([f"`{t}`", str(n)] + [pct(ns["typ"][c][t]["recall"].value, 0) for c in ORDER])
    return (
        table(["Problem type", "Problems", *ORDER], rows),
        "results.json:configurations.*.per_problem_type.*.{entries,recall.mean}",
    )


def block_tests(ns, ctx) -> tuple[str, str]:
    rows = []
    for cid, e in ns["cmp"].items():
        rd = e["recall_diff"].value if "recall_diff" in e else None
        rows.append(
            [
                f"`{cid}`",
                f"{e['first'].value} to {e['second'].value}",
                f"+{e['only_second'].value} / -{e['only_first'].value}",
                fmt_p(e["p"].value.__float__()),
                fmt_p(e["p_holm"].value) if "p_holm" in e else "not in family",
                f"{rd[0] * 100:+.1f} pts ({rd[1] * 100:.1f} to {rd[2] * 100:.1f})" if rd else "n/a",
            ]
        )
    return (
        table(
            [
                "Comparison",
                "Configs",
                "Problems gained / lost",
                "Exact McNemar p",
                "Holm p",
                "Recall difference (95% bootstrap CI)",
            ],
            rows,
        ),
        "results.json:comparisons[*].{detection_mcnemar_exact,detection_p_holm,accuracy_difference_bootstrap.recall}",
    )


def block_cost(ns, ctx) -> tuple[str, str]:
    rows = []
    for c in ORDER:
        e = ns["cfg"][c]
        lat = (
            FORMATS["cis"](e["detection_latency_s_ci"].value)
            if "detection_latency_s_ci" in e
            else "no detections"
        )
        rows.append(
            [c, lat, FORMATS["cis"](e["cpu_s_ci"].value), FORMATS["cis"](e["wall_s_ci"].value)]
        )
    return (
        table(["Config", "Time to first detection", "CPU per run", "Wall time per run"], rows),
        "results.json:configurations.*.pooled_over_apps.{detection_latency_s,cpu_s,wall_s}",
    )


def block_overhead(ns, ctx) -> tuple[str, str]:
    rows = [
        [
            s["session"][:8],
            s["app"],
            str(s["repetitions"]),
            f"{s['median_overhead_ms']:.2f}",
            pct(s["median_overhead_ratio"]),
            f"{s['latency']['on']['median_ms']:.2f}",
            f"{s['latency']['off']['median_ms']:.2f}",
        ]
        for s in ctx["overhead"]["sessions"]
    ]
    return (
        table(
            [
                "Session",
                "App",
                "Repetitions",
                "Median overhead (ms)",
                "Median overhead (ratio)",
                "Median latency, collector on (ms)",
                "off (ms)",
            ],
            rows,
        ),
        "collector_overhead.json:sessions[*]",
    )


def block_coverage(ns, ctx) -> tuple[str, str]:
    zero = ctx["coverage"]["with_zero_located_operations"]
    rows = [
        [
            r["repo"],
            str(r["source_files"]),
            str(r["located_operations"]),
            str(r["text_lookalike_operations"]),
        ]
        for r in ctx["coverage"]["repositories"]
        if r["repo"] in zero
    ]
    return (
        table(
            [
                "Repository",
                "Source files loaded",
                "Prisma operations the analyzer located",
                "Text lookalike operations (heuristic)",
            ],
            rows,
        ),
        "realworld_coverage.json:repositories[with zero located operations]",
    )


def block_realworld_rules(ns, ctx) -> tuple[str, str]:
    s = ctx["summary"]
    rows = [[f"`{r}`", str(n)] for r, n in s["findings_by_rule"].items()]
    return table(["Rule", "Findings"], rows), "realworld_summary.json:findings_by_rule"


def block_labels(ns, ctx) -> tuple[str, str]:
    labels = ctx["labels"]
    if labels is None:
        text = (
            "> **Not yet measured.** The 1,221 findings have not been labelled, so no real-world precision, "
            "kappa, false-positive causes or index-divergence rate exists. This section reports only what "
            "can be said without labels. Nothing below stands in for those numbers."
        )
        return text, "labels_results.json does not exist"
    rows = []
    for rule, v in labels["per_rule"].items():
        w = v["wilson_95"]
        c = v["repo_cluster_bootstrap_95"]
        rows.append(
            [
                f"`{rule}`",
                f"{v['tp']} / {v['fp']} / {v['unsure']}",
                pct(v["precision"]) if v["precision"] is not None else "n/a",
                f"{pct(w['low'])} to {pct(w['high'])}" if w["low"] is not None else "n/a",
                f"{pct(c['low'])} to {pct(c['high'])}" if c["low"] is not None else "n/a",
            ]
        )
    return (
        table(
            [
                "Rule",
                "TP / FP / unsure",
                "Precision",
                "Wilson 95% CI",
                "Repository-cluster bootstrap 95% CI",
            ],
            rows,
        ),
        "labels_results.json:per_rule",
    )


BLOCKS = {
    "accuracy_table": block_accuracy,
    "type_table": block_types,
    "tests_table": block_tests,
    "cost_table": block_cost,
    "overhead_table": block_overhead,
    "coverage_table": block_coverage,
    "realworld_rules": block_realworld_rules,
    "labels": block_labels,
}

_PLACEHOLDER = re.compile(r"\{\{\s*([^{}|]+?)\s*(?:\|\s*(\w+)\s*)?\}\}")


def render(
    template: str, ns: dict[str, Any], ctx: dict[str, Any]
) -> tuple[str, list[tuple[str, str, str]]]:
    used: list[tuple[str, str, str]] = []

    def resolve(match: re.Match[str]) -> str:
        expression, fmt = match.group(1), match.group(2)
        if expression.startswith("block:"):
            name = expression.removeprefix("block:")
            if name not in BLOCKS:
                raise TemplateError(f"unknown block '{name}'")
            text, source = BLOCKS[name](ns, ctx)
            used.append((expression, "(table)", source))
            return text
        node: Any = ns
        for part in expression.split("."):
            if not isinstance(node, dict) or part not in node:
                raise TemplateError(f"no such number: {expression}")
            node = node[part]
        if not isinstance(node, Val):
            raise TemplateError(f"{expression} is a group, not a number")
        if node.value is None:
            raise TemplateError(f"{expression} is undefined in the results")
        text = FORMATS[fmt or "raw"](node.value)
        used.append((expression, text, node.source))
        return text

    return _PLACEHOLDER.sub(resolve, template), used


def appendix(used: list[tuple[str, str, str]]) -> str:
    seen: dict[str, tuple[str, str]] = {}
    for expression, text, source in used:
        seen.setdefault(expression, (text, source))
    lines = [
        "## Appendix: where every number comes from",
        "",
        "Generated with the chapter. Files are in `services/experiments/results/`; `results.json` is "
        "produced by `python -m experiments.analysis` and the others by `python -m experiments.writeup.collect`.",
        "",
        "| Placeholder | Value as printed | Source |",
        "|---|---|---|",
    ]
    lines += [f"| `{e}` | {t} | `{s}` |" for e, (t, s) in seen.items()]
    return "\n".join(lines)


def build(out: Path = DEFAULT_OUT) -> Path:
    results = load("results.json")
    if results is None:
        raise SystemExit("no results.json; run `python -m experiments.analysis` first")
    backtests = {a: load(f"anomaly_backtest_{a}.json") for a in ("ecommerce", "blog")}
    overhead, summary, coverage = (
        load("collector_overhead.json"),
        load("realworld_summary.json"),
        load("realworld_coverage.json"),
    )
    if None in (*backtests.values(), overhead, summary, coverage):
        raise SystemExit("missing inputs; run `python -m experiments.writeup.collect` first")
    labels = load("labels_results.json")
    ns = namespace(results, backtests, overhead, summary, coverage, labels)
    ctx = {"overhead": overhead, "summary": summary, "coverage": coverage, "labels": labels}
    body, used = render(TEMPLATE.read_text(), ns, ctx)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body.rstrip() + "\n\n" + appendix(used) + "\n")
    return out


def main() -> int:
    sys.stdout.write(f"{build()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
