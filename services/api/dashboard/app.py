"""Dashboard API.

    uv run uvicorn api.dashboard.app:app --port 8710

Read-only apart from `POST /v1/apps/{app}/scans`, which runs a scan. Nothing here changes a
finding's type, severity or confidence: findings are served exactly as stored.
"""

import os
import threading
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from analyzers.finding import Finding
from api.explain import AnthropicLLM, Explainer, ExplainError, PostgresCache
from experiments.ablation.experiment import REPO_ROOT

from . import project as projects
from .scan import run_project_scan, run_scan
from .store import ScanStore

APPS = sorted(
    p.name for p in (REPO_ROOT / "apps").iterdir() if (p / "prisma" / "schema.prisma").exists()
)
_scan_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "store"):
        app.state.store = ScanStore(os.environ["DBINSIGHT_RESULTS_DATABASE_URL"])
    yield


app = FastAPI(title="DBInsight dashboard API", lifespan=lifespan)


def get_store(request: Request) -> ScanStore:
    return request.app.state.store


StoreDep = Annotated[ScanStore, Depends(get_store)]


def _known(store: ScanStore) -> set[str]:
    return set(APPS) | {p["app"] for p in store.projects()}


def _require_app(name: str, store: ScanStore) -> str:
    if name not in _known(store):
        raise HTTPException(404, f"unknown app or project '{name}'")
    return name


def _scan_or_404(store: ScanStore, scan_id: str) -> dict[str, Any]:
    try:
        scan = store.scan(scan_id)
    except Exception as error:  # a malformed uuid
        raise HTTPException(404, "no such scan") from error
    if scan is None:
        raise HTTPException(404, "no such scan")
    return scan


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/apps")
def apps(store: StoreDep) -> list[dict[str, Any]]:
    """The built-in test apps, then the projects that have been scanned."""
    out = []
    for name in APPS:
        scans = store.scans(name, limit=1)
        out.append(
            {"app": name, "kind": "app", "source": None, "latest_scan": scans[0] if scans else None}
        )
    for project in store.projects():
        scans = store.scans(project["app"], limit=1)
        out.append(
            {
                "app": project["app"],
                "kind": "project",
                "source": project["source"],
                "latest_scan": scans[0] if scans else None,
            }
        )
    return out


@app.get("/v1/apps/{app_name}/scans")
def scans(app_name: str, store: StoreDep, limit: Annotated[int, Query(ge=1, le=200)] = 50):
    return store.scans(_require_app(app_name, store), limit)


@app.post("/v1/apps/{app_name}/scans", status_code=201)
def start_scan(app_name: str, store: StoreDep) -> dict[str, Any]:
    if app_name not in APPS:
        raise HTTPException(
            404, f"'{app_name}' is not a built-in app; scan a project with POST /v1/projects/scans"
        )
    if not _scan_lock.acquire(blocking=False):
        raise HTTPException(409, "a scan is already running")
    try:
        scan_id = run_scan(app_name, store)
    except Exception as error:
        raise HTTPException(500, f"scan failed: {type(error).__name__}: {error}") from error
    finally:
        _scan_lock.release()
    return {"scan_id": scan_id}


class ProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    git_url: str | None = None
    schema_path: str | None = None
    name: str | None = None


def _scan_project(
    store: ScanStore, *, refresh: bool = False, **request: str | None
) -> dict[str, Any]:
    try:
        source = projects.resolve(refresh=refresh, **request)
    except projects.ProjectError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:  # a git failure or timeout
        raise HTTPException(502, f"could not fetch the project: {error}") from error
    if source.name in APPS:
        raise HTTPException(409, f"'{source.name}' is a built-in app; choose another project name")
    if not _scan_lock.acquire(blocking=False):
        raise HTTPException(409, "a scan is already running")
    try:
        scan_id = run_project_scan(source, store)
    except Exception as error:
        raise HTTPException(500, f"scan failed: {type(error).__name__}: {error}") from error
    finally:
        _scan_lock.release()
    return {"scan_id": scan_id, "app": source.name}


@app.post("/v1/projects/scans", status_code=201)
def scan_project(body: ProjectRequest, store: StoreDep) -> dict[str, Any]:
    """Scan a project given as a local path or an https Git URL (Approach B: no database)."""
    return _scan_project(
        store, path=body.path, git_url=body.git_url, schema_path=body.schema_path, name=body.name
    )


