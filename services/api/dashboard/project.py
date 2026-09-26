"""Scanning a project that is not one of the built-in test apps.

A real-world project has no running application and no database of ours, so it gets the Approach B
pipeline only: static ORM analysis, SQL analysis of the repository text, and the declared schema.
Runtime, actual-schema and data-quality layers do not apply and are not run.

Nothing from the project is executed or installed: a Git URL is cloned shallowly over https (no
hooks run on clone) and the sources are only read. The dependencies are deliberately not installed,
so this measures the analyzer on source alone.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from analyzers.core_bridge import coverage

WORK = Path(__file__).resolve().parents[2] / "experiments" / "realworld" / "work" / "projects"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")
GIT_URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+?(?:\.git)?/?$")
SKIPPED = {"node_modules", ".git", "dist", "build", ".next", "generated"}
CLONE_TIMEOUT_S = 600


class ProjectError(ValueError):
    """The request cannot be turned into a scannable project; the message says why."""


def slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-._")
    return cleaned[:63] or "project"


@dataclass(frozen=True)
class ProjectSource:
    name: str
    root: Path
    #: How it was given: "local" or "git".
    origin_kind: str
    origin: str
    #: Chosen schema, relative to root; None when the project has no schema.prisma.
    schema_path: str | None
    schema_candidates: tuple[dict[str, Any], ...]
    commit: str | None
    dirty: bool | None
    notes: tuple[str, ...]

    def as_json(self, cover: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "kind": self.origin_kind,
            "origin": self.origin,
            "commit": self.commit,
            "dirty": self.dirty,
            "schema_path": self.schema_path,
            "schema_candidates": list(self.schema_candidates),
            "notes": list(self.notes),
            "coverage": cover,
        }


def _git(root: Path, *args: str) -> str | None:
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False, timeout=120
    )
    return done.stdout.strip() if done.returncode == 0 else None


def find_schemas(root: Path) -> list[dict[str, Any]]:
    """Every schema.prisma under root with its model count, most models first."""
    found = []
    for path in root.rglob("schema.prisma"):
        relative = path.relative_to(root)
        if any(part in SKIPPED for part in relative.parts):
            continue
        text = path.read_text(errors="ignore")
        found.append(
            {
                "path": relative.as_posix(),
                "models": len(re.findall(r"^model\s+\w+", text, re.MULTILINE)),
                "postgresql": bool(re.search(r'provider\s*=\s*"(postgresql|postgres)"', text)),
            }
        )
    return sorted(found, key=lambda s: (-s["models"], s["path"]))


def clone(url: str, destination: Path) -> None:
    if not GIT_URL_RE.match(url):
        raise ProjectError("the Git URL must look like https://host/owner/repository")
    destination.parent.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(
        [
            "git", "-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
            "clone", "--quiet", "--depth", "1", url, str(destination),
        ],
        capture_output=True, text=True, check=False, timeout=CLONE_TIMEOUT_S,
    )  # fmt: skip
    if done.returncode != 0:
        raise ProjectError(f"could not clone {url}: {done.stderr.strip()[:200]}")


def resolve(
    *,
    path: str | None = None,
    git_url: str | None = None,
    schema_path: str | None = None,
    name: str | None = None,
    refresh: bool = False,
) -> ProjectSource:
    if bool(path) == bool(git_url):
        raise ProjectError("give exactly one of a local path or a Git URL")
    notes: list[str] = []

    if path:
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            raise ProjectError(f"{root} is not a directory")
        kind, origin = "local", str(root)
        chosen_name = slug(name or root.name)
    else:
        assert git_url
        if not GIT_URL_RE.match(git_url):
            raise ProjectError("the Git URL must look like https://host/owner/repository")
        stem = git_url.rstrip("/").removesuffix(".git").rsplit("/", 2)
        chosen_name = slug(name or f"{stem[-2]}-{stem[-1]}")
        root = WORK / chosen_name
        if root.exists() and refresh:
            pulled = subprocess.run(
                ["git", "-C", str(root), "pull", "--ff-only", "--quiet"],
                capture_output=True, text=True, check=False, timeout=CLONE_TIMEOUT_S,
            )  # fmt: skip
            if pulled.returncode != 0:
                notes.append(
                    "could not update the clone; scanning what was already there "
                    + f"({pulled.stderr.strip()[:120]})"
                )
        elif not root.exists():
            clone(git_url, root)
        kind, origin = "git", git_url

    if not NAME_RE.match(chosen_name):
        raise ProjectError(f"'{chosen_name}' is not a usable project name")

    schemas = find_schemas(root)
    if schema_path:
        chosen = Path(schema_path)
        if chosen.is_absolute() or ".." in chosen.parts or not (root / chosen).is_file():
            raise ProjectError(f"schema path '{schema_path}' is not a file inside the project")
        schema = chosen.as_posix()
    elif schemas:
        schema = schemas[0]["path"]
        if len(schemas) > 1:
            notes.append(
                f"{len(schemas)} schema.prisma files found; using the one with the most "
                f"models ({schema})"
            )
    else:
        schema = None
        notes.append(
            "no schema.prisma found: the declared-schema layer was skipped, so index findings "
            "cannot be produced"
        )
    if schema and not any(s["path"] == schema and s["postgresql"] for s in schemas):
        notes.append("the schema's datasource is not PostgreSQL; the analysis still runs")

    commit = _git(root, "rev-parse", "HEAD")
    dirty = bool(_git(root, "status", "--porcelain")) if commit else None
    return ProjectSource(
        chosen_name, root, kind, origin, schema, tuple(schemas), commit, dirty, tuple(notes)
    )


def measure_coverage(source: ProjectSource) -> dict[str, Any]:
    seen = coverage(
        source.root, (source.root / source.schema_path) if source.schema_path else None, timeout=300
    )
    return {"source_files": seen["sourceFiles"], "orm_operations": seen["ormOperations"]}
