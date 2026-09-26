"""Builds the labelling worksheet from stored findings. Never labels anything.

One row per finding, with the source around it and the relevant schema excerpt, and empty
columns for the human's label and rationale. Severity and confidence are deliberately left out
of the worksheet (they are in `worksheet_key.csv`, joined by `finding_id`) so a labeller judges
what the code does, not how sure the analyzer was.

The double-labelled sample (the rows a second person also labels, for Cohen's kappa) is drawn
here, before any labelling, with a fixed seed: at least 20% of the findings of every rule.
"""

import csv
import math
import random
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from .analyze_repos import clone_dir

CONTEXT_LINES = 10
DOUBLE_LABEL_FRACTION = 0.2
DOUBLE_LABEL_SEED = 20261002
#: Longest schema excerpt kept per row, in lines. Models this long are cut, and say so.
MAX_EXCERPT_LINES = 80

WORKSHEET_COLUMNS = [
    "finding_id",
    "repo",
    "commit",
    "rule_id",
    "title",
    "claim",
    "file",
    "line",
    "end_line",
    "source_context",
    "schema_excerpt",
    "double_label",
    "label",
    "fp_cause",
    "rationale",
    "label_2",
    "fp_cause_2",
    "rationale_2",
]
KEY_COLUMNS = ["finding_id", "severity", "confidence", "fingerprint"]


def show(repo: str, sha: str, path: str) -> str | None:
    done = subprocess.run(
        ["git", "-C", str(clone_dir(repo)), "show", f"{sha}:{path}"],
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    return done.stdout if done.returncode == 0 else None


def source_context(text: str | None, line: int, end_line: int | None) -> str:
    """The flagged lines and CONTEXT_LINES either side, numbered; flagged lines marked `>`."""
    if text is None:
        return "(source not available at this commit)"
    lines = text.splitlines()
    last = end_line or line
    first_shown = max(line - CONTEXT_LINES, 1)
    last_shown = min(last + CONTEXT_LINES, len(lines))
    width = len(str(last_shown))
    return "\n".join(
        f"{'>' if line <= n <= last else ' '} {n:>{width}} | {lines[n - 1]}"
        for n in range(first_shown, last_shown + 1)
    )


def models_named(evidence: list[dict[str, Any]]) -> list[str]:
    """Model names the finding's evidence mentions, in first-seen order."""
    names: list[str] = []
    for item in evidence:
        data = item.get("data") or {}
        for key in ("model", "models"):
            value = data.get(key)
            for name in value if isinstance(value, list) else [value]:
                if isinstance(name, str) and name not in names:
                    names.append(name)
    return names


def schema_excerpt(schema: str | None, models: list[str]) -> str:
    if schema is None:
        return "(schema not available at this commit)"
    blocks = []
    for name in models:
        match = re.search(rf"^model\s+{re.escape(name)}\s*\{{.*?^\}}", schema, re.M | re.S)
        if match is None:
            continue
        block = match.group(0).splitlines()
        if len(block) > MAX_EXCERPT_LINES:
            block = [
                *block[:MAX_EXCERPT_LINES],
                f"... ({len(block) - MAX_EXCERPT_LINES} more lines)",
            ]
        blocks.append("\n".join(block))
    return "\n\n".join(blocks) if blocks else "(no model named in this finding's evidence)"


def double_label_sample(findings: list[dict[str, Any]]) -> set[str]:
    """At least 20% of every rule's findings, drawn once with a fixed seed."""
    by_rule: dict[str, list[str]] = defaultdict(list)
    for finding in findings:
        by_rule[finding["rule_id"]].append(finding["finding_id"])
    rng = random.Random(DOUBLE_LABEL_SEED)
    chosen: set[str] = set()
    for rule in sorted(by_rule):
        ids = sorted(by_rule[rule])
        chosen.update(rng.sample(ids, math.ceil(DOUBLE_LABEL_FRACTION * len(ids))))
    return chosen


def build(
    findings: list[dict[str, Any]], repos: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    schema_of = {r["repo"]: r["schema_path"] for r in repos}
    schemas: dict[str, str | None] = {}
    sample = double_label_sample(findings)
    rows, key = [], []
    for f in findings:
        repo, sha = f["repo"], f["commit_sha"]
        if repo not in schemas:
            schemas[repo] = show(repo, sha, schema_of[repo])
        rows.append(
            {
                "finding_id": f["finding_id"],
                "repo": repo,
                "commit": sha,
                "rule_id": f["rule_id"],
                "title": f["title"],
                "claim": f["body"],
                "file": f["file"],
                "line": f["line"],
                "end_line": f["end_line"] or "",
                "source_context": source_context(
                    show(repo, sha, f["file"]), f["line"], f["end_line"]
                ),
                "schema_excerpt": schema_excerpt(schemas[repo], models_named(f["evidence"])),
                "double_label": "yes" if f["finding_id"] in sample else "no",
                **{column: "" for column in WORKSHEET_COLUMNS[12:]},
            }
        )
        key.append({k: f[k] for k in KEY_COLUMNS})
    return rows, key


def write(rows: list[dict[str, Any]], key: list[dict[str, Any]], out: Path) -> tuple[Path, Path]:
    out.mkdir(parents=True, exist_ok=True)
    worksheet, key_file = out / "worksheet.csv", out / "worksheet_key.csv"
    with worksheet.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=WORKSHEET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    with key_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=KEY_COLUMNS)
        writer.writeheader()
        writer.writerows(key)
    return worksheet, key_file
