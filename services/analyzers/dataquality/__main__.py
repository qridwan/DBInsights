"""Data-quality profiler.

    python -m analyzers.dataquality profile --app ecommerce [window options] [--schema PRISMA]
    python -m analyzers.dataquality history --app ecommerce --table Customer --column phone
    python -m analyzers.dataquality integrity --app ecommerce --schema PRISMA

profile
    Snapshot (default): profiles every table whole and, with --schema, checks the declared
    relations. Windowed: --window-start/--window-end for one window, or
    --windows N --window-days D --end DATE for N consecutive windows ending at DATE.
    Each profile is stored as its own run; history accumulates.
history
    A column's stored windowed profiles, oldest first.
integrity
    Live referential-integrity check; prints Finding[] (the scorer's input), or the raw
    checks with --report. Stores nothing.

Databases: --database-url (the app, read-only; default $DBINSIGHT_<APP>_DATABASE_URL or the
compose database) and --results-database-url ($DBINSIGHT_RESULTS_DATABASE_URL, default the
compose `dbinsight` database).
"""

import argparse
import json
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from ..schema.actual import connect, read_actual_schema
from ..schema.declared import load_declared_schema
from .integrity import check_integrity, to_findings
from .models import ProfileRun, Window, utcnow
from .profile import DEFAULT_MAX_CATEGORIES, profile_database
from .store import ProfileStore, parse_time


def _urls(args: argparse.Namespace) -> tuple[str, str]:
    user = os.environ.get("POSTGRES_USER", "dbinsight")
    password = os.environ.get("POSTGRES_PASSWORD", "dbinsight")
    base = f"postgresql://{user}:{password}@localhost:{os.environ.get('POSTGRES_PORT', '5432')}"
    app_url = (
        args.database_url
        or os.environ.get(f"DBINSIGHT_{args.app.upper()}_DATABASE_URL")
        or f"{base}/{args.app}"
    )
    results = (
        args.results_database_url
        or os.environ.get("DBINSIGHT_RESULTS_DATABASE_URL")
        or f"{base}/dbinsight"
    )
    return app_url, results


def _windows(args: argparse.Namespace) -> list[Window | None]:
    if args.windows:
        if not args.end:
            raise SystemExit("--windows needs --end")
        end = parse_time(args.end)
        step = timedelta(days=args.window_days)
        return [
            Window(start=end - step * (i + 1), end=end - step * i)
            for i in reversed(range(args.windows))
        ]
    if args.window_start or args.window_end:
        if not (args.window_start and args.window_end):
            raise SystemExit("--window-start and --window-end go together")
        return [Window(start=parse_time(args.window_start), end=parse_time(args.window_end))]
    return [None]


def _time_columns(pairs: list[str]) -> dict[str, str]:
    overrides = {}
    for pair in pairs:
        table, _, column = pair.partition("=")
        if not column:
            raise SystemExit(f"--time-column expects TABLE=COLUMN, got {pair!r}")
        overrides[table] = column
    return overrides


def _print(value: Any) -> None:
    sys.stdout.write(json.dumps(value, indent=2, default=str) + "\n")


def _profile(args: argparse.Namespace) -> int:
    windows = _windows(args)
    if args.schema and windows != [None]:
        raise SystemExit(
            "--schema (integrity) applies to snapshot profiles; drop the window options"
        )
    app_url, results_url = _urls(args)
    declared = load_declared_schema(args.schema) if args.schema else None
    store = ProfileStore(results_url)
    summaries = []
    with connect(app_url) as conn:
        actual = read_actual_schema(conn, args.db_schema)
        for window in windows:
            profile = profile_database(
                conn,
                actual,
                window=window,
                time_columns=_time_columns(args.time_column),
                max_categories=args.max_categories,
            )
            integrity, integrity_skipped = (
                check_integrity(conn, declared, actual) if declared else ([], {})
            )
            run = ProfileRun(
                run_id=str(uuid.uuid4()),
                app=args.app,
                label=args.label,
                profiled_at=utcnow(),
                window=window,
                max_categories=args.max_categories,
                time_columns=profile.time_columns,
                skipped_tables={**profile.skipped_tables, **integrity_skipped},
                tables=profile.tables,
                columns=profile.columns,
                categories=profile.categories,
                integrity=integrity,
            )
            store.save(run)
            summaries.append(run.summary())
    _print(summaries)
    return 0


def _history(args: argparse.Namespace) -> int:
    _, results_url = _urls(args)
    store = ProfileStore(results_url)
    _print(
        store.category_history(args.app, args.table, args.column, label=args.label)
        if args.categories
        else store.column_history(args.app, args.table, args.column, label=args.label)
    )
    return 0


def _integrity(args: argparse.Namespace) -> int:
    app_url, _ = _urls(args)
    declared = load_declared_schema(args.schema)
    with connect(app_url) as conn:
        checks, skipped = check_integrity(conn, declared, read_actual_schema(conn, args.db_schema))
    if args.report:
        _print({"checks": [c.model_dump(mode="json") for c in checks], "skipped": skipped})
    else:
        findings = to_findings(checks, args.schema_file)
        _print([f.model_dump(mode="json", by_alias=True, exclude_none=True) for f in findings])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m analyzers.dataquality",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def common(command: argparse.ArgumentParser) -> None:
        command.add_argument("--app", required=True)
        command.add_argument("--database-url")
        command.add_argument("--results-database-url")
        command.add_argument("--db-schema", default="public")

    profile = commands.add_parser("profile")
    common(profile)
    profile.add_argument("--label", help="tag for this series of profiles, e.g. clean-seed")
    profile.add_argument("--window-start")
    profile.add_argument("--window-end")
    profile.add_argument("--windows", type=int, help="number of consecutive windows")
    profile.add_argument("--window-days", type=int, default=30)
    profile.add_argument("--end", help="end of the last window (with --windows)")
    profile.add_argument("--max-categories", type=int, default=DEFAULT_MAX_CATEGORIES)
    profile.add_argument("--time-column", action="append", default=[], metavar="TABLE=COLUMN")
    profile.add_argument(
        "--schema", type=Path, help="schema.prisma: enables integrity checks (snapshot only)"
    )
    profile.set_defaults(run=_profile)

    history = commands.add_parser("history")
    common(history)
    history.add_argument("--table", required=True)
    history.add_argument("--column", required=True)
    history.add_argument("--label")
    history.add_argument(
        "--categories", action="store_true", help="value distributions instead of rates"
    )
    history.set_defaults(run=_history)

    integrity = commands.add_parser("integrity")
    common(integrity)
    integrity.add_argument("--schema", type=Path, required=True, help="schema.prisma")
    integrity.add_argument(
        "--schema-file", default="prisma/schema.prisma", help="how findings name the schema file"
    )
    integrity.add_argument("--report", action="store_true", help="raw checks instead of findings")
    integrity.set_defaults(run=_integrity)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
