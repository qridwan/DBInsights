import copy
import os
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api.dashboard import app as dashboard
from api.dashboard.store import ScanStore

SCAN = str(uuid.uuid4())


def row(fid, rule, severity, confidence, layers, **over):
    base = {
        "scan_id": SCAN,
        "finding_id": fid,
        "rule_id": rule,
        "severity": severity,
        "confidence": confidence,
        "file": "src/a.ts",
        "line": 10,
        "end_line": None,
        "title": f"{rule} finding",
        "body": "body",
        "evidence": [{"source": layer, "description": f"from {layer}"} for layer in layers],
        "layers": layers,
        "suggested_fix": None,
        "fingerprint": f"fp-{fid}",
    }
    base.update(over)
    return base


ROWS = [
    row("F001", "N_PLUS_ONE_IN_LOOP", "HIGH", "HIGH", ["STATIC_SOURCE", "RUNTIME", "SQL"]),
    row("F002", "MISSING_PAGINATION", "MEDIUM", "MEDIUM", ["STATIC_SOURCE"]),
    row("F003", "NULL_SPIKE", "MEDIUM", "LOW", ["DATA_QUALITY"]),
]


class FakeStore:
    def __init__(self):
        self.rows = copy.deepcopy(ROWS)
        self.scan_row = {
            "scan_id": SCAN,
            "app": "ecommerce",
            "started_at": datetime(2026, 9, 26, tzinfo=UTC),
            "finished_at": datetime(2026, 9, 26, tzinfo=UTC),
            "status": "ok",
            "error": None,
            "layers": ["static_orm"],
            "layer_seconds": {"static_orm": 1.0},
            "git_commit": "abc",
            "git_dirty": False,
            "query_analytics": {"statements": 3},
            "data_quality": [{"table": "T"}],
            "schema_view": {"declared": [], "actual": []},
        }

    def scans(self, app=None, limit=50):
        counts = {"high": 1, "medium": 2, "low": 0, "total": 3}
        return [
            {**{k: self.scan_row[k] for k in ("scan_id", "app", "started_at", "status")}, **counts}
        ]

    def scan(self, scan_id):
        if scan_id != SCAN:
            if scan_id == "not-a-uuid":
                raise ValueError("bad uuid")
            return None
        return self.scan_row

    def findings(self, scan_id):
        return self.rows

    def finding(self, scan_id, finding_id):
        return next((r for r in self.rows if r["finding_id"] == finding_id), None)


@pytest.fixture
def client():
    dashboard.app.state.store = FakeStore()
    dashboard.app.state.__dict__.pop("explainer", None)
    with TestClient(dashboard.app) as c:
        yield c


def test_findings_are_filterable_by_severity_confidence_rule_and_layer(client):
    def ids(query):
        return [f["finding_id"] for f in client.get(f"/v1/scans/{SCAN}/findings?{query}").json()]

    assert ids("") == ["F001", "F002", "F003"]
    assert ids("severity=high") == ["F001"]
    assert ids("severity=MEDIUM") == ["F002", "F003"]
    assert ids("confidence=low") == ["F003"]
    assert ids("rule=MISSING_PAGINATION") == ["F002"]
    assert ids("layer=runtime") == ["F001"]
    assert ids("severity=medium&layer=data_quality") == ["F003"]
    assert ids("severity=high&rule=NULL_SPIKE") == []


def test_a_finding_is_served_exactly_as_stored_with_its_evidence_layers_labelled(client):
    served = client.get(f"/v1/scans/{SCAN}/findings/F001").json()
    stored = ROWS[0]
    assert served == stored
    assert {e["source"] for e in served["evidence"]} == set(served["layers"])


def test_reading_findings_never_changes_them(client):
    before = copy.deepcopy(client.app.state.store.rows)
    client.get(f"/v1/scans/{SCAN}/findings")
    client.get(f"/v1/scans/{SCAN}/findings/F002")
    assert client.app.state.store.rows == before


