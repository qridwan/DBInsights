"""Runs the ablation: every configuration, against both apps, for N repetitions."""

import uuid
from collections.abc import Mapping, Sequence

from analyzers.anomaly import load_series
from analyzers.dataquality import ProfileStore
from analyzers.schema import load_declared_schema, read_actual_schema
from analyzers.schema.actual import connect
from experiments.groundtruth import load_manifest
from experiments.load.harness import Config as LoadConfig

from . import setup as environment
from .layers import CONFIGURATIONS, Configuration, Layer
from .pipeline import Provider, RunContext, run_configuration
from .providers import LOAD_REPETITIONS, default_providers
from .store import AblationStore
from .universe import build_universe

REPO_ROOT = environment.REPO_ROOT
MANIFESTS = REPO_ROOT / "services" / "experiments" / "groundtruth" / "manifests"
DEFAULT_SEED = 20260928
DEFAULT_REPETITIONS = 10


def _urls(app: str) -> tuple[str, str]:
    config = LoadConfig.from_env(app)
    return config.app_database_url, config.results_database_url


def context_for(app: str, repetition: int, seed: int) -> RunContext:
    app_dir = REPO_ROOT / "apps" / app
    app_url, results_url = _urls(app)
    return RunContext(
        app=app,
        repetition=repetition,
        seed=seed + repetition,
        app_dir=app_dir,
        schema_path=app_dir / "prisma" / "schema.prisma",
        app_database_url=app_url,
        results_database_url=results_url,
        baseline_label=environment.BASELINE_LABEL,
        window=environment.current_window(),
    )


def compute_universe(app: str) -> dict[str, int]:
    ctx = context_for(app, 0, 0)
    store = ProfileStore(ctx.results_database_url)
    try:
        baseline = load_series(store, app, ctx.baseline_label)
    finally:
        store.close()
    with connect(ctx.app_database_url) as conn:
        actual = read_actual_schema(conn)
    return build_universe(ctx.app_dir, load_declared_schema(ctx.schema_path), actual, baseline)


def run_experiment(
    *,
    apps: Sequence[str],
    configs: Sequence[str],
    repetitions: int = DEFAULT_REPETITIONS,
    seed: int = DEFAULT_SEED,
    providers: Mapping[Layer, Provider] | None = None,
    skip_setup: bool = False,
    log=print,
) -> str:
    chosen: list[Configuration] = [CONFIGURATIONS[name] for name in configs]
    if not skip_setup:
        environment.setup(list(apps), log)
    providers = providers or default_providers()

    universes = {app: compute_universe(app) for app in apps}
    manifests = {app: load_manifest(MANIFESTS / f"{app}.json") for app in apps}
    _, results_url = _urls(apps[0])
    store = AblationStore(results_url)
    experiment_id = str(uuid.uuid4())
    store.start_experiment(
        experiment_id,
        repetitions=repetitions,
        seed=seed,
        apps=list(apps),
        configurations={c.name: c for c in chosen},
        universe=universes,
        parameters={
            "baseline_label": environment.BASELINE_LABEL,
            "window_days": environment.WINDOW_DAYS,
            "baseline_windows": environment.BASELINE_WINDOWS,
            "data_end": environment.DATA_END.isoformat(),
            "load_repetitions": LOAD_REPETITIONS,
            "seed_per_repetition": "seed + repetition, drives the runtime workload only",
        },
    )
    log(
        f"experiment {experiment_id}: {len(chosen)} configurations x {len(apps)} apps "
        f"x {repetitions} repetitions"
    )
    try:
        for repetition in range(1, repetitions + 1):
            # Rotate the order each repetition so no configuration always runs first (timing drift).
            offset = repetition % len(chosen)
            for app in apps:
                for config in chosen[offset:] + chosen[:offset]:
                    result = run_configuration(
                        config,
                        context_for(app, repetition, seed),
                        manifests[app],
                        providers,
                        universes[app],
                    )
                    store.add_run(
                        experiment_id, str(uuid.uuid4()), result, sensitivity=config.sensitivity
                    )
                    log(
                        f"  rep {repetition:>2} {app:<9} {config.name:<6} {result.wall_s:6.2f}s "
                        f"{len(result.findings):>3} findings  TP {result.report.aggregate.tp:>2} "
                        f"FP {result.report.aggregate.fp:>2} FN {result.report.aggregate.fn:>2}"
                    )
        store.finish_experiment(experiment_id)
    finally:
        store.close()
    return experiment_id
