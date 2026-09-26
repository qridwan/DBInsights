"""Dashboard API.

    uv run uvicorn api.dashboard.app:app --port 8710

Every route except /health and /v1/auth/* needs a signed-in user (`Authorization: Bearer <token>`).
Data is isolated by owner: a scanned project belongs to whoever scanned it and is invisible to
everyone else (a request for someone else's scan is a 404, never a 403, so its existence is not
revealed). The built-in test apps are open to every signed-in user. Nothing here changes a
finding's type, severity or confidence: findings are served exactly as stored.
"""

import os
import shutil
import threading
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict

from analyzers.finding import Finding
from api.explain import AnthropicLLM, Explainer, ExplainError, PostgresCache
from experiments.ablation.experiment import REPO_ROOT

from . import fsbrowse
from . import project as projects
from .auth.mailer import mailer_from_env
from .auth.routes import CurrentUser, admin_emails, auth_error_response
from .auth.routes import router as auth_router
from .auth.service import AuthError, AuthService
from .auth.store import AuthStore
from .scan import run_project_scan, run_scan
from .store import ScanStore

APPS = sorted(
    p.name for p in (REPO_ROOT / "apps").iterdir() if (p / "prisma" / "schema.prisma").exists()
)
_scan_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    url = os.environ.get("DBINSIGHT_RESULTS_DATABASE_URL")
    if not hasattr(app.state, "store"):
        app.state.store = ScanStore(url or os.environ["DBINSIGHT_RESULTS_DATABASE_URL"])
    if not hasattr(app.state, "auth"):
        app.state.auth = AuthService(
            AuthStore(url or os.environ["DBINSIGHT_RESULTS_DATABASE_URL"]),
            mailer_from_env(),
            admin_emails=admin_emails(),
        )
    yield


app = FastAPI(title="DBInsight dashboard API", lifespan=lifespan)
app.add_exception_handler(AuthError, auth_error_response)  # type: ignore[arg-type]
app.include_router(auth_router)


def get_store(request: Request) -> ScanStore:
    return request.app.state.store


StoreDep = Annotated[ScanStore, Depends(get_store)]


def _known(store: ScanStore, user: dict[str, Any]) -> set[str]:
    return set(APPS) | {p["app"] for p in store.projects(user["id"])}


def _require_app(name: str, store: ScanStore, user: dict[str, Any]) -> str:
    if name not in _known(store, user):
        raise HTTPException(404, f"unknown app or project '{name}'")
    return name


def _scan_or_404(store: ScanStore, scan_id: str, user: dict[str, Any]) -> dict[str, Any]:
    """The scan if this user may see it. Someone else's scan is indistinguishable from none."""
    try:
        scan = store.scan(scan_id, viewer=user["id"])
    except Exception as error:  # a malformed uuid
        raise HTTPException(404, "no such scan") from error
    if scan is None:
        raise HTTPException(404, "no such scan")
    return scan


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/apps")
def apps(store: StoreDep, user: CurrentUser) -> list[dict[str, Any]]:
    """The built-in test apps, then this user's scanned projects."""
    out = []
    for name in APPS:
        scans = store.scans(name, limit=1, viewer=user["id"])
        out.append(
            {"app": name, "kind": "app", "source": None, "latest_scan": scans[0] if scans else None}
        )
    for project in store.projects(user["id"]):
        scans = store.scans(project["app"], limit=1, viewer=user["id"])
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
def scans(
    app_name: str,
    store: StoreDep,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return store.scans(_require_app(app_name, store, user), limit, viewer=user["id"])


@app.post("/v1/apps/{app_name}/scans", status_code=201)
def start_scan(app_name: str, store: StoreDep, user: CurrentUser) -> dict[str, Any]:
    if app_name not in APPS:
        raise HTTPException(
            404, f"'{app_name}' is not a built-in app; scan a project with POST /v1/projects/scans"
        )
    if not _scan_lock.acquire(blocking=False):
        raise HTTPException(409, "a scan is already running")
    try:
        scan_id = run_scan(app_name, store, user["id"])
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
    store: ScanStore, user: dict[str, Any], *, refresh: bool = False, **request: str | None
) -> dict[str, Any]:
    try:
        source = projects.resolve(
            refresh=refresh,
            owner_key=user["id"][:8],
            allow_local=user["can_scan_local"],
            **request,
        )
    except projects.ProjectError as error:
        raise HTTPException(error.status, str(error)) from error
    except Exception as error:  # a git failure or timeout
        raise HTTPException(502, f"could not fetch the project: {error}") from error
    if source.name in APPS:
        raise HTTPException(409, f"'{source.name}' is a built-in app; choose another project name")
    if not _scan_lock.acquire(blocking=False):
        raise HTTPException(409, "a scan is already running")
    try:
        scan_id = run_project_scan(source, store, user["id"])
    except Exception as error:
        raise HTTPException(500, f"scan failed: {type(error).__name__}: {error}") from error
    finally:
        _scan_lock.release()
    return {"scan_id": scan_id, "app": source.name}


