"""Who can see what. Runs against the real results database (skipped without one)."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from api.dashboard import app as dashboard
from api.dashboard.store import ScanStore
from tests.api.auth_fakes import make, sign_in

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("DBINSIGHT_TEST_DATABASE_URL")
        or os.environ.get("DBINSIGHT_RESULTS_DATABASE_URL")
    ),
    reason="no database configured",
)

FINDING = {
    "ruleId": "N_PLUS_ONE_IN_LOOP",
    "severity": "HIGH",
    "confidence": "HIGH",
    "file": "a.ts",
    "line": 1,
    "title": "t",
    "body": "b",
    "evidence": [{"source": "STATIC_SOURCE", "description": "d"}],
    "fingerprint": "fp",
}


def url():
    return (
        os.environ.get("DBINSIGHT_TEST_DATABASE_URL")
        or os.environ["DBINSIGHT_RESULTS_DATABASE_URL"]
    )


class World:
    """Three accounts (an administrator and two ordinary users) over a real scan store."""

    def __init__(self):
        self.store = ScanStore(url())
        self.before = self._unowned()
        self.service, self.auth_store, self.mail, _ = make()
        self.h = {}
        self.ids = {}
        self.created = []
        for who in ("admin", "alice", "bob"):
            self.h[who] = sign_in(self.service, self.mail, f"{who}@example.com")
            self.ids[who] = self.service.authenticate(self.h[who]["Authorization"][7:])["id"]
        dashboard.app.state.store = self.store
        dashboard.app.state.auth = self.service
        self.client = TestClient(dashboard.app)

    def scan(self, owner, app, kind="project", source=None):
        scan_id = str(uuid.uuid4())
        self.store.start(
            scan_id,
            app,
            ["static_orm"],
            {"commit": "x", "dirty": False},
            kind=kind,
            source=source or {"kind": "git", "origin": "https://github.com/o/r"},
            owner_id=owner,
        )
        self.store.finish(
            scan_id,
            findings=[FINDING],
            layer_seconds={},
            load_session=None,
            query_analytics=None,
            data_quality=None,
            schema_view={"declared": [], "actual": None, "divergence": None},
        )
        self.created.append(scan_id)
        return scan_id

    def get(self, who, path):
        return self.client.get(path, headers=self.h[who])

    def _unowned(self):
        rows = self.store.conn.execute(
            "SELECT scan_id::text FROM dashboard.scan WHERE kind = 'project' AND owner_id IS NULL"
        ).fetchall()
        return {r["scan_id"] for r in rows} if rows and isinstance(rows[0], dict) else set()

    def close(self):
        for scan_id in self.created:
            self.store.conn.execute("DELETE FROM dashboard.scan WHERE scan_id = %s", (scan_id,))
        # The suite shares a database with real data: leave every scan it did not create as found.
        after = self._unowned()
        self.store.close()
        assert after == self.before - set(self.created), (
            "a test changed who owns pre-existing scans"
        )


@pytest.fixture
def world():
    w = World()
    with w.client:
        yield w
    w.close()


def names(response):
    return [a["app"] for a in response.json()]


def test_a_project_is_visible_only_to_the_person_who_scanned_it(world):
    name = f"secret-{uuid.uuid4().hex[:6]}"
    world.scan(world.ids["alice"], name)
    assert name in names(world.get("alice", "/v1/apps"))
    assert name not in names(world.get("bob", "/v1/apps"))
    assert name not in names(world.get("admin", "/v1/apps")), "not even the administrator sees it"


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "/findings",
        "/findings/F001",
        "/findings/F001/explanation",
        "/queries",
        "/data-quality",
        "/schema",
    ],
)
def test_someone_elses_scan_is_a_404_on_every_route_never_a_403(world, suffix):
    scan_id = world.scan(world.ids["alice"], f"p-{uuid.uuid4().hex[:6]}")
    assert world.get("alice", f"/v1/scans/{scan_id}{suffix}").status_code != 404
    response = world.get("bob", f"/v1/scans/{scan_id}{suffix}")
    nothing = world.get("bob", f"/v1/scans/{uuid.uuid4()}{suffix}")
    assert response.status_code == 404, "existence must not leak"
    assert (response.status_code, response.json()) == (nothing.status_code, nothing.json())


def test_the_project_scan_list_and_rescan_and_delete_are_also_private(world):
    name = f"mine-{uuid.uuid4().hex[:6]}"
    scan_id = world.scan(world.ids["alice"], name)
    assert world.get("bob", f"/v1/apps/{name}/scans").status_code == 404
    assert (
        world.client.post(f"/v1/projects/{name}/rescan", headers=world.h["bob"]).status_code == 404
    )
    assert world.client.delete(f"/v1/projects/{name}", headers=world.h["bob"]).status_code == 404
    assert world.get("alice", f"/v1/scans/{scan_id}").status_code == 200, (
        "bob's attempts changed nothing"
    )


def test_two_users_can_use_the_same_project_name_without_seeing_each_other(world):
    name = f"same-{uuid.uuid4().hex[:6]}"
    a, b = world.scan(world.ids["alice"], name), world.scan(world.ids["bob"], name)
    assert [s["scan_id"] for s in world.get("alice", f"/v1/apps/{name}/scans").json()] == [a]
    assert [s["scan_id"] for s in world.get("bob", f"/v1/apps/{name}/scans").json()] == [b]


def test_deleting_a_project_removes_only_yours(world):
    name = f"gone-{uuid.uuid4().hex[:6]}"
    world.scan(world.ids["alice"], name)
    bobs = world.scan(world.ids["bob"], name)
    assert world.client.delete(f"/v1/projects/{name}", headers=world.h["alice"]).status_code == 204
    assert name not in names(world.get("alice", "/v1/apps"))
    assert world.get("bob", f"/v1/scans/{bobs}").status_code == 200


def test_built_in_apps_are_open_to_everyone_but_each_users_own_scans_are_theirs(world):
    app = dashboard.APPS[0]
    shared = world.scan(None, app, kind="app", source=None)  # a scan from before accounts existed
    alices = world.scan(world.ids["alice"], app, kind="app", source=None)
    for who in ("alice", "bob", "admin"):
        assert app in names(world.get(who, "/v1/apps"))
        assert world.get(who, f"/v1/scans/{shared}").status_code == 200, (
            "shared samples stay visible"
        )
    assert world.get("alice", f"/v1/scans/{alices}").status_code == 200
    assert world.get("bob", f"/v1/scans/{alices}").status_code == 404
    bob_list = [s["scan_id"] for s in world.get("bob", f"/v1/apps/{app}/scans").json()]
    assert shared in bob_list and alices not in bob_list


def test_a_legacy_project_scan_without_an_owner_belongs_to_nobody_until_claimed(world):
    name = f"legacy-{uuid.uuid4().hex[:6]}"
    scan_id = world.scan(None, name)
    for who in ("alice", "bob", "admin"):
        assert name not in names(world.get(who, "/v1/apps"))
        assert world.get(who, f"/v1/scans/{scan_id}").status_code == 404


def test_the_first_verified_account_inherits_projects_scanned_before_accounts(world):
    # Claiming re-owns EVERY unowned project scan, which in a shared database includes real ones.
    # So this runs inside a transaction that is always rolled back and touches nothing permanent.
    world.store.conn.live().autocommit = False
    try:
        name = f"inherit-{uuid.uuid4().hex[:6]}"
        scan_id = world.scan(None, name)
        assert world.store.claim_legacy_projects(world.ids["admin"]) >= 1
        assert name in names(world.get("admin", "/v1/apps"))
        assert world.get("admin", f"/v1/scans/{scan_id}").status_code == 200
        assert name not in names(world.get("bob", "/v1/apps"))
    finally:
        world.store.conn.live().rollback()
        world.store.conn.live().autocommit = True


@pytest.mark.parametrize(
    ("method", "route"),
    [
        ("get", "/v1/apps"),
        ("get", "/v1/apps/ecommerce/scans"),
        ("post", "/v1/apps/ecommerce/scans"),
        ("post", "/v1/projects/scans"),
        ("post", "/v1/projects/x/rescan"),
        ("delete", "/v1/projects/x"),
        ("get", f"/v1/scans/{uuid.uuid4()}"),
        ("get", f"/v1/scans/{uuid.uuid4()}/findings"),
        ("get", "/v1/auth/me"),
        ("get", "/v1/auth/sessions"),
    ],
)
def test_nothing_is_reachable_without_signing_in(world, method, route):
    response = getattr(world.client, method)(route, **({"json": {}} if method == "post" else {}))
    assert response.status_code == 401 and response.json()["code"] == "unauthenticated"


def test_a_bad_or_revoked_token_is_treated_as_signed_out(world):
    assert (
        world.client.get("/v1/apps", headers={"Authorization": "Bearer nonsense"}).status_code
        == 401
    )
    token = world.h["bob"]["Authorization"][7:]
    world.service.logout(token)
    assert world.client.get("/v1/apps", headers=world.h["bob"]).status_code == 401


def test_only_administrators_may_scan_a_folder_on_the_server(world, tmp_path):
    body = {"path": str(tmp_path / "missing")}
    assert (
        world.client.post("/v1/projects/scans", json=body, headers=world.h["bob"]).status_code
        == 403
    )
    assert (
        world.client.post("/v1/projects/scans", json=body, headers=world.h["admin"]).status_code
        == 422
    ), "allowed, but the folder is missing"
    assert world.get("bob", "/v1/auth/me").json()["can_scan_local"] is False
    assert world.get("admin", "/v1/auth/me").json()["can_scan_local"] is True


@pytest.mark.parametrize(
    "name", ["login", "register", "verify", "account", "api", "forgot-password", "reset-password"]
)
def test_a_project_cannot_take_the_name_of_a_dashboard_page(world, tmp_path, name):
    (tmp_path / "p").mkdir()
    response = world.client.post(
        "/v1/projects/scans",
        json={"path": str(tmp_path / "p"), "name": name},
        headers=world.h["admin"],
    )
    assert response.status_code == 422 and "reserved" in response.json()["detail"]


def test_the_session_hash_is_never_returned(world):
    assert "session" not in world.get("alice", "/v1/auth/me").json()
