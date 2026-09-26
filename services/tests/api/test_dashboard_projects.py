import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.dashboard import app as dashboard
from api.dashboard import project
from api.dashboard.project import ProjectError
from api.dashboard.store import ScanStore

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "source"


def git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A small Prisma project as a git repository."""
    root = tmp_path / "Shop App"
    shutil.copytree(FIXTURES / "rules", root / "src")
    (root / "prisma").mkdir()
    shutil.copy(FIXTURES / "schema.prisma", root / "prisma" / "schema.prisma")
    git(root, "init", "--quiet")
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "init")
    return root


# ---- what may be scanned ---------------------------------------------------------------------


def test_exactly_one_of_path_and_url_is_required(repo):
    with pytest.raises(ProjectError, match="exactly one"):
        project.resolve()
    with pytest.raises(ProjectError, match="exactly one"):
        project.resolve(path=str(repo), git_url="https://github.com/a/b")


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "git://github.com/a/b",
        "file:///etc/passwd",
        "ssh://git@github.com/a/b",
        "https://github.com/a",
        "https://github.com/a/b/c/d",
        "ext::sh -c evil",
        "https://github.com/a/b; rm -rf /",
    ],
)
def test_only_plain_https_repository_urls_are_accepted(url):
    with pytest.raises(ProjectError, match="Git URL"):
        project.resolve(git_url=url)


def test_a_missing_folder_is_rejected(tmp_path):
    with pytest.raises(ProjectError, match="not a directory"):
        project.resolve(path=str(tmp_path / "nope"))


def test_the_schema_path_must_be_a_file_inside_the_project(repo):
    for bad in ("../outside.prisma", "/etc/passwd", "prisma/missing.prisma", "prisma"):
        with pytest.raises(ProjectError, match="not a file inside"):
            project.resolve(path=str(repo), schema_path=bad)


def test_the_name_is_made_safe_and_used_for_the_project(repo):
    assert project.resolve(path=str(repo)).name == "shop-app"
    assert project.resolve(path=str(repo), name="My Project!").name == "my-project"


def test_the_schema_with_the_most_models_is_chosen_and_the_choice_is_noted(repo):
    (repo / "packages" / "db").mkdir(parents=True)
    (repo / "packages" / "db" / "schema.prisma").write_text("model A {\n id Int @id\n}\n")
    (repo / "node_modules" / "x").mkdir(parents=True)
    (repo / "node_modules" / "x" / "schema.prisma").write_text("model B {\n}\n" * 50)
    source = project.resolve(path=str(repo))
    assert source.schema_path == "prisma/schema.prisma"
    assert len(source.schema_candidates) == 2, "dependencies are not candidates"
    assert any("2 schema.prisma files" in n for n in source.notes)


def test_a_project_without_a_schema_is_still_scannable_and_says_what_is_lost(tmp_path):
    root = tmp_path / "noschema"
    (root / "src").mkdir(parents=True)
    source = project.resolve(path=str(root))
    assert source.schema_path is None
    assert any("declared-schema layer was skipped" in n for n in source.notes)


def test_the_commit_and_dirtiness_of_the_scanned_code_are_recorded(repo):
    clean = project.resolve(path=str(repo))
    assert clean.commit == git(repo, "rev-parse", "HEAD") and clean.dirty is False
    (repo / "src" / "new.ts").write_text("// edit\n")
    assert project.resolve(path=str(repo)).dirty is True


# ---- endpoints -------------------------------------------------------------------------------


class Store:
    def __init__(self):
        self.project_rows = []

    def projects(self):
        return self.project_rows

    def scans(self, app=None, limit=50):
        return []


@pytest.fixture
def client():
    dashboard.app.state.store = Store()
    with TestClient(dashboard.app) as c:
        yield c


def test_a_bad_request_is_a_422_with_the_reason(client):
    response = client.post("/v1/projects/scans", json={"git_url": "http://x/y/z"})
    assert response.status_code == 422 and "Git URL" in response.json()["detail"]
    assert client.post("/v1/projects/scans", json={}).status_code == 422


def test_unknown_fields_are_rejected(client):
    assert (
        client.post("/v1/projects/scans", json={"path": "/tmp", "command": "rm"}).status_code == 422
    )


def test_a_project_cannot_take_a_built_in_apps_name(client, repo):
    response = client.post("/v1/projects/scans", json={"path": str(repo), "name": "ecommerce"})
    assert response.status_code == 409 and "built-in" in response.json()["detail"]


def test_rescanning_an_unknown_project_is_a_404(client):
    assert client.post("/v1/projects/nothing/rescan").status_code == 404


def test_the_built_in_scan_endpoint_refuses_projects(client):
    assert client.post("/v1/apps/some-project/scans").status_code == 404


def test_projects_appear_after_the_built_in_apps(client):
    client.app.state.store.project_rows = [{"app": "shop", "source": {"kind": "local"}}]
    listed = client.get("/v1/apps").json()
    assert [a["kind"] for a in listed] == ["app"] * len(dashboard.APPS) + ["project"]
    assert listed[-1]["app"] == "shop" and listed[-1]["source"] == {"kind": "local"}


# ---- a real scan, against the real store (needs the results database) ----------------------------


def test_a_project_is_scanned_with_only_the_layers_that_need_no_database(repo):
    url = os.environ.get("DBINSIGHT_TEST_DATABASE_URL") or os.environ.get(
        "DBINSIGHT_RESULTS_DATABASE_URL"
    )
    if not url:
        pytest.skip("no database configured")
    core = Path(__file__).resolve().parents[3] / "packages" / "core" / "dist" / "cli.js"
    if not core.exists():
        pytest.skip("the core is not built")
    try:
        store = ScanStore(url)
    except Exception as error:
        pytest.skip(f"database unreachable: {error}")
    from api.dashboard.scan import run_project_scan

    name = f"test-{uuid.uuid4().hex[:8]}"
    source = project.resolve(path=str(repo), name=name)
    scan_id = None
    try:
        scan_id = run_project_scan(source, store)
        scan = store.scan(scan_id)
        assert scan["status"] == "ok" and scan["kind"] == "project"
        assert scan["layers"] == ["static_orm", "sql", "declared"]
        assert scan["query_analytics"] is None and scan["data_quality"] is None
        assert scan["schema_view"]["actual"] is None and scan["schema_view"]["divergence"] is None
        assert scan["schema_view"]["declared"], "the declared schema is shown"
        assert scan["source"]["coverage"]["orm_operations"] > 0
        assert scan["source"]["commit"] == source.commit
        findings = store.findings(scan_id)
        assert findings, "the fixtures contain problems"
        assert all(
            "RUNTIME" not in f["layers"] and "ACTUAL_SCHEMA" not in f["layers"] for f in findings
        )
        assert [p["app"] for p in store.projects() if p["app"] == name] == [name]
    finally:
        store.conn.execute("DELETE FROM dashboard.scan WHERE app = %s", (name,))
        store.close()
