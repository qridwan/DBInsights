"""Matplotlib figures for the ablation results. Reads only the results dictionary."""

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # no display needed: this runs in a container or over ssh

import matplotlib.pyplot as plt  # noqa: E402

ORDER = ["A", "A-log", "B1", "B2", "C1", "C2", "C3"]
COLORS = {"precision": "#4c72b0", "recall": "#dd8452", "f1": "#55a868"}


def _configs(results: dict[str, Any]) -> list[str]:
    return [c for c in ORDER if c in results["configurations"]]


def _save(fig: Any, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def accuracy(results: dict[str, Any], out: Path) -> Path:
    """Precision, recall and F1 per configuration; whiskers are 95% bootstrap intervals over
    the benchmark's problems (repetitions add no variance to accuracy: see stats.py)."""
    configs = _configs(results)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    width = 0.26
    for offset, metric in enumerate(("precision", "recall", "f1")):
        heights, lows, highs = [], [], []
        for config in configs:
            summary = results["configurations"][config]
            mean = summary["pooled_over_apps"][metric]["mean"] or 0.0
            boot = summary["problem_bootstrap"][metric]
            heights.append(mean)
            lows.append(max(mean - (boot["low"] if boot["low"] is not None else mean), 0))
            highs.append(max((boot["high"] if boot["high"] is not None else mean) - mean, 0))
        xs = [i + (offset - 1) * width for i in range(len(configs))]
        ax.bar(
            xs, heights, width, yerr=[lows, highs], capsize=2, label=metric, color=COLORS[metric]
        )
    ax.set_xticks(range(len(configs)), configs)
    ax.set_ylim(0, 1.25)
    ax.set_ylabel("score (both apps pooled)")
    ax.set_title("Accuracy by configuration (95% bootstrap CI over problems)")
    ax.legend(ncols=3, loc="upper left")
    return _save(fig, out / "accuracy_by_configuration.png")


def per_problem_type(results: dict[str, Any], out: Path) -> Path:
    """Recall of every configuration on every problem type."""
    configs = _configs(results)
    types = sorted({t for c in configs for t in results["configurations"][c]["per_problem_type"]})
    grid = [
        [
            results["configurations"][c]["per_problem_type"]
            .get(t, {})
            .get("recall", {})
            .get("mean")
            for c in configs
        ]
        for t in types
    ]
    fig, ax = plt.subplots(figsize=(1.0 * len(configs) + 4, 0.45 * len(types) + 1.8))
    image = ax.imshow(
        [[v if v is not None else float("nan") for v in row] for row in grid],
        vmin=0,
        vmax=1,
        cmap="YlGn",
        aspect="auto",
    )
    ax.set_xticks(range(len(configs)), configs)
    ax.set_yticks(range(len(types)), types)
    for y, row in enumerate(grid):
        for x, value in enumerate(row):
            ax.text(
                x,
                y,
                "n/a" if value is None else f"{value:.2f}",
                ha="center",
                va="center",
                fontsize=8,
            )
    fig.colorbar(image, ax=ax, label="recall")
    ax.set_title("Recall by problem type")
    return _save(fig, out / "recall_by_problem_type.png")


def cost(results: dict[str, Any], out: Path) -> Path:
    """Detection latency and CPU overhead per configuration; whiskers are 95% t intervals over
    repetitions, which is where timing varies."""
    configs = _configs(results)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, metric, label in (
        (axes[0], "detection_latency_s", "seconds to first detection"),
        (axes[1], "cpu_s", "CPU seconds per run (both apps)"),
    ):
        means, errors = [], []
        for config in configs:
            ci = results["configurations"][config]["pooled_over_apps"][metric]
            mean = ci["mean"] or 0.0
            means.append(mean)
            errors.append([mean - (ci["low"] or mean), (ci["high"] or mean) - mean])
        ax.bar(
            range(len(configs)),
            means,
            yerr=list(zip(*errors, strict=True)),
            capsize=2,
            color="#8172b3",
        )
        ax.set_xticks(range(len(configs)), configs)
        ax.set_ylabel(label)
    axes[0].set_title("Detection latency")
    axes[1].set_title("Analysis overhead")
    return _save(fig, out / "latency_and_overhead.png")


def paired_detection(results: dict[str, Any], out: Path) -> Path:
    """For each named comparison, the problems found by only one side: the McNemar evidence."""
    tests = results["comparisons"]
    fig, ax = plt.subplots(figsize=(8, 0.9 * len(tests) + 1.5))
    for row, test in enumerate(tests):
        m = test["detection_mcnemar_exact"]
        ax.barh(row, -m["only_first"], color="#c44e52")
        ax.barh(row, m["only_second"], color="#55a868")
        p = test["detection_p_holm"]
        note = f"p (Holm) = {p:.3g}" if p is not None else "uncorrected"
        ax.text(
            1.0,
            row,
            f"{test['first']} vs {test['second']}\n{note}",
            transform=ax.get_yaxis_transform(),
            ha="right",
            va="center",
            fontsize=8,
        )
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlim(right=1.45 * max(1, *(t["detection_mcnemar_exact"]["only_second"] for t in tests)))
    ax.set_yticks(range(len(tests)), [t["hypothesis"] for t in tests])
    ax.set_xlabel("problems detected by only one configuration  (left: first, right: second)")
    ax.set_title("Where the configurations disagree")
    return _save(fig, out / "paired_detection.png")


def all_figures(results: dict[str, Any], out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    return [
        accuracy(results, out),
        per_problem_type(results, out),
        cost(results, out),
        paired_detection(results, out),
    ]
