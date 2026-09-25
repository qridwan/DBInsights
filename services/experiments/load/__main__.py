"""Load harness.

    python -m experiments.load plan         --app ecommerce [--seed N] [--repetitions N]
    python -m experiments.load run          --app ecommerce [--repetitions N]
    python -m experiments.load repeatability --app ecommerce --runs 5
    python -m experiments.load overhead     --app ecommerce --cycles 2
    python -m experiments.load report       --session <uuid>

Requires the docker compose stack. Results go to the results database
($DBINSIGHT_RESULTS_DATABASE_URL, default the compose `dbinsight` database).
"""

import argparse
import json
import sys

from . import analysis
from .harness import (
    Config,
    collector_enabled_in_container,
    overhead_session,
    plan,
    repeatability_session,
    run_once,
    start_session,
)
from .store import ResultsStore


def _print(value: object) -> None:
    sys.stdout.write(json.dumps(value, indent=2, default=str) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m experiments.load",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "run", "repeatability", "overhead"):
        command = commands.add_parser(name)
        command.add_argument("--app", required=True, choices=["ecommerce", "blog"])
        command.add_argument("--seed", type=int)
        command.add_argument("--repetitions", type=int)
        if name == "repeatability":
            command.add_argument("--runs", type=int, default=5)
        if name == "overhead":
            command.add_argument(
                "--cycles", type=int, default=2, help="ABBA cycles (4 blocks each)"
            )
    report = commands.add_parser("report")
    report.add_argument("--session", required=True)
    args = parser.parse_args(argv)

    if args.command == "report":
        store = ResultsStore(Config.from_env("ecommerce").results_database_url)
        runs = store.runs(args.session)
        kind = store.conn.execute(
            "SELECT kind FROM experiments.load_session WHERE session_id = %s", (args.session,)
        ).fetchone()["kind"]
        if kind == "overhead":
            _print(
                analysis.overhead(
                    store.requests(args.session),
                    store.samples(args.session),
                    store.counters(args.session),
                )
            )
        else:
            per_run = [
                store.runtime_counts(r["app"], r["window_start"], r["window_end"])
                for r in runs
                if not r["warmup"]
            ]
            _print(analysis.repeatability(per_run))
        return 0

    config = Config.from_env(args.app, seed=args.seed, repetitions=args.repetitions)
    if args.command == "plan":
        _print([request.__dict__ for request in plan(config)])
        return 0

    store = ResultsStore(config.results_database_url)
    if args.command == "run":
        session_id = start_session(store, config, "run")
        enabled = collector_enabled_in_container(config.app)
        result = run_once(
            store,
            config,
            plan(config),
            session_id=session_id,
            block=0,
            warmup=False,
            collector_enabled=enabled,
        )
        store.finish_session(session_id)
        _print({"session": session_id, **{k: v for k, v in result.items() if k != "counts"}})
    elif args.command == "repeatability":
        session_id, summary = repeatability_session(store, config, args.runs)
        _print({"session": session_id, **summary})
    else:
        session_id, summary = overhead_session(store, config, args.cycles)
        _print({"session": session_id, **summary})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
