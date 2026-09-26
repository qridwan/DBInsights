import os
import uuid
from pathlib import Path

import pytest

from analyzers.finding import Finding
from experiments.ablation.layers import (
    ABLATION,
    CONFIGURATIONS,
    EXECUTION_ORDER,
    SENSITIVITY,
    Layer,
)
from experiments.ablation.metrics import UNMAPPED, build_rows
from experiments.ablation.pipeline import LayerOutput, RunContext, run_configuration
from experiments.groundtruth import Manifest, parse_findings, score

# ---- the configurations are data, not code paths ----------------------------------------------


def test_ablation_is_a_strictly_nested_chain():
    chain = [CONFIGURATIONS[name].layers for name in ("B1", "B2", "C1", "C2", "C3")]
    for smaller, larger in zip(chain, chain[1:], strict=False):
        assert smaller < larger
    assert CONFIGURATIONS["A"].layers < CONFIGURATIONS["B1"].layers


def test_six_configurations_plus_one_sensitivity_arm():
    assert ABLATION == ("A", "B1", "B2", "C1", "C2", "C3")
    assert SENSITIVITY == ("A-log",)


def test_each_step_adds_exactly_the_layer_it_is_named_for():
    added = {
        ("B1", "A"): {Layer.STATIC_ORM},
        ("B2", "B1"): {Layer.DECLARED},
        ("C1", "B2"): {Layer.ACTUAL},
        ("C2", "C1"): {Layer.RUNTIME},
        ("C3", "C2"): {Layer.DATA},
    }
    for (bigger, smaller), layer in added.items():
        assert CONFIGURATIONS[bigger].layers - CONFIGURATIONS[smaller].layers == layer


def test_every_layer_has_an_execution_slot():
    assert set(EXECUTION_ORDER) == set(Layer)


# ---- one pipeline, driven by the configuration -------------------------------------------------


def _ctx(tmp_path: Path) -> RunContext:
    from datetime import UTC, datetime

    from analyzers.dataquality import Window

    return RunContext(
        app="ecommerce",
        repetition=1,
        seed=1,
        app_dir=tmp_path,
        schema_path=tmp_path / "prisma" / "schema.prisma",
        app_database_url="",
        results_database_url="",
        baseline_label="x",
        window=Window(start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 2, 1, tzinfo=UTC)),
    )


def _finding(make_finding, **overrides) -> Finding:
    return parse_findings([make_finding(**overrides)])[0]


def _manifest(make_manifest, make_entry):
    return Manifest.model_validate(make_manifest(make_entry()))


def test_only_enabled_layers_run(tmp_path, make_finding, make_manifest, make_entry):
    called: list[Layer] = []

    def provider(layer):
        def run(ctx, config, state):
            called.append(layer)
            return LayerOutput(findings=[])

        return run

    providers = {layer: provider(layer) for layer in Layer}
    run_configuration(
        CONFIGURATIONS["B2"], _ctx(tmp_path), _manifest(make_manifest, make_entry), providers, {}
    )
    assert called == [Layer.STATIC_ORM, Layer.SQL, Layer.DECLARED]


def test_detection_latency_is_the_first_layer_that_matched(
    tmp_path, make_finding, make_manifest, make_entry
):
    hit = _finding(make_finding)

    def empty(ctx, config, state):
        return LayerOutput()

    def orm(ctx, config, state):
        return LayerOutput(findings=[hit])

    providers = {layer: empty for layer in Layer} | {Layer.STATIC_ORM: orm}
    result = run_configuration(
        CONFIGURATIONS["C1"], _ctx(tmp_path), _manifest(make_manifest, make_entry), providers, {}
    )
    assert result.report.aggregate.tp == 1
    row = next(r for r in result.rows if r.problem_type == "n_plus_one")
    assert row.detection_latency_s == pytest.approx(result.available_at["static_orm"])
    assert result.available_at["static_orm"] <= result.available_at["actual"]


def test_a_configuration_without_findings_misses_everything(tmp_path, make_manifest, make_entry):
    providers = {layer: (lambda ctx, config, state: LayerOutput()) for layer in Layer}
    result = run_configuration(
        CONFIGURATIONS["A"], _ctx(tmp_path), _manifest(make_manifest, make_entry), providers, {}
    )
    assert (result.report.aggregate.tp, result.report.aggregate.fn) == (0, 1)


