"""The ablation experiment.

    python -m experiments.ablation run      # setup, then all configurations x both apps x 10 reps
    python -m experiments.ablation run --repetitions 3 --configs B1,B2 --apps blog
    python -m experiments.ablation setup               # only prepare the environment (idempotent)
    python -m experiments.ablation list                # the configurations and their layers
    python -m experiments.ablation show [--experiment ID]

`run` is the one command that reproduces the experiment from a working docker compose stack: it
prepares whatever is missing (nothing is ever dropped), runs every repetition, and stores raw
rows in the `ablation` schema of the results database. Aggregation happens later, at analysis time.
"""

import argparse
import sys
from collections import defaultdict

from . import setup as environment
from .experiment import DEFAULT_REPETITIONS, DEFAULT_SEED, run_experiment
from .layers import ABLATION, CONFIGURATIONS, SENSITIVITY, Layer
from .store import AblationStore

APPS = ("ecommerce", "blog")


def _log(message: str) -> None:
    sys.stderr.write(message + "\n")


def _list() -> int:
    layers = [layer for layer in Layer]
    print(f"{'config':8}" + "".join(f"{layer.value:>11}" for layer in layers) + "  description")
    for name, config in CONFIGURATIONS.items():
        marks = "".join(f"{'yes' if config.uses(layer) else '-':>11}" for layer in layers)
        note = "  [sensitivity arm]" if config.sensitivity else ""
        print(f"{name:8}{marks}  {config.description}{note}")
    return 0


def _show(experiment: str | None) -> int:
    from .experiment import _urls

    store = AblationStore(_urls(APPS[0])[1])
    experiment = experiment or store.latest_experiment()
    if experiment is None:
        print("no experiments yet")
        return 1
    rows = store.results(experiment)
    totals: dict[tuple[str, str, int], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        for key in ("tp", "fp", "fn"):
            totals[(row["config"], row["app"], row["repetition"])][key] += row[key]
    per_config: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    for (config, _app, _rep), t in totals.items():
        per_config[config].append((t["tp"], t["fp"], t["fn"]))
    print(f"experiment {experiment}: {len(store.runs(experiment))} runs")
    print(
        f"{'config':8} {'runs':>5} {'mean TP':>8} {'mean FP':>8} {'mean FN':>8}"
        "   (summed over both apps, per repetition)"
    )
    for config, values in sorted(per_config.items()):
        n = len(values)
        print(
            f"{config:8} {n:5} {sum(v[0] for v in values) / n:8.1f} "
            f"{sum(v[1] for v in values) / n:8.1f} "
            f"{sum(v[2] for v in values) / n:8.1f}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m experiments.ablation",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    run.add_argument("--seed", type=int, default=DEFAULT_SEED)
    run.add_argument("--apps", default=",".join(APPS))
    run.add_argument(
        "--configs",
        help="comma-separated; default: the six configurations plus the sensitivity arm",
    )
    run.add_argument(
        "--no-sensitivity", action="store_true", help="only the six ablation configurations"
    )
    run.add_argument("--skip-setup", action="store_true")
    setup_parser = commands.add_parser("setup")
    setup_parser.add_argument("--apps", default=",".join(APPS))
    commands.add_parser("list")
    show = commands.add_parser("show")
    show.add_argument("--experiment")
    args = parser.parse_args(argv)

    if args.command == "list":
        return _list()
    if args.command == "show":
        return _show(args.experiment)
    if args.command == "setup":
        environment.setup(args.apps.split(","), _log)
        return 0
    configs = (
        args.configs.split(",")
        if args.configs
        else list(ABLATION) + ([] if args.no_sensitivity else list(SENSITIVITY))
    )
    unknown = [c for c in configs if c not in CONFIGURATIONS]
    if unknown:
        parser.error(f"unknown configuration(s) {unknown}; see `list`")
    experiment = run_experiment(
        apps=args.apps.split(","),
        configs=configs,
        repetitions=args.repetitions,
        seed=args.seed,
        skip_setup=args.skip_setup,
        log=_log,
    )
    print(experiment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