@app.post("/v1/projects/{name}/rescan", status_code=201)
def rescan_project(name: str, store: StoreDep) -> dict[str, Any]:
    """Scan a known project again from its stored source (a Git project is updated first)."""
    known = next((p for p in store.projects() if p["app"] == name), None)
    if known is None:
        raise HTTPException(404, f"no scanned project '{name}'")
    source = known["source"] or {}
    is_git = source.get("kind") == "git"
    return _scan_project(
        store,
        refresh=True,
        path=None if is_git else source.get("origin"),
        git_url=source.get("origin") if is_git else None,
        schema_path=source.get("schema_path"),
        name=name,
    )


@app.get("/v1/scans/{scan_id}")
def scan_summary(scan_id: str, store: StoreDep) -> dict[str, Any]:
    scan = _scan_or_404(store, scan_id)
    counts = next((s for s in store.scans(scan["app"]) if str(s["scan_id"]) == scan_id), {})
    return {
        **{k: scan[k] for k in ("scan_id", "app", "started_at", "finished_at", "status", "error")},
        "layers": scan["layers"],
        "layer_seconds": scan["layer_seconds"],
        "git_commit": scan["git_commit"],
        "git_dirty": scan["git_dirty"],
        "kind": scan["kind"],
        "source": scan["source"],
        "counts": {k: counts.get(k, 0) for k in ("high", "medium", "low", "total")},
    }


@app.get("/v1/scans/{scan_id}/findings")
def findings(
    scan_id: str,
    store: StoreDep,
    severity: str | None = None,
    confidence: str | None = None,
    rule: str | None = None,
    layer: str | None = None,
) -> list[dict[str, Any]]:
    _scan_or_404(store, scan_id)
    rows = store.findings(scan_id)
    return [
        r
        for r in rows
        if (severity is None or r["severity"] == severity.upper())
        and (confidence is None or r["confidence"] == confidence.upper())
        and (rule is None or r["rule_id"] == rule)
        and (layer is None or layer.upper() in r["layers"])
    ]


@app.get("/v1/scans/{scan_id}/findings/{finding_id}")
def finding(scan_id: str, finding_id: str, store: StoreDep) -> dict[str, Any]:
    _scan_or_404(store, scan_id)
    row = store.finding(scan_id, finding_id)
    if row is None:
        raise HTTPException(404, "no such finding")
    return row


def _explainer(request: Request) -> Explainer:
    if not hasattr(request.app.state, "explainer"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise HTTPException(
                503, "the explanation layer is not configured (set ANTHROPIC_API_KEY)"
            )
        request.app.state.explainer = Explainer(
            AnthropicLLM(), PostgresCache(os.environ["DBINSIGHT_RESULTS_DATABASE_URL"])
        )
    return request.app.state.explainer


@app.get("/v1/scans/{scan_id}/findings/{finding_id}/explanation")
def explanation(scan_id: str, finding_id: str, request: Request, store: StoreDep):
    """Downstream text only: the finding is read, projected, and never modified."""
    _scan_or_404(store, scan_id)
    row = store.finding(scan_id, finding_id)
    if row is None:
        raise HTTPException(404, "no such finding")
    stored = Finding.model_validate(
        {
            "schemaVersion": 1,
            "ruleId": row["rule_id"],
            "severity": row["severity"],
            "confidence": row["confidence"],
            "file": row["file"],
            "line": row["line"],
            "endLine": row["end_line"],
            "title": row["title"],
            "body": row["body"],
            "evidence": row["evidence"],
            "suggestedFix": row["suggested_fix"],
            "fingerprint": row["fingerprint"],
        }
    )
    try:
        return _explainer(request).explain(stored).model_dump()
    except ExplainError as error:
        raise HTTPException(502, str(error)) from error


def _snapshot(store: ScanStore, scan_id: str, column: str) -> Any:
    return _scan_or_404(store, scan_id)[column]


@app.get("/v1/scans/{scan_id}/queries")
def queries(scan_id: str, store: StoreDep) -> Any:
    return _snapshot(store, scan_id, "query_analytics")


@app.get("/v1/scans/{scan_id}/data-quality")
def data_quality(scan_id: str, store: StoreDep) -> Any:
    return _snapshot(store, scan_id, "data_quality")


@app.get("/v1/scans/{scan_id}/schema")
def schema(scan_id: str, store: StoreDep) -> Any:
    return _snapshot(store, scan_id, "schema_view")
