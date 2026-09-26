"""Select repositories for the real-world validation study, exactly as PROTOCOL.md describes.

    python -m experiments.realworld.select_repos            # search, decide, write outputs
    python -m experiments.realworld.select_repos --resume   # reuse cached per-repo decisions

The analyzer is never run here: no decision depends on what it would find.
"""

import argparse
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "PROTOCOL.md"
WORK = HERE / "work"  # clones and per-repo decision cache; not committed
SELECTION_DATE = datetime(2026, 9, 26, tzinfo=UTC)
ACTIVE_SINCE = SELECTION_DATE - timedelta(days=365)
STUDY_SEED = 20261001
STUDY_SIZE = 30
TARGET_ELIGIBLE = 40
MIN_ELIGIBLE = 20
LICENSE_QUALIFIERS = [
    "mit",
    "apache-2.0",
    "bsd-2-clause",
    "bsd-3-clause",
    "isc",
    "0bsd",
    "unlicense",
]

PERMISSIVE = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD", "Unlicense"}
E3 = re.compile(
    r"starter|boilerplate|template|tutorial|example|demo|course|learn|workshop|playground|"
    r"sample|bootcamp|cheatsheet|awesome",
    re.IGNORECASE,
)
MIN_MODELS, MIN_LOC = 20, 5000
SKIPPED_DIRS = {"node_modules", "dist", "build", ".next", "generated", ".git"}


def log(message: str) -> None:
    sys.stderr.write(message + "\n")


# ---- GitHub access (through the authenticated gh CLI; read-only) -----------------------------


def gh(path: str, *, raw: bool = False) -> Any:
    command = ["gh", "api", "--method", "GET", path]
    if raw:
        command += ["-H", "Accept: application/vnd.github.raw"]
    for attempt in range(6):
        done = subprocess.run(command, capture_output=True, text=True, check=False)
        if done.returncode == 0:
            return done.stdout if raw else json.loads(done.stdout)
        message = done.stderr + done.stdout
        if "rate limit" in message.lower() or "secondary" in message.lower() or "abuse" in message:
            time.sleep(30 * (attempt + 1))
            continue
        if "HTTP 404" in message or "HTTP 409" in message or "HTTP 451" in message:
            return None
        if attempt == 5:
            raise RuntimeError(f"gh api {path}: {message.strip()[:300]}")
        time.sleep(2)
    raise RuntimeError(f"gh api {path}: rate limited")


def search(kind: str, query: str, shard_note: str, shards: list[dict[str, Any]]) -> list[Any]:
    """All results of a search query (at most GitHub's 1000-result window), 100 per page."""
    items: list[Any] = []
    total = 0
    for page in range(1, 11):
        data = gh(f"search/{kind}?q={quote(query)}&per_page=100&page={page}")
        if data is None:
            break
        total = data["total_count"]
        items += data["items"]
        if len(items) >= min(total, 1000) or not data["items"]:
            break
        time.sleep(2.2)  # stay under the search rate limit
    shards.append({"kind": kind, "query": query, "total_count": total, "returned": len(items)})
    log(f"  {kind} {shard_note}: {len(items)} / {total}")
    return items


def _count(kind: str, query: str) -> int:
    data = gh(f"search/{kind}?q={quote(query)}&per_page=1")
    time.sleep(2.2)
    return int(data["total_count"]) if data else 0


def sharded(kind: str, template: str, lo: int, hi: int, shards: list[dict[str, Any]]) -> list[Any]:
    """Splits the range [lo, hi] until each shard fits GitHub's 1000-result window."""
    query = template.format(a=lo, b=hi)
    if hi > lo and _count(kind, query) > 1000:
        mid = (lo + hi) // 2
        return sharded(kind, template, lo, mid, shards) + sharded(
            kind, template, mid + 1, hi, shards
        )
    return search(kind, query, f"[{lo}..{hi}]", shards)


# ---- the per-candidate decision ---------------------------------------------------------------


@dataclass
class Candidate:
    repo: str
    found_by: list[str] = field(default_factory=list)
    decision: str = "pending"  # "eligible" or "excluded"
    reason: str = ""
    url: str = ""
    stars: int | None = None
    license: str | None = None
    default_branch: str | None = None
    last_commit_date: str | None = None
    last_commit_sha: str | None = None
    schema_path: str | None = None
    schema_files: int = 0
    models: int | None = None
    typescript_loc: int | None = None


def exclude(c: Candidate, reason: str) -> Candidate:
    c.decision, c.reason = "excluded", reason
    return c


