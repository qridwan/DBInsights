"""Analyze a stored ablation experiment.

    python -m experiments.analysis                    # the latest experiment
    python -m experiments.analysis --experiment ID --out results/

Writes `results.json` (every number the thesis reports) and the figures. Reads only what the
ablation harness stored, so it can be re-run at any time and gives the same output.
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from experiments.ablation.experiment import MANIFESTS, _urls
from experiments.ablation.store import AblationStore

from .compare import compare, index_share, summarize
from .data import load_dataset
from .figures import all_figures

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "results"


def _clean(value: Any) -> Any:
    """Valid JSON: infinities and NaN become strings / null instead of the non-standard tokens."""
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    return value


def analyze(experiment_id: str | None, out: Path) -> dict[str, Any]:
    store = AblationStore(_urls("blog")[1])
    try:
        experiment_id = experiment_id or store.latest_experiment()
        if experiment_id is None:
            raise SystemExit("no experiments stored; run `python -m experiments.ablation run`")
        dataset = load_dataset(store, experiment_id, MANIFESTS)
    finally:
        store.close()

    results = {
        "experiment": experiment_id,
        "provenance": dataset.provenance,
        "configurations": summarize(dataset),
        "comparisons": compare(dataset),
        "h5_index_share": index_share(dataset),
        "notes": {
            "confidence_intervals": "Mean over repetitions with a 95% Student-t interval; a "
            "metric whose n_distinct is 1 had no variance across repetitions, so its interval is "
            "a point. problem_bootstrap gives the 95% percentile interval over the benchmark's "
            "problems, which is where accuracy uncertainty lives.",
            "tests": "See experiments/analysis/stats.py for why each test was chosen.",
        },
    }
    results = _clean(results)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    all_figures(results, out / "figures")
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m experiments.analysis", description=__doc__)
    parser.add_argument("--experiment")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    results = analyze(args.experiment, args.out)
    sys.stdout.write(f"{args.out / 'results.json'}\n")
    for test in results["comparisons"]:
        m = test["detection_mcnemar_exact"]
        sys.stdout.write(
            f"{test['id']:16} {test['first']}->{test['second']}  "
            f"+{m['only_second']} / -{m['only_first']}  p={m['p_value']:.4g}  {test['verdict']}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
