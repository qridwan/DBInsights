import pytest

from experiments.groundtruth import Manifest, load_manifest
from experiments.load.harness import MANIFESTS
from experiments.load.sequence import (
    build_sequence,
    load_param_sources,
    placeholders,
    resolve_candidates,
    route_pattern,
)


def manifest(*endpoints: str) -> Manifest:
    return Manifest.model_validate(
        {
            "schemaVersion": 1,
            "app": "t",
            "entries": [
                {
                    "id": f"e{i}",
                    "problemType": "n_plus_one",
                    "category": "performance",
                    "file": "f.ts",
                    "line": 1,
                    "endpoint": endpoint,
                    "expectedRuleId": "N_PLUS_ONE_IN_LOOP",
                    "description": "d",
                    "injectedAt": "2026-09-26T00:00:00Z",
                }
                for i, endpoint in enumerate(endpoints)
            ],
        }
    )


CANDIDATES = {
    "orders/:id": ["o1", "o2", "o3"],
    "tags/:slug": ["a b", "c"],
    "?email=": ["x@y.z", "q@r.s"],
}


@pytest.mark.parametrize(
    ("endpoint", "route"),
    [
        ("GET /api/orders/:id/invoice", "/api/orders/[id]/invoice"),
        ("GET /api/orders?status=PENDING", "/api/orders"),
        ("GET /api/feed", "/api/feed"),
    ],
)
def test_route_pattern_matches_the_collectors_next_route(endpoint, route):
    assert route_pattern(endpoint) == route


def test_placeholders_cover_path_and_empty_query_parameters():
    assert placeholders("GET /api/orders/:id/invoice") == ["orders/:id"]
    assert placeholders("GET /api/comments?email=") == ["?email="]
    assert placeholders("GET /api/reviews?rating=1") == []


def test_same_seed_same_sequence_and_every_endpoint_each_repetition():
    m = manifest(
        "GET /api/orders/:id/invoice",
        "GET /api/tags/:slug/posts",
        "GET /api/comments?email=",
        "GET /api/feed",
    )
    first = build_sequence(m, CANDIDATES, seed=7, repetitions=3)
    assert first == build_sequence(m, CANDIDATES, seed=7, repetitions=3)
    assert len(first) == 12
    assert [r.entry_id for r in first[:4]] == ["e0", "e1", "e2", "e3"]
    assert build_sequence(m, CANDIDATES, seed=8, repetitions=3) != first


def test_values_are_substituted_and_url_encoded():
    m = manifest("GET /api/tags/:slug/posts", "GET /api/comments?email=")
    paths = {r.path for r in build_sequence(m, CANDIDATES, seed=1, repetitions=20)}
    assert paths <= {
        "/api/tags/a%20b/posts",
        "/api/tags/c/posts",
        "/api/comments?email=x%40y.z",
        "/api/comments?email=q%40r.s",
    }
    assert not any(":" in p.split("?")[0] for p in paths)


def test_missing_parameter_values_fail_loudly():
    with pytest.raises(ValueError, match="orders/:id"):
        build_sequence(manifest("GET /api/orders/:id/invoice"), {}, seed=1, repetitions=1)


@pytest.mark.parametrize("app", ["ecommerce", "blog"])
def test_params_json_covers_every_committed_manifest_endpoint(app):
    committed = load_manifest(MANIFESTS / f"{app}.json")
    resolve_candidates(app, lambda _query: ["value"], committed)  # raises if a source is missing
    assert load_param_sources(app)