def test_unknown_things_are_404(client):
    assert client.get("/v1/scans/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/v1/scans/not-a-uuid/findings").status_code == 404
    assert client.get(f"/v1/scans/{SCAN}/findings/F999").status_code == 404
    assert client.get("/v1/apps/no-such-app/scans").status_code == 404
    assert client.post("/v1/apps/no-such-app/scans").status_code == 404


def test_the_snapshots_are_served_per_scan(client):
    assert client.get(f"/v1/scans/{SCAN}/queries").json() == {"statements": 3}
    assert client.get(f"/v1/scans/{SCAN}/data-quality").json() == [{"table": "T"}]
    assert client.get(f"/v1/scans/{SCAN}/schema").json() == {"declared": [], "actual": []}


def test_the_summary_carries_counts_and_layer_timings(client):
    summary = client.get(f"/v1/scans/{SCAN}").json()
    assert summary["counts"] == {"high": 1, "medium": 2, "low": 0, "total": 3}
    assert summary["layer_seconds"] == {"static_orm": 1.0}


def test_the_explanation_is_unavailable_not_broken_without_a_key(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = client.get(f"/v1/scans/{SCAN}/findings/F001/explanation")
    assert response.status_code == 503 and "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_an_explanation_never_alters_the_stored_finding(client):
    from api.explain import Explainer

    class Fake:
        name = "fake"

        def complete(self, system, user):
            return '{"explanation": "e", "recommendation": "r"}'

    client.app.state.explainer = Explainer(Fake())
    before = copy.deepcopy(client.app.state.store.rows)
    response = client.get(f"/v1/scans/{SCAN}/findings/F001/explanation")
    assert response.status_code == 200
    assert response.json() == {"explanation": "e", "recommendation": "r"}
    assert client.app.state.store.rows == before


def test_only_one_scan_runs_at_a_time(client):
    assert dashboard._scan_lock.acquire(blocking=False)
    try:
        assert client.post("/v1/apps/ecommerce/scans").status_code == 409
    finally:
        dashboard._scan_lock.release()


# ---- the real store (needs the results database) ----------------------------------------------


def test_scan_store_round_trip():
    url = os.environ.get("DBINSIGHT_TEST_DATABASE_URL") or os.environ.get(
        "DBINSIGHT_RESULTS_DATABASE_URL"
    )
    if not url:
        pytest.skip("no database configured")
    try:
        store = ScanStore(url)
    except Exception as error:
        pytest.skip(f"database unreachable: {error}")
    scan_id = str(uuid.uuid4())
    finding = {
        "ruleId": "N_PLUS_ONE_IN_LOOP",
        "severity": "HIGH",
        "confidence": "MEDIUM",
        "file": "a.ts",
        "line": 3,
        "title": "t",
        "body": "b",
        "evidence": [
            {"source": "RUNTIME", "description": "d"},
            {"source": "SQL", "description": "q"},
        ],
        "fingerprint": "fp",
    }
    low = {**finding, "severity": "LOW", "line": 1, "fingerprint": "fp2"}
    try:
        store.start(scan_id, "test-app", ["static_orm"], {"commit": "x", "dirty": False})
        store.finish(
            scan_id,
            findings=[low, finding],
            layer_seconds={"static_orm": 0.1},
            load_session=None,
            query_analytics={"statements": 1},
            data_quality=[],
            schema_view={},
        )
        rows = store.findings(scan_id)
        assert [r["finding_id"] for r in rows] == ["F001", "F002"]
        assert rows[0]["severity"] == "HIGH", "most severe first"
        assert rows[0]["layers"] == ["RUNTIME", "SQL"]
        summary = store.scans("test-app")[0]
        assert (summary["high"], summary["low"], summary["total"]) == (1, 1, 2)
        assert store.latest_scan_id("test-app") == scan_id
    finally:
        store.conn.execute("DELETE FROM dashboard.scan WHERE scan_id = %s", (scan_id,))
        store.close()
