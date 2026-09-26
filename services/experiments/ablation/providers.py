"""The real provider for each layer: thin adapters over the analyzers that already exist.

Each provider does one layer's work from raw inputs every time it is called (no caching between
repetitions), so its cost is what the layer really costs.
"""

import logging

from analyzers import core_bridge
from analyzers.anomaly import detect_anomalies, load_series
from analyzers.anomaly import to_findings as anomaly_findings
from analyzers.anomaly.series import series_from_profile
from analyzers.dataquality import ProfileStore, check_integrity, profile_database
from analyzers.dataquality.integrity import to_findings as integrity_findings
from analyzers.finding import parse_findings
from analyzers.runtime import detect_n_plus_one
from analyzers.runtime.__main__ import load_operations
from analyzers.runtime.n_plus_one import Operation
from analyzers.schema import (
    compare,
    load_declared_schema,
    read_actual_schema,
)
from analyzers.schema import (
    to_findings as divergence_findings,
)
from analyzers.schema.actual import connect
from analyzers.sql import SqlStatement, analyze_statements, statements_from_repository
from experiments.load import harness as load

from .layers import Configuration, Layer
from .pipeline import LayerOutput, PipelineState, Provider, RunContext

log = logging.getLogger(__name__)

#: How many times the load harness sends its request sequence in one runtime capture.
LOAD_REPETITIONS = 3


class RuntimeCapture:
    """One fresh load run against the live app; its operations, as the collector recorded them."""

    def __init__(self, ctx: RunContext, state: PipelineState) -> None:
        config = load.Config.from_env(
            ctx.app,
            seed=ctx.seed,
            repetitions=LOAD_REPETITIONS,
            app_database_url=ctx.app_database_url,
            results_database_url=ctx.results_database_url,
        )
        if not load.collector_enabled_in_container(ctx.app):
            raise RuntimeError(
                f"{ctx.app}: the collector is switched off; the runtime layer needs it on"
            )
        store = load.ResultsStore(config.results_database_url)
        try:
            session = load.start_session(store, config, "ablation", repetition=ctx.repetition)
            outcome = load.run_once(
                store,
                config,
                load.plan(config),
                session_id=session,
                block=0,
                warmup=False,
                collector_enabled=True,
                sample_resources=False,
            )
            store.finish_session(session)
        finally:
            store.close()
        if outcome["recorded_operations"] == 0:
            raise RuntimeError(f"{ctx.app}: the load run recorded no operations")
        state.cache["load_session"] = session
        self.operations: list[Operation] = load_operations(
            ctx.results_database_url, ctx.app, session
        )


def _runtime(ctx: RunContext, state: PipelineState) -> RuntimeCapture:
    if "runtime" not in state.cache:
        state.cache["runtime"] = RuntimeCapture(ctx, state)
    return state.cache["runtime"]


def static_orm(ctx: RunContext, config: Configuration, state: PipelineState) -> LayerOutput:
    # The declared schema is a separate layer: without it the analyzer runs blind to indexes.
    schema = ctx.schema_path if config.uses(Layer.DECLARED) else None
    return LayerOutput(findings=parse_findings(core_bridge.analyze(ctx.app_dir, schema)))


def sql(ctx: RunContext, config: Configuration, state: PipelineState) -> LayerOutput:
    if config.sql_source == "captured":
        statements = [
            SqlStatement(sql=s.normalized_sql, route=op.route)
            for op in _runtime(ctx, state).operations
            if op.route
            for s in op.statements
        ]
    else:
        statements = statements_from_repository(ctx.app_dir)
    return LayerOutput(findings=analyze_statements(statements))


def declared(ctx: RunContext, config: Configuration, state: PipelineState) -> LayerOutput:
    return LayerOutput(declared=load_declared_schema(ctx.schema_path))


def actual(ctx: RunContext, config: Configuration, state: PipelineState) -> LayerOutput:
    with connect(ctx.app_database_url) as conn:
        schema = read_actual_schema(conn)
    # Divergence is the comparison of the two schemas, so it exists only where both are enabled.
    findings = (
        divergence_findings(compare(state.declared, schema), ctx.schema_file)
        if state.declared
        else []
    )
    return LayerOutput(findings=findings, actual=schema)


def runtime(ctx: RunContext, config: Configuration, state: PipelineState) -> LayerOutput:
    return LayerOutput(findings=detect_n_plus_one(_runtime(ctx, state).operations))


def data(ctx: RunContext, config: Configuration, state: PipelineState) -> LayerOutput:
    store = ProfileStore(ctx.results_database_url)
    try:
        baseline = load_series(store, ctx.app, ctx.baseline_label)
    finally:
        store.close()
    if not baseline:
        raise RuntimeError(
            f"no baseline profiles labelled {ctx.baseline_label!r} for {ctx.app}; run setup"
        )
    with connect(ctx.app_database_url) as conn:
        schema = read_actual_schema(
            conn
        )  # the profiler's own table list, not the actual-schema layer
        profile = profile_database(conn, schema, window=ctx.window)
        integrity = []
        if state.declared and state.actual:
            checks, _ = check_integrity(conn, state.declared, state.actual)
            integrity = integrity_findings(checks, ctx.schema_file)
    current = series_from_profile(profile, ctx.window)
    anomalies = detect_anomalies(baseline, current, window_start=ctx.window.start)
    return LayerOutput(findings=[*anomaly_findings(anomalies), *integrity])


def default_providers() -> dict[Layer, Provider]:
    return {
        Layer.STATIC_ORM: static_orm,
        Layer.SQL: sql,
        Layer.DECLARED: declared,
        Layer.ACTUAL: actual,
        Layer.RUNTIME: runtime,
        Layer.DATA: data,
    }
