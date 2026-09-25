import os
import uuid

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.storage import MemoryEventStore

IN_1 = 'SELECT "p"."id" FROM "public"."Product" AS "p" WHERE "p"."id" IN ($1) OFFSET $2'
IN_3 = 'SELECT "p"."id" FROM "public"."Product" AS "p" WHERE "p"."id" IN ($1,$2,$3) OFFSET $4'


def event(**overrides):
    base = {
        "schemaVersion": 1,
        "app": "ecommerce",
        "operationId": str(uuid.uuid4()),
        "requestId": "req-1",
        "route": "/api/orders/recent",
        "model": "Customer",
        "operation": "findUnique",
        "startedAt": "2026-09-26T10:00:00.000Z",
        "durationMs": 1.5,
        "rowsReturned": 1,
        "error": False,
        "statements": [
            {"sql": IN_1, "paramCount": 2, "kind": "query", "durationMs": 1.2, "rows": 1}
        ],
    }
    base.update(overrides)
    return base


@pytest.fixture
def client():
    app.state.store = MemoryEventStore()
    with TestClient(app) as test_client:
        yield test_client
    del app.state.store


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ingest_fingerprints_statements_and_groups_by_request(client):
    batch = [
        event(),
        event(
            statements=[
                {"sql": IN_3, "paramCount": 4, "kind": "query", "durationMs": 2.0, "rows": 3}
            ]
        ),
        event(requestId="req-2"),
    ]
    assert client.post("/v1/operations", json=batch).status_code == 202

    same_request = client.get("/v1/operations", params={"requestId": "req-1"}).json()
    assert len(same_request) == 2
    fingerprints = {op["statements"][0]["fingerprint"] for op in same_request}
    assert len(fingerprints) == 1, "IN lists of different arity share one fingerprint"
    assert {"requestId", "operationId", "durationMs", "rowsReturned"} <= set(same_request[0])
    assert {"normalizedSql", "paramCount", "durationMs"} <= set(same_request[0]["statements"][0])


def test_ingest_is_idempotent_per_operation_id(client):
    e = event()
    client.post("/v1/operations", json=[e])
    client.post("/v1/operations", json=[e])
    assert len(client.get("/v1/operations").json()) == 1


def test_rejects_events_that_break_the_contract(client):
    assert client.post("/v1/operations", json=[event(schemaVersion=2)]).status_code == 422
    assert client.post("/v1/operations", json=[event(unexpected=True)]).status_code == 422


URL = os.environ.get("DBINSIGHT_TEST_DATABASE_URL")


@pytest.mark.integration
@pytest.mark.skipif(not URL, reason="DBINSIGHT_TEST_DATABASE_URL not set")
def test_postgres_store_round_trip():
    import psycopg

    from api.events import OperationEvent
    from api.storage import PostgresEventStore

    schema = f"runtime_test_{uuid.uuid4().hex[:8]}"
    store = PostgresEventStore(URL, schema=schema)
    try:
        events = [
            OperationEvent.model_validate(event()),
            OperationEvent.model_validate(event(requestId="req-9")),
        ]
        assert store.ingest(events) == 2
        store.ingest(events)  # idempotent
        rows = store.operations(app="ecommerce", request_id="req-1", route=None, limit=10)
        assert len(rows) == 1
        assert rows[0]["requestId"] == "req-1"
        assert rows[0]["statements"][0]["fingerprint"]
        assert rows[0]["statements"][0]["normalizedSql"]
    finally:
        with psycopg.connect(URL, autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
