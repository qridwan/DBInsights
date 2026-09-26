"""Anomaly detection over stored data-quality profiles.

    python -m analyzers.anomaly detect   --app ecommerce --baseline-label clean-seed \
        --current-label injected
    python -m analyzers.anomaly backtest --app ecommerce --label clean-seed

detect
    Learns each column's expected range from the windows of the baseline series and judges one
    window (default: the latest) of the current series against it. Prints Finding[] (the scorer's
    input), or with --report the analyses, including decreases, which are never findings.
    If --current-label is omitted the baseline series is judged against its own earlier windows.
backtest
    Walk-forward over a series known to be clean: how often does each detector raise an alarm
    that cannot be a real problem?

Profiles are read from the results database ($DBINSIGHT_RESULTS_DATABASE_URL, default the
compose `dbinsight` database); create them with `python -m analyzers.dataquality profile`.
"""

import argparse
import json
import os
import sys
from typing import Any

from ..dataquality.store import ProfileStore, parse_time
from .detectors import DETECTOR_NAMES, detectors_by_name
from .pipeline import backtest, detect_anomalies, to_findings
from .series import load_series


def _store(args: argparse.Namespace) -> ProfileStore:
    url = args.results_database_url or os.environ.get(
        "DBINSIGHT_RESULTS_DATABASE_URL",
        "postgresql://dbinsight:dbinsight@localhost:5432/dbinsight",
    )
    return ProfileStore(url)


def _print(value: Any) -> None:
    sys.stdout.write(json.dumps(value, indent=2, default=str) + "\n")


def _detectors(args: argparse.Namespace):
    return detectors_by_name([n for n in args.detectors.split(",") if n])


def _detect(args: argparse.Namespace) -> int:
    store = _store(args)
    baseline = load_series(store, args.app, args.baseline_label)
    if not baseline:
        raise SystemExit(
            f"no windowed profiles labelled {args.baseline_label!r} for app {args.app!r}"
        )
    same = args.current_label is None or args.current_label == args.baseline_label
    current = baseline if same else load_series(store, args.app, args.current_label)
    if not current:
        raise SystemExit(
            f"no windowed profiles labelled {args.current_label!r} for app {args.app!r}"
        )

    analyses = detect_anomalies(
        baseline,
        current,
        window_start=parse_time(args.window) if args.window else None,
        history_before_window=same,
        detectors=_detectors(args),
        vote=args.vote,
    )
    if args.report:
        flagged = [a for a in analyses if a.anomalous]
        _print(
            {
                "analyzed": len(analyses),
                "evaluated": sum(a.evaluated > 0 for a in analyses),
                "anomalous": len(flagged),
                "anomalies": [
                    {
                        "table": a.table,
                        "column": a.column,
                        "metric": a.metric,
                        "window_start": a.window.start,
                        "observation": a.observation,
                        "direction": a.direction,
                        "fired": a.fired,
                        "evaluated": a.evaluated,
                        "detections": [d.as_evidence() for d in a.detections],
                    }
                    for a in flagged
                ],
            }
        )
    else:
        _print(
            [
                f.model_dump(mode="json", by_alias=True, exclude_none=True)
                for f in to_findings(analyses)
            ]
        )
    return 0


def _backtest(args: argparse.Namespace) -> int:
    series = load_series(_store(args), args.app, args.label)
    if not series:
        raise SystemExit(f"no windowed profiles labelled {args.label!r} for app {args.app!r}")
    _print(backtest(series, detectors=_detectors(args), vote=args.vote))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m analyzers.anomaly",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def common(command: argparse.ArgumentParser) -> None:
        command.add_argument("--app", required=True)
        command.add_argument("--results-database-url")
        command.add_argument(
            "--detectors", default=",".join(DETECTOR_NAMES), help="comma-separated"
        )
        command.add_argument("--vote", choices=["any", "majority", "all"], default="majority")

    detect = commands.add_parser("detect")
    common(detect)
    detect.add_argument("--baseline-label", required=True)
    detect.add_argument("--current-label")
    detect.add_argument("--window", help="start date of the window to judge (default: latest)")
    detect.add_argument("--report", action="store_true")
    detect.set_defaults(run=_detect)

    back = commands.add_parser("backtest")
    common(back)
    back.add_argument("--label", required=True)
    back.set_defaults(run=_backtest)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