# ---- metrics -------------------------------------------------------------------------------------


def test_rows_use_the_shared_negative_universe_for_fpr(make_finding, make_manifest, make_entry):
    manifest = Manifest.model_validate(make_manifest(make_entry()))
    findings = parse_findings(
        [
            make_finding(),
            make_finding(fingerprint="fp-2", line=99),
        ]
    )
    report = score(findings, manifest)
    rows = build_rows(
        report, manifest, findings, first_detection={"ecom-n1-01": 2.0}, universe={"n_plus_one": 11}
    )
    row = next(r for r in rows if r.problem_type == "n_plus_one")
    assert (row.tp, row.fp, row.fn, row.entries) == (1, 1, 0, 1)
    assert row.fpr == pytest.approx(1 / 10)  # 11 routes, 1 of them really has the problem
    assert row.precision == 0.5
    assert row.mean_tp_confidence == 3
    assert row.detection_latency_s == 2.0


def test_fpr_is_undefined_without_a_universe(make_finding, make_manifest, make_entry):
    manifest = Manifest.model_validate(make_manifest(make_entry()))
    findings = parse_findings([make_finding(line=99)])
    rows = build_rows(
        score(findings, manifest), manifest, findings, first_detection={}, universe={}
    )
    assert next(r for r in rows if r.problem_type == "n_plus_one").fpr is None


def test_findings_that_map_to_no_problem_type_are_reported_as_unmapped(
    make_finding, make_manifest, make_entry
):
    manifest = Manifest.model_validate(make_manifest(make_entry()))
    findings = parse_findings(
        [make_finding(), make_finding(ruleId="SOMETHING_ELSE", fingerprint="z")]
    )
    rows = build_rows(
        score(findings, manifest), manifest, findings, first_detection={}, universe={}
    )
    assert any(r.problem_type == UNMAPPED and r.fp == 1 for r in rows)


# ---- results store: raw rows, one per (config, app, repetition, problem type) -------------------


@pytest.fixture
def store():
    from experiments.ablation.store import AblationStore

    url = os.environ.get("RESULTS_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        try:
            from experiments.ablation.experiment import _urls

            url = _urls("blog")[1]
        except Exception:  # pragma: no cover - no configuration at all
            pytest.skip("no results database configured")
    try:
        s = AblationStore(url)
    except Exception as error:
        pytest.skip(f"results database unreachable: {error}")
    yield s
    s.close()


def test_store_writes_raw_rows_and_never_aggregates(
    store, tmp_path, make_finding, make_manifest, make_entry
):
    hit = _finding(make_finding)
    providers = {layer: (lambda ctx, config, state: LayerOutput()) for layer in Layer} | {
        Layer.STATIC_ORM: lambda ctx, config, state: LayerOutput(findings=[hit])
    }
    config = CONFIGURATIONS["B1"]
    experiment = str(uuid.uuid4())
    store.start_experiment(
        experiment,
        repetitions=2,
        seed=1,
        apps=["ecommerce"],
        configurations={"B1": config},
        universe={"ecommerce": {"n_plus_one": 5}},
        parameters={},
    )
    for repetition in (1, 2):
        ctx = _ctx(tmp_path)
        ctx = RunContext(**{**ctx.__dict__, "repetition": repetition})
        result = run_configuration(
            config, ctx, _manifest(make_manifest, make_entry), providers, {"n_plus_one": 5}
        )
        store.add_run(experiment, str(uuid.uuid4()), result, sensitivity=False)
    store.finish_experiment(experiment)
    try:
        _assert_raw_rows(store, experiment)
    finally:
        # The test wrote to the real results database; leave no trace in it.
        store.conn.execute(
            "DELETE FROM ablation.experiment WHERE experiment_id = %s", (experiment,)
        )
        store.conn.commit()


def _assert_raw_rows(store, experiment):
    rows = store.results(experiment)
    keys = [(r["config"], r["app"], r["repetition"], r["problem_type"]) for r in rows]
    assert len(keys) == len(set(keys)) == 2
    assert {r["repetition"] for r in rows} == {1, 2}
    assert all(r["tp"] == 1 and r["precision"] == 1.0 for r in rows)
    assert len(store.runs(experiment)) == 2
