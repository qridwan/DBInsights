"""Orchestrates load runs: sequence, execution, resource sampling, storage."""

import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

from experiments.groundtruth import load_manifest

from . import analysis
from .resources import ResourceSampler, read_counters
from .runner import execute, wait_until_ready
from .sequence import PlannedRequest, build_sequence, resolve_candidates
from .store import ResultsStore

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFESTS = REPO_ROOT / "services" / "experiments" / "groundtruth" / "manifests"
DEFAULT_PORTS = {"ecommerce": 3001, "blog": 3002}
#: Time for the collector's background flush (250 ms timer) to land before counting.
FLUSH_WAIT_S = 2.0


@dataclass(frozen=True)
class Config:
    app: str
    seed: int = 20260926
    repetitions: int = 3
    base_url: str = ""
    app_database_url: str = ""
    results_database_url: str = ""

    @classmethod
    def from_env(cls, app: str, **overrides: Any) -> "Config":
        user = os.environ.get("POSTGRES_USER", "dbinsight")
        password = os.environ.get("POSTGRES_PASSWORD", "dbinsight")
        pg = f"postgresql://{user}:{password}@localhost:{os.environ.get('POSTGRES_PORT', '5432')}"
        values = {
            "base_url": os.environ.get(
                f"DBINSIGHT_{app.upper()}_URL", f"http://localhost:{DEFAULT_PORTS.get(app, 3000)}"
            ),
            "app_database_url": os.environ.get(
                f"DBINSIGHT_{app.upper()}_DATABASE_URL", f"{pg}/{app}"
            ),
            "results_database_url": os.environ.get(
                "DBINSIGHT_RESULTS_DATABASE_URL",
                f"{pg}/{os.environ.get('POSTGRES_DB', 'dbinsight')}",
            ),
            **{k: v for k, v in overrides.items() if v is not None},
        }
        return cls(app=app, **values)


def git_commit() -> str | None:
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    if head.returncode != 0:
        return None
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True
    ).stdout
    return head.stdout.strip() + ("-dirty" if dirty.strip() else "")


def plan(config: Config) -> list[PlannedRequest]:
    manifest = load_manifest(MANIFESTS / f"{config.app}.json")
    with psycopg.connect(config.app_database_url, autocommit=True) as conn:
        conn.execute("SET default_transaction_read_only = on")

        def fetch(query: str) -> list[str]:
            return [row[0] for row in conn.execute(query).fetchall()]

        candidates = resolve_candidates(config.app, fetch, manifest)
    return build_sequence(manifest, candidates, seed=config.seed, repetitions=config.repetitions)


def collector_enabled_in_container(app: str) -> bool:
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", app, "printenv", "DBINSIGHT_COLLECTOR_URL"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(out.stdout.strip())


def set_collector(config: Config, enabled: bool) -> None:
    """Recreates the app container with the collector switched on or off."""
    env = dict(os.environ)
    if enabled:
        env.pop("DBINSIGHT_COLLECTOR_URL", None)  # compose default: the collector service
    else:
        env["DBINSIGHT_COLLECTOR_URL"] = ""
    subprocess.run(
        ["docker", "compose", "up", "-d", "--no-deps", config.app],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    wait_until_ready(config.base_url)
    if collector_enabled_in_container(config.app) is not enabled:
        raise RuntimeError(
            f"{config.app}: collector state did not switch to {'on' if enabled else 'off'}"
        )


def run_once(
    store: ResultsStore,
    config: Config,
    sequence: list[PlannedRequest],
    *,
    session_id: str,
    block: int,
    warmup: bool,
    collector_enabled: bool,
    sample_resources: bool = True,
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    store.start_run(
        run_id,
        session_id=session_id,
        app=config.app,
        block=block,
        warmup=warmup,
        collector_enabled=collector_enabled,
    )
    services = [config.app, "collector"] if sample_resources else []
    before = read_counters(str(REPO_ROOT), services)
    with ResourceSampler(str(REPO_ROOT), services) as sampler:
        results = execute(sequence, config.base_url)
    after = read_counters(str(REPO_ROOT), services)
    store.finish_run(run_id)
    store.add_requests(run_id, results)
    store.add_samples(run_id, sampler.samples)
    store.add_counters(run_id, "start", before)
    store.add_counters(run_id, "end", after)

    time.sleep(FLUSH_WAIT_S)
    run = next(r for r in store.runs(session_id) if str(r["run_id"]) == run_id)
    counts = store.runtime_counts(config.app, run["window_start"], run["window_end"])
    recorded = sum(c["operations"] for c in counts)
    store.set_verified(run_id, (recorded > 0) is collector_enabled)
    return {
        "run_id": run_id,
        "requests": len(results),
        "errors": sum(r["status"] != 200 for r in results),
        "recorded_operations": recorded,
        "counts": counts,
    }


def start_session(store: ResultsStore, config: Config, kind: str, **parameters: Any) -> str:
    session_id = str(uuid.uuid4())
    store.start_session(
        session_id,
        kind=kind,
        app=config.app,
        seed=config.seed,
        repetitions=config.repetitions,
        parameters={"base_url": config.base_url, **parameters},
        git_commit=git_commit(),
    )
    return session_id


def repeatability_session(
    store: ResultsStore, config: Config, runs: int
) -> tuple[str, dict[str, Any]]:
    """N identical runs with the collector on; reports query-count variance."""
    if not collector_enabled_in_container(config.app):
        raise RuntimeError(f"{config.app}: the collector is off; repeatability needs it on")
    sequence = plan(config)
    session_id = start_session(store, config, "repeatability", runs=runs)
    per_run = [
        run_once(
            store,
            config,
            sequence,
            session_id=session_id,
            block=i,
            warmup=False,
            collector_enabled=True,
        )["counts"]
        for i in range(runs)
    ]
    store.finish_session(session_id)
    return session_id, analysis.repeatability(per_run)


def overhead_session(
    store: ResultsStore, config: Config, cycles: int
) -> tuple[str, dict[str, Any]]:
    """Collector on vs off in ABBA cycles (on, off, off, on), so linear drift over the
    session cancels out. Each block recreates the app container, runs one unrecorded
    warm-up pass, then the measured run."""
    sequence = plan(config)
    warmup = sequence[: len(sequence) // config.repetitions]  # one pass over every endpoint
    order = [True, False, False, True] * cycles
    session_id = start_session(store, config, "overhead", cycles=cycles, design="ABBA", order=order)
    try:
        for block, enabled in enumerate(order):
            set_collector(config, enabled)
            run_once(
                store,
                config,
                warmup,
                session_id=session_id,
                block=block,
                warmup=True,
                collector_enabled=enabled,
                sample_resources=False,
            )
            run_once(
                store,
                config,
                sequence,
                session_id=session_id,
                block=block,
                warmup=False,
                collector_enabled=enabled,
            )
    finally:
        set_collector(config, True)
        store.finish_session(session_id)
    return session_id, analysis.overhead(
        store.requests(session_id), store.samples(session_id), store.counters(session_id)
    )
