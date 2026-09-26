"""Batch analysis: run the Approach B analyzer (static source + declared schema, no database) on
each study repository at its pinned commit and store every finding.

The analyzer's only input is `{ sourceDir, schemaPath }` (constraint 2); nothing here knows about
any particular repository. A repository the analyzer cannot process is recorded as failed, with
the reason, and kept in the denominator of the study: dropping it would bias the sample.
"""

import hashlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from analyzers.core_bridge import CoreError, analyze
from experiments.ablation.store import code_state

from .store import RealWorldStore

HERE = Path(__file__).resolve().parent
WORK = HERE / "work"
CANDIDATES = HERE / "candidates.json"
PROTOCOL = HERE / "PROTOCOL.md"
DEFAULT_TIMEOUT_S = 900.0


def _git(clone: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(clone), *args], capture_output=True, text=True, check=False, timeout=600
    )
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()[:200]}")
    return done.stdout.strip()


def clone_dir(repo: str) -> Path:
    return WORK / "clones" / repo.replace("/", "__")


def checkout(repo: str, sha: str) -> Path:
    """The repository at exactly `sha`: cloned if absent, moved to the pin if it drifted."""
    clone = clone_dir(repo)
    if not (clone / ".git").exists():
        clone.mkdir(parents=True, exist_ok=True)
        _git(clone, "init", "--quiet")
        _git(clone, "remote", "add", "origin", f"https://github.com/{repo}.git")
    try:
        head = _git(clone, "rev-parse", "HEAD")
    except RuntimeError:
        head = ""
    if head != sha:
        _git(clone, "fetch", "--quiet", "--depth", "1", "origin", sha)
        _git(clone, "checkout", "--quiet", "--force", "--detach", sha)
    return clone


def load_study() -> tuple[list[dict[str, Any]], str]:
    raw = CANDIDATES.read_bytes()
    data = json.loads(raw)
    by_repo = {c["repo"]: c for c in data["candidates"]}
    return [by_repo[r] for r in data["study_set"]], hashlib.sha256(raw).hexdigest()


def analyze_repo(
    candidate: dict[str, Any], timeout: float = DEFAULT_TIMEOUT_S
) -> tuple[dict, list]:
    repo, sha = candidate["repo"], candidate["last_commit_sha"]
    result: dict[str, Any] = {
        "repo": repo,
        "commit_sha": sha,
        "schema_path": candidate["schema_path"],
        "status": "ok",
        "error": None,
        "duration_s": 0.0,
    }
    started = time.perf_counter()
    findings: list[dict[str, Any]] = []
    try:
        clone = checkout(repo, sha)
        findings = analyze(clone, clone / candidate["schema_path"], timeout=timeout)
    except (CoreError, RuntimeError, subprocess.TimeoutExpired, OSError) as error:
        result["status"], result["error"] = "failed", str(error)[:500]
    result["duration_s"] = time.perf_counter() - started
    findings.sort(key=lambda f: (f["file"], f["line"], f["ruleId"], f["fingerprint"]))
    return result, findings


def run(timeout: float = DEFAULT_TIMEOUT_S, only: list[str] | None = None, log=print) -> str:
    from experiments.ablation.experiment import _urls  # the results database

    study, candidates_sha = load_study()
    if only:
        study = [c for c in study if c["repo"] in only]
    os.environ.setdefault("NODE_OPTIONS", "--max-old-space-size=8192")
    store = RealWorldStore(_urls("blog")[1])
    analysis_id = str(uuid.uuid4())
    protocol_sha = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    store.start(
        analysis_id,
        state=code_state(),
        candidates_sha256=candidates_sha,
        protocol_sha256=protocol_sha,
        study_set=[c["repo"] for c in study],
    )
    try:
        for index, candidate in enumerate(study, 1):
            result, findings = analyze_repo(candidate, timeout)
            for n, finding in enumerate(findings, 1):
                finding["finding_id"] = f"R{index:02d}-{n:03d}"
            store.add_repo(analysis_id, result, findings)
            log(
                f"[{index}/{len(study)}] {candidate['repo']}: {result['status']} "
                f"{len(findings)} findings in {result['duration_s']:.1f}s"
                + (f" ({result['error']})" if result["error"] else "")
            )
        store.finish(analysis_id)
    finally:
        store.close()
    return analysis_id