def metadata_tests(c: Candidate, meta: dict[str, Any]) -> str | None:
    """E1, E2, E3, then I4. Returns the reason for the first failing test."""
    if meta.get("fork") or meta.get("archived") or meta.get("is_template"):
        return "E1: fork, archived or template"
    if meta["owner"]["login"].lower() in {"prisma", "prisma-labs"}:
        return "E2: Prisma's own"
    text = " ".join([meta["name"], meta.get("description") or "", *meta.get("topics", [])])
    if match := E3.search(text):
        return f"E3: tutorial/starter word '{match.group(0).lower()}'"
    spdx = (meta.get("license") or {}).get("spdx_id")
    c.license = spdx
    if spdx not in PERMISSIVE:
        return f"I4: license {spdx or 'none'} is not in the permissive list"
    return None


def count_models(schema: str) -> int:
    return len(re.findall(r"^model\s+\w+", schema, re.MULTILINE))


def provider_is_postgres(schema: str) -> bool:
    for block in re.findall(r"datasource\s+\w+\s*\{(.*?)\}", schema, re.DOTALL):
        if re.search(r'provider\s*=\s*"(postgresql|postgres)"', block):
            return True
    return False


def typescript_loc(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if any(part in SKIPPED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file() and path.suffix in {".ts", ".tsx"} and not path.name.endswith(".d.ts"):
            with path.open("rb") as handle:
                total += sum(1 for _ in handle)
    return total


def decide(c: Candidate, meta: dict[str, Any]) -> Candidate:
    c.url = meta["html_url"]
    c.stars = meta["stargazers_count"]
    c.default_branch = meta["default_branch"]
    if reason := metadata_tests(c, meta):
        return exclude(c, reason)

    commits = gh(f"repos/{c.repo}/commits?sha={quote(c.default_branch)}&per_page=1")
    if not commits:
        return exclude(c, "I3: no commits readable")
    c.last_commit_sha = commits[0]["sha"]
    c.last_commit_date = commits[0]["commit"]["committer"]["date"]
    if datetime.fromisoformat(c.last_commit_date.replace("Z", "+00:00")) < ACTIVE_SINCE:
        return exclude(c, f"I3: last commit {c.last_commit_date[:10]} is older than 12 months")

    tree = gh(f"repos/{c.repo}/git/trees/{c.last_commit_sha}?recursive=1")
    if not tree:
        return exclude(c, "I1: repository tree unreadable")
    paths = [
        e["path"]
        for e in tree["tree"]
        if e["type"] == "blob" and e["path"].split("/")[-1] == "schema.prisma"
    ]
    paths = [p for p in paths if not any(part in SKIPPED_DIRS for part in p.split("/"))]
    c.schema_files = len(paths)
    if not paths:
        return exclude(c, "I1: no schema.prisma file")
    best: tuple[int, str] | None = None
    for path in paths:
        text = gh(f"repos/{c.repo}/contents/{quote(path)}?ref={c.last_commit_sha}", raw=True)
        if text and provider_is_postgres(text):
            models = count_models(text)
            if best is None or models > best[0]:
                best = (models, path)
    if best is None:
        return exclude(c, "I1: no schema.prisma with a postgresql datasource")
    c.models, c.schema_path = best

    if not any(n.get("path", "").endswith((".ts", ".tsx")) for n in tree["tree"]):
        return exclude(c, "E4: no TypeScript")

    clone = WORK / "clones" / c.repo.replace("/", "__")
    if not clone.exists():
        clone.parent.mkdir(parents=True, exist_ok=True)
        done = subprocess.run(
            [
                "git",
                "clone",
                "--quiet",
                "--depth",
                "1",
                f"https://github.com/{c.repo}.git",
                str(clone),
            ],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if done.returncode != 0:
            return exclude(c, f"I2: clone failed ({done.stderr.strip()[:80]})")
    c.typescript_loc = typescript_loc(clone)
    if c.models < MIN_MODELS and c.typescript_loc < MIN_LOC:
        shutil.rmtree(clone, ignore_errors=True)
        return exclude(c, f"I2: {c.models} models and {c.typescript_loc} TypeScript lines")
    c.decision, c.reason = "eligible", "meets all criteria"
    return c


# ---- the run ------------------------------------------------------------------------------------


def enumerate_candidates(
    shards: list[dict[str, Any]],
) -> tuple[dict[str, Candidate], dict[str, dict[str, Any]]]:
    found: dict[str, Candidate] = {}
    metas: dict[str, dict[str, Any]] = {}
    since = ACTIVE_SINCE.date().isoformat()
    for license_id in LICENSE_QUALIFIERS:
        log(f"repository search: license:{license_id}")
        template = (
            f"topic:prisma language:TypeScript license:{license_id} fork:false archived:false "
            f"pushed:>{since} stars:{{a}}..{{b}}"
        )
        for item in sharded("repositories", template, 0, 500_000, shards):
            found.setdefault(item["full_name"], Candidate(item["full_name"])).found_by.append(
                f"topic:{license_id}"
            )
            metas[item["full_name"]] = item
    return found, metas


def run(resume: bool) -> dict[str, Any]:
    WORK.mkdir(exist_ok=True)
    cache_file = WORK / "decisions.json"
    cached: dict[str, Any] = (
        json.loads(cache_file.read_text()) if resume and cache_file.exists() else {}
    )
    shards: list[dict[str, Any]] = []
    pool_file = WORK / "pool.json"
    if resume and pool_file.exists():
        pool = json.loads(pool_file.read_text())
        found = {r: Candidate(**v) for r, v in pool["found"].items()}
        metas, shards = pool["metas"], pool["shards"]
    else:
        found, metas = enumerate_candidates(shards)
        pool_file.write_text(
            json.dumps(
                {
                    "found": {r: asdict(c) for r, c in found.items()},
                    "metas": metas,
                    "shards": shards,
                }
            )
        )
    log(f"{len(found)} distinct repositories found")

    order = sorted(found)
    random.Random(STUDY_SEED).shuffle(order)
    decisions: dict[str, Candidate] = {}
    for n, repo in enumerate(order, 1):
        if sum(c.decision == "eligible" for c in decisions.values()) >= TARGET_ELIGIBLE:
            break
        if repo in cached:
            decisions[repo] = Candidate(**cached[repo])
            continue
        c = found[repo]
        try:
            meta = metas.get(repo) or gh(f"repos/{repo}")
            if meta is None:
                decisions[repo] = exclude(c, "E1: repository not readable (deleted or private)")
            else:
                decisions[repo] = decide(c, meta)
        except Exception as error:  # a broken candidate must not stop the study
            decisions[repo] = exclude(c, f"error: {str(error)[:120]}")
        cached[repo] = asdict(decisions[repo])
        cache_file.write_text(json.dumps(cached))
        if n % 25 == 0 or decisions[repo].decision == "eligible":
            log(f"[{n}/{len(found)}] {repo}: {decisions[repo].decision} ({decisions[repo].reason})")

    eligible = sorted(
        (c for c in decisions.values() if c.decision == "eligible"), key=lambda c: c.repo
    )
    study = eligible
    if len(eligible) > STUDY_SIZE:
        study = sorted(random.Random(STUDY_SEED).sample(eligible, STUDY_SIZE), key=lambda c: c.repo)
    reasons: dict[str, int] = {}
    for c in decisions.values():
        if c.decision == "excluded":
            key = c.reason.split(":")[0] if not c.reason.startswith("error") else "error"
            reasons[key] = reasons.get(key, 0) + 1
    return {
        "selection_date": SELECTION_DATE.date().isoformat(),
        "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        "study_seed": STUDY_SEED,
        "evaluation_order": [r for r in order if r in decisions],
        "pool_size": len(found),
        "unevaluated": len(found) - len(decisions),
        "shards": shards,
        "found": len(found),
        "eligible": len(eligible),
        "meets_minimum": len(eligible) >= MIN_ELIGIBLE,
        "excluded_by_first_failing_test": dict(sorted(reasons.items())),
        "study_set": [c.repo for c in study],
        "candidates": [asdict(decisions[r]) for r in order if r in decisions],
    }


def write_table(result: dict[str, Any], path: Path) -> None:
    study = set(result["study_set"])
    rows = [c for c in result["candidates"] if c["decision"] == "eligible"]
    lines = [
        f"# Candidate repositories (selected {result['selection_date']})",
        "",
        f"Protocol SHA-256 `{result['protocol_sha256'][:16]}`. {result['found']} repositories "
        f"in the pool, {result['eligible']} eligible, {len(study)} in the study set.",
        "",
        "| Repository | Stars | Models | TS LOC | Last commit | License | Pinned commit | Study |",
        "|---|---:|---:|---:|---|---|---|---|",
    ]
    for c in sorted(rows, key=lambda c: c["repo"]):
        lines.append(
            f"| [{c['repo']}]({c['url']}) | {c['stars']} | {c['models']} | {c['typescript_loc']} | "
            f"{c['last_commit_date'][:10]} | {c['license']} | `{c['last_commit_sha'][:10]}` | "
            f"{'yes' if c['repo'] in study else 'no'} |"
        )
    lines += ["", "## Exclusions (first failing test)", ""]
    lines += [f"- {k}: {v}" for k, v in result["excluded_by_first_failing_test"].items()]
    path.write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m experiments.realworld.select_repos")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    result = run(args.resume)
    (HERE / "candidates.json").write_text(json.dumps(result, indent=2) + "\n")
    write_table(result, HERE / "CANDIDATES.md")
    log(
        f"eligible {result['eligible']} of {result['pool_size']} in the pool; "
        f"minimum {MIN_ELIGIBLE} met: {result['meets_minimum']}"
    )
    return 0 if result["meets_minimum"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
