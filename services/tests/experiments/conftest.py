from typing import Any

import pytest


def entry(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "ecom-n1-01",
        "problemType": "n_plus_one",
        "category": "performance",
        "file": "src/app/api/orders/route.ts",
        "line": 20,
        "endpoint": "GET /api/orders",
        "expectedRuleId": "N_PLUS_ONE_IN_LOOP",
        "description": "Per-order customer lookup inside a loop",
        "injectedAt": "2026-09-26T10:00:00Z",
    }
    base.update(overrides)
    return base


def data_entry(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "ecom-null-01",
        "problemType": "null_spike",
        "category": "data_quality",
        "table": "Customer",
        "column": "email",
        "expectedRuleId": "NULL_SPIKE",
        "description": "Recent customers missing email",
        "injectedAt": "2026-09-26T10:00:00Z",
    }
    base.update(overrides)
    return base


def manifest(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"schemaVersion": 1, "app": "ecommerce", "entries": list(entries)}


def finding(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schemaVersion": 1,
        "ruleId": "N_PLUS_ONE_IN_LOOP",
        "severity": "HIGH",
        "confidence": "HIGH",
        "file": "src/app/api/orders/route.ts",
        "line": 20,
        "title": "N+1",
        "body": "body",
        "evidence": [{"source": "STATIC_SOURCE", "description": "loop"}],
        "fingerprint": "fp-1",
    }
    base.update(overrides)
    return base


@pytest.fixture
def make_entry():
    return entry


@pytest.fixture
def make_data_entry():
    return data_entry


@pytest.fixture
def make_manifest():
    return manifest


@pytest.fixture
def make_finding():
    return finding
