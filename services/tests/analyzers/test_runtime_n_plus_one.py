import pytest

from analyzers.runtime import Operation, detect_n_plus_one
from analyzers.runtime.n_plus_one import Statement
from experiments.groundtruth import Manifest, score


def op(
    request: str | None,
    *fingerprints: str,
    route: str | None = "/api/orders/recent",
    app: str = "shop",
) -> Operation:
    return Operation(
        app=app,
        request_id=request,
        route=route,
        model="Customer",
        operation="findUnique",
        statements=tuple(Statement(fp, f"SELECT {fp}") for fp in fingerprints),
    )


def repeated(request: str, fp: str, times: int, **kw) -> list[Operation]:
    return [op(request, fp, **kw) for _ in range(times)]


def test_fires_when_one_shape_exceeds_the_threshold_in_one_request():
    findings = detect_n_plus_one(repeated("r1", "fp-customer", 3), threshold=2)
    assert [f.rule_id for f in findings] == ["RUNTIME_N_PLUS_ONE"]
    data = findings[0].evidence[0].data
    assert data["route"] == "/api/orders/recent"
    assert data["maxExecutionsPerRequest"] == 3
    assert data["threshold"] == 2


def test_exactly_the_threshold_does_not_fire():
    assert detect_n_plus_one(repeated("r1", "fp", 2), threshold=2) == []


def test_repetition_spread_across_requests_is_not_an_n_plus_one():
    ops = [op(f"r{i}", "fp") for i in range(10)]
    assert detect_n_plus_one(ops, threshold=2) == []


def test_distinct_shapes_in_one_request_are_counted_separately():
    ops = [op("r1", "a"), op("r1", "b"), op("r1", "c"), op("r1", "a"), op("r1", "b")]
    assert detect_n_plus_one(ops, threshold=2) == []


def test_operations_outside_a_request_are_ignored():
    assert detect_n_plus_one(repeated(None, "fp", 50, route=None), threshold=2) == []


def test_one_finding_per_route_and_shape_with_evidence_across_requests():
    ops = repeated("r1", "fp", 20) + repeated("r2", "fp", 20) + [op("r3", "other")]
    findings = detect_n_plus_one(ops, threshold=2)
    assert len(findings) == 1
    data = findings[0].evidence[0].data
    assert (data["requestsAffected"], data["requestsObserved"]) == (2, 3)
    assert findings[0].confidence == "HIGH"


def test_small_fan_out_is_medium_confidence():
    assert detect_n_plus_one(repeated("r1", "fp", 4), threshold=2)[0].confidence == "MEDIUM"


def test_fingerprint_is_stable_and_independent_of_counts():
    first = detect_n_plus_one(repeated("r1", "fp", 5), threshold=2)[0]
    second = detect_n_plus_one(repeated("r9", "fp", 50), threshold=2)[0]
    assert first.fingerprint == second.fingerprint


def test_threshold_must_be_positive():
    with pytest.raises(ValueError):
        detect_n_plus_one([], threshold=0)


def test_runtime_findings_score_against_manifest_endpoints():
    manifest = Manifest.model_validate(
        {
            "schemaVersion": 1,
            "app": "shop",
            "entries": [
                {
                    "id": "n1",
                    "problemType": "n_plus_one",
                    "category": "performance",
                    "file": "src/app/api/orders/[id]/invoice/route.ts",
                    "line": 27,
                    "endpoint": "GET /api/orders/:id/invoice",
                    "expectedRuleId": "N_PLUS_ONE_IN_LOOP",
                    "description": "d",
                    "injectedAt": "2026-09-26T00:00:00Z",
                }
            ],
        }
    )
    findings = detect_n_plus_one(
        repeated("r1", "fp", 4, route="/api/orders/[id]/invoice"), threshold=2
    )
    result = score(findings, manifest)
    assert (result.aggregate.tp, result.aggregate.fp, result.aggregate.fn) == (1, 0, 0)
