"""Gathers the inputs the results chapter needs that are not already in `results.json`.

    python -m experiments.writeup.collect

Writes, into experiments/results/:
  anomaly_backtest_<app>.json   false alarms of the anomaly detectors on clean history (RQ4)
  collector_overhead.json       runtime collector overhead, every stored 10+ repetition session (RQ5)
  realworld_summary.json        what M6 measured without labels: sample and findings
  realworld_coverage.json       per study repository: what the analyzer could see (M6)

Nothing is chosen by hand: the overhead sessions are every stored overhead session with at least
10 repetitions, and all are reported, so no single favourable run can stand in for the rest.
"""

import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from analyzers.core_bridge import CoreError, coverage
from experiments.ablation.experiment import _urls
from experiments.ablation.setup import BASELINE_LABEL

SERVICES = Path(__file__).resolve().parents[2]
RESULTS = SERVICES / "experiments" / "results"
REALWORLD = SERVICES / "experiments" / "realworld"
MIN_REPETITIONS = 10


def run_json(*command: str) -> dict:
    done = subprocess.run(
        [sys.executable, "-m", *command], cwd=SERVICES, capture_output=True, text=True, check=True
    )
    return json.loads(done.stdout)


def anomaly_backtests(apps: list[str]) -> None:
    for app in apps:
        result = run_json("analyzers.anomaly", "backtest", "--app", app, "--label", BASELINE_LABEL)
        (RESULTS / f"anomaly_backtest_{app}.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )


def collector_overhead() -> list[str]:
    with psycopg.connect(_urls("blog")[1], row_factory=dict_row) as conn:
        sessions = conn.execute(
            """SELECT session_id, app, repetitions, git_commit, started_at
               FROM experiments.load_session
               WHERE kind = 'overhead' AND repetitions >= %s ORDER BY started_at""",
            (MIN_REPETITIONS,),
        ).fetchall()
    out = []
    for s in sessions:
        report = run_json("experiments.load", "report", "--session", str(s["session_id"]))
        out.append(
            {
                "session": str(s["session_id"]),
                "app": s["app"],
                "repetitions": s["repetitions"],
                "git_commit": s["git_commit"],
                "started_at": s["started_at"].isoformat(),
                "median_overhead_ms": report["median_overhead_ms"],
                "median_overhead_ratio": report["median_overhead_ratio"],
                "p95_overhead_ms": report["p95_overhead_ms"],
                "latency": report["latency"],
                "cost": report["cost"],
            }
        )
    (RESULTS / "collector_overhead.json").write_text(
        json.dumps(
            {
                "rule": f"every stored overhead session with >= {MIN_REPETITIONS} repetitions",
                "sessions": out,
            },
            indent=2,
        )
        + "\n"
    )
    return [o["session"] for o in out]


def realworld_summary() -> None:
    candidates = json.loads((REALWORLD / "candidates.json").read_text())
    from experiments.realworld.store import RealWorldStore

    store = RealWorldStore(_urls("blog")[1])
    try:
        analysis = store.latest()
        if analysis is None:
            return
        repos, findings = store.repos(analysis), store.findings(analysis)
    finally:
        store.close()
    summary = {
        "selection_date": candidates["selection_date"],
        "pool_size": candidates["pool_size"],
        "evaluated": len(candidates["candidates"]),
        "eligible": candidates["eligible"],
        "study_repositories": len(candidates["study_set"]),
        "excluded_by_first_failing_test": candidates["excluded_by_first_failing_test"],
        "repositories_analyzed_ok": sum(r["status"] == "ok" for r in repos),
        "repositories_failed": sum(r["status"] != "ok" for r in repos),
        "repositories_with_zero_findings": sum(r["finding_count"] == 0 for r in repos),
        "findings": len(findings),
        "findings_by_rule": dict(sorted(Counter(f["rule_id"] for f in findings).items())),
        "findings_by_confidence": dict(sorted(Counter(f["confidence"] for f in findings).items())),
    }
    (RESULTS / "realworld_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )


#: A crude, analyzer-independent yardstick: text that looks like a Prisma model operation, counted
#: in TypeScript files that mention prisma or a db handle. It is NOT analysis (it cannot tell a
#: real client from a lookalike); it exists only to notice when the analyzer located nothing in a
#: project that plainly issues such calls.
_LOOKS_LIKE_OPERATION = re.compile(
    r"\.(findMany|findFirst|findUnique|findFirstOrThrow|findUniqueOrThrow|create|createMany|update"
    r"|updateMany|upsert|delete|deleteMany|count|aggregate|groupBy)\("
)
_MENTIONS_DB = re.compile(r"prisma|Prisma|\bdb\b")
_SKIP = {"node_modules", ".git", "generated", "dist", ".next", "build"}


def text_count(root: Path) -> int:
    total = 0
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _SKIP]
        for name in files:
            if name.endswith((".ts", ".tsx")) and not name.endswith(".d.ts"):
                text = (Path(base) / name).read_text(errors="ignore")
                if _MENTIONS_DB.search(text):
                    total += len(_LOOKS_LIKE_OPERATION.findall(text))
    return total


def realworld_coverage() -> None:
    study = json.loads((REALWORLD / "candidates.json").read_text())
    by_repo = {c["repo"]: c for c in study["candidates"]}
    rows = []
    for repo in study["study_set"]:
        candidate = by_repo[repo]
        clone = REALWORLD / "work" / "clones" / repo.replace("/", "__")
        row = {"repo": repo, "commit": candidate["last_commit_sha"]}
        try:
            seen = coverage(clone, clone / candidate["schema_path"], timeout=600)
            row |= {
                "source_files": seen["sourceFiles"],
                "located_operations": seen["ormOperations"],
                "text_lookalike_operations": text_count(clone),
            }
        except (CoreError, OSError) as error:
            row["error"] = str(error)[:200]
        rows.append(row)
    zero = [r for r in rows if r.get("located_operations") == 0]
    (RESULTS / "realworld_coverage.json").write_text(
        json.dumps(
            {
                "note": "text_lookalike_operations is a heuristic yardstick, not analysis",
                "repositories": rows,
                "with_zero_located_operations": [r["repo"] for r in zero],
                "zero_located_but_text_lookalikes_ge_10": [
                    r["repo"] for r in zero if r["text_lookalike_operations"] >= 10
                ],
            },
            indent=2,
        )
        + "\n"
    )


def main() -> int:
    RESULTS.mkdir(exist_ok=True)
    anomaly_backtests(["ecommerce", "blog"])
    sessions = collector_overhead()
    realworld_summary()
    realworld_coverage()
    sys.stderr.write(
        f"backtests for 2 apps, {len(sessions)} overhead sessions, real-world summary\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
