"""Prepares everything the experiment needs, idempotently, so the whole thing runs from one command.

Every step first checks whether it is already done and only then acts, and none of them destroys
anything: databases are created, never dropped; the injection is idempotent SQL.

1. the docker compose stack is up (Postgres, both apps, the collector);
2. the TypeScript core is built;
3. the ground-truth problems are injected into the live databases;
4. a clean, never-injected copy of each app database exists (the seed is deterministic, so a fresh
   database equals the data before injection);
5. that clean copy is profiled over consecutive time windows: the baseline the data layer's
   expected ranges are learned from.
"""

import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg

from analyzers.dataquality import ProfileRun, ProfileStore, Window, profile_database
from analyzers.dataquality.models import utcnow
from analyzers.schema.actual import connect, read_actual_schema
from experiments.load.runner import wait_until_ready

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICES = REPO_ROOT / "services"
BASELINE_LABEL = "ablation-baseline"
#: The data layer's windows: consecutive 30-day windows ending where the seed data ends.
WINDOW_DAYS = 30
BASELINE_WINDOWS = 12
DATA_END = datetime(2026, 9, 1, tzinfo=UTC)
APP_PORTS = {"ecommerce": 3001, "blog": 3002}

Log = Callable[[str], None]


def windows() -> list[Window]:
    """The baseline windows, oldest first; the last one is the window the data layer judges."""
    step = timedelta(days=WINDOW_DAYS)
    return [
        Window(start=DATA_END - step * (i + 1), end=DATA_END - step * i)
        for i in reversed(range(BASELINE_WINDOWS))
    ]


def current_window() -> Window:
    return windows()[-1]


def credentials() -> tuple[str, str]:
    return os.environ.get("POSTGRES_USER", "dbinsight"), os.environ.get(
        "POSTGRES_PASSWORD", "dbinsight"
    )


def postgres_url(database: str) -> str:
    user, password = credentials()
    port = os.environ.get("POSTGRES_PORT", "5432")
    return f"postgresql://{user}:{password}@localhost:{port}/{database}"


def _run(*command: str, cwd: Path = REPO_ROOT) -> str:
    done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(
            f"`{' '.join(command)}` failed:\n{done.stderr.strip() or done.stdout.strip()}"
        )
    return done.stdout


def ensure_stack(apps: list[str], log: Log) -> None:
    _run("docker", "compose", "up", "-d")
    for app in apps:
        wait_until_ready(f"http://localhost:{APP_PORTS[app]}")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            with urlopen_health():
                break
        except OSError:
            time.sleep(1)
    log("stack: postgres, apps and collector are up")


def urlopen_health():  # a tiny context manager so the loop above reads plainly
    import urllib.request

    return urllib.request.urlopen("http://localhost:8700/health", timeout=5)


def ensure_core_built(log: Log) -> None:
    if not (REPO_ROOT / "packages" / "core" / "dist" / "cli.js").exists():
        log("core: building packages/core")
        _run("pnpm", "--filter", "@dbinsight/core", "build")
    log("core: built")


def ensure_injected(app: str, log: Log) -> None:
    _run(sys.executable, "-m", "experiments.groundtruth.inject", app, cwd=SERVICES)
    log(f"{app}: ground-truth problems injected (idempotent)")


def _database_exists(name: str) -> bool:
    with psycopg.connect(postgres_url("postgres"), autocommit=True) as conn:
        return (
            conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
            is not None
        )


def _has_tables(name: str) -> bool:
    with psycopg.connect(postgres_url(name), autocommit=True) as conn:
        row = conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchone()
        return bool(row and row[0] > 0)


def ensure_clean_copy(app: str, log: Log) -> str:
    """A fresh, seeded, never-injected database `<app>_clean`. Created if missing, never dropped."""
    name = f"{app}_clean"
    if not _database_exists(name):
        with psycopg.connect(postgres_url("postgres"), autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{name}"')
        log(f"{name}: created")
    if not _has_tables(name):
        user, password = credentials()
        log(f"{name}: migrating and seeding (deterministic)")
        _run(
            "docker",
            "compose",
            "run",
            "--rm",
            "--no-deps",
            "-e",
            f"DATABASE_URL=postgresql://{user}:{password}@postgres:5432/{name}",
            app,
            "sh",
            "-c",
            "pnpm db:migrate && pnpm db:seed",
        )
    return name


def profile_windows(app: str, database: str, label: str, log: Log) -> None:
    store = ProfileStore(postgres_url("dbinsight"))
    try:
        if len(store.runs(app, label)) >= BASELINE_WINDOWS:
            log(f"{app}: baseline {label!r} already profiled ({BASELINE_WINDOWS} windows)")
            return
        with connect(postgres_url(database)) as conn:
            schema = read_actual_schema(conn)
            for window in windows():
                profile = profile_database(conn, schema, window=window)
                store.save(
                    ProfileRun(
                        run_id=str(uuid.uuid4()),
                        app=app,
                        label=label,
                        profiled_at=utcnow(),
                        window=window,
                        max_categories=50,
                        time_columns=profile.time_columns,
                        skipped_tables=profile.skipped_tables,
                        tables=profile.tables,
                        columns=profile.columns,
                        categories=profile.categories,
                        integrity=[],
                    )
                )
        log(
            f"{app}: baseline {label!r} profiled over {BASELINE_WINDOWS} windows "
            f"of {WINDOW_DAYS} days"
        )
    finally:
        store.close()


def setup(apps: list[str], log: Log = print) -> None:
    ensure_stack(apps, log)
    ensure_core_built(log)
    for app in apps:
        ensure_injected(app, log)
        profile_windows(app, ensure_clean_copy(app, log), BASELINE_LABEL, log)