@app.post("/v1/projects/scans", status_code=201)
def scan_project(body: ProjectRequest, store: StoreDep, user: CurrentUser) -> dict[str, Any]:
    """Scan a project given as a local path (administrators) or an https Git URL. Approach B: no
    database. The project is private to the user who scanned it."""
    return _scan_project(
        store,
        user,
        path=body.path,
        git_url=body.git_url,
        schema_path=body.schema_path,
        name=body.name,
    )


@app.post("/v1/projects/{name}/rescan", status_code=201)
def rescan_project(name: str, store: StoreDep, user: CurrentUser) -> dict[str, Any]:
    """Scan one of your projects again from its stored source (a Git project is updated first)."""
    known = next((p for p in store.projects(user["id"]) if p["app"] == name), None)
    if known is None:
        raise HTTPException(404, f"no scanned project '{name}'")
    source = known["source"] or {}
    is_git = source.get("kind") == "git"
    return _scan_project(
        store,
        user,
        refresh=True,
        path=None if is_git else source.get("origin"),
        git_url=source.get("origin") if is_git else None,
        schema_path=source.get("schema_path"),
        name=name,
    )


@app.get("/v1/fs/browse")
def browse_folders(
    user: CurrentUser, path: str | None = None, hidden: bool = False
) -> dict[str, Any]:
    """Directories inside a folder on this machine, for choosing a project to scan. Administrators
    only: the same people who may scan a server folder."""
    if not user["can_scan_local"]:
        raise HTTPException(403, "browsing folders on the server is limited to administrators")
    try:
        return fsbrowse.browse(path, hidden)
    except fsbrowse.BrowseError as error:
        raise HTTPException(error.status, str(error)) from error


@app.delete("/v1/projects/{name}", status_code=204)
def delete_project(name: str, store: StoreDep, user: CurrentUser) -> Response:
    """Remove one of your projects: its scans, findings, and the cloned copy."""
    if store.delete_project(user["id"], name) == 0:
        raise HTTPException(404, f"no scanned project '{name}'")
    shutil.rmtree(projects.WORK / user["id"][:8] / name, ignore_errors=True)
    return Response(status_code=204)


@app.get("/v1/scans/{scan_id}")
def scan_summary(scan_id: str, store: StoreDep, user: CurrentUser) -> dict[str, Any]:
    scan = _scan_or_404(store, scan_id, user)
    counts = next(
        (s for s in store.scans(scan["app"], viewer=user["id"]) if str(s["scan_id"]) == scan_id), {}
    )
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
    user: CurrentUser,
    severity: str | None = None,
    confidence: str | None = None,
    rule: str | None = None,
    layer: str | None = None,
) -> list[dict[str, Any]]:
    _scan_or_404(store, scan_id, user)
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
def finding(scan_id: str, finding_id: str, store: StoreDep, user: CurrentUser) -> dict[str, Any]:
    _scan_or_404(store, scan_id, user)
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
def explanation(
    scan_id: str, finding_id: str, request: Request, store: StoreDep, user: CurrentUser
):
    """Downstream text only: the finding is read, projected, and never modified."""
    _scan_or_404(store, scan_id, user)
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


def _snapshot(store: ScanStore, scan_id: str, column: str, user: dict[str, Any]) -> Any:
    return _scan_or_404(store, scan_id, user)[column]


@app.get("/v1/scans/{scan_id}/queries")
def queries(scan_id: str, store: StoreDep, user: CurrentUser) -> Any:
    return _snapshot(store, scan_id, "query_analytics", user)


@app.get("/v1/scans/{scan_id}/data-quality")
def data_quality(scan_id: str, store: StoreDep, user: CurrentUser) -> Any:
    return _snapshot(store, scan_id, "data_quality", user)


@app.get("/v1/scans/{scan_id}/schema")
def schema(scan_id: str, store: StoreDep, user: CurrentUser) -> Any:
    return _snapshot(store, scan_id, "schema_view", user)
