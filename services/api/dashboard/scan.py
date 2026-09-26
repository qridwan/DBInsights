"""Runs one scan: every evidence layer, correlated, plus the view snapshots.

A scan is the full hybrid pipeline (the ablation's C3 configuration) run against a live test
application. It reuses the ablation providers and the correlation engine, and does not score
against ground truth: a dashboard scan has no manifest.
"""

import time
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from analyzers.anomaly import detect_anomalies, load_series
from analyzers.anomaly.series import series_from_profile
from analyzers.correlate import SchemaFacts, correlate
from analyzers.dataquality import ProfileStore, profile_database
from analyzers.finding import Finding
from analyzers.schema import compare
from analyzers.schema.actual import connect, read_actual_schema
from experiments.ablation.experiment import context_for
from experiments.ablation.layers import CONFIGURATIONS, Layer
from experiments.ablation.pipeline import PipelineState, Provider, RunContext
from experiments.ablation.providers import default_providers
from experiments.ablation.store import code_state

from . import views
from .store import ScanStore

SCAN_CONFIGURATION = "C3"
SEED = 1


def _data_quality_snapshot(ctx: RunContext) -> list[dict[str, Any]]:
    profiles = ProfileStore(ctx.results_database_url)
    try:
        baseline = load_series(profiles, ctx.app, ctx.baseline_label)
    finally:
        profiles.close()
    with connect(ctx.app_database_url) as conn:
        profile = profile_database(conn, read_actual_schema(conn), window=ctx.window)
    analyses = detect_anomalies(
        baseline, series_from_profile(profile, ctx.window), window_start=ctx.window.start
    )
    return views.data_quality(analyses, profile.columns)


def run_scan(
    app: str,
    store: ScanStore,
    *,
    providers: Mapping[Layer, Provider] | None = None,
    log: Callable[[str], None] = lambda _: None,
) -> str:
    providers = providers or default_providers()
    config = CONFIGURATIONS[SCAN_CONFIGURATION]
    ctx = context_for(app, 1, SEED)
    scan_id = str(uuid.uuid4())
    store.start(scan_id, app, [layer.value for layer in config.ordered_layers()], code_state())
    try:
        state = PipelineState()
        layer_findings: list[Finding] = []
        seconds: dict[str, float] = {}
        for layer in config.ordered_layers():
            started = time.perf_counter()
            output = providers[layer](ctx, config, state)
            state.declared = output.declared or state.declared
            state.actual = output.actual or state.actual
            layer_findings += output.findings
            seconds[layer.value] = time.perf_counter() - started
            log(f"  {layer.value}: {len(output.findings)} findings in {seconds[layer.value]:.1f}s")

        correlated = correlate(
            layer_findings, facts=SchemaFacts(declared=state.declared, actual=state.actual)
        ).findings
        session = state.cache.get("load_session")
        store.finish(
            scan_id,
            findings=[
                f.model_dump(mode="json", by_alias=True, exclude_none=True) for f in correlated
            ],
            layer_seconds=seconds,
            load_session=session,
            query_analytics=views.query_analytics(ctx.results_database_url, app, session),
            data_quality=_data_quality_snapshot(ctx),
            schema_view=views.schema_view(
                state.declared, state.actual, compare(state.declared, state.actual)
            ),
        )
    except Exception as error:
        store.fail(scan_id, f"{type(error).__name__}: {error}")
        raise
    return scan_id
