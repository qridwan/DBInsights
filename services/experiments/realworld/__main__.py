"""Real-world validation.

python -m experiments.realworld select              # M6.1: choose repositories (PROTOCOL.md)
python -m experiments.realworld analyze             # M6.2: analyze the study set at pinned commits
python -m experiments.realworld worksheet           # M6.2: write the labelling worksheet
python -m experiments.realworld show                # per-repository results of the latest analysis
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

from . import analyze_repos, select_repos, worksheet
from .store import RealWorldStore

DEFAULT_OUT = Path(__file__).resolve().parent / "labelling"


def _store() -> RealWorldStore:
    from experiments.ablation.experiment import _urls

    return RealWorldStore(_urls("blog")[1])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m experiments.realworld", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("select")
    run = commands.add_parser("analyze")
    run.add_argument("--timeout", type=float, default=analyze_repos.DEFAULT_TIMEOUT_S)
    run.add_argument("--only", help="comma-separated owner/name list (a subset of the study set)")
    sheet = commands.add_parser("worksheet")
    sheet.add_argument("--analysis")
    sheet.add_argument("--out", type=Path, default=DEFAULT_OUT)
    lab = commands.add_parser("labels")
    lab.add_argument("--worksheet", type=Path, required=True)
    lab.add_argument("--key", type=Path, default=DEFAULT_OUT / "worksheet_key.csv")
    lab.add_argument("--out", type=Path, default=DEFAULT_OUT / "labels_results.json")
    lab.add_argument(
        "--allow-partial", action="store_true", help="some rows are unlabelled (reported)"
    )
    show = commands.add_parser("show")
    show.add_argument("--analysis")
    args = parser.parse_args(argv)

    if args.command == "select":
        return select_repos.main([])
    if args.command == "analyze":
        only = args.only.split(",") if args.only else None
        analysis = analyze_repos.run(args.timeout, only, log=lambda m: sys.stderr.write(m + "\n"))
        print(analysis)
        return 0

    if args.command == "labels":
        import json

        from . import labels

        try:
            result = labels.analyze(args.worksheet, args.key, args.allow_partial)
        except labels.LabelError as error:
            sys.stderr.write(f"the worksheet does not follow LABELLING.md:\n{error}\n")
            return 1
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(args.out)
        return 0

    store = _store()
    try:
        analysis = args.analysis or store.latest()
        if analysis is None:
            sys.stderr.write("no analysis stored; run `analyze` first\n")
            return 1
        repos, findings = store.repos(analysis), store.findings(analysis)
        if args.command == "show":
            for r in repos:
                print(
                    f"{r['repo']:45} {r['status']:6} {r['finding_count']:4} findings "
                    f"{r['duration_s']:7.1f}s"
                )
            print(dict(Counter(f["rule_id"] for f in findings)))
            return 0
        rows, key = worksheet.build(findings, repos)
        paths = worksheet.write(rows, key, args.out)
        print(f"{len(rows)} findings -> {paths[0]}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
