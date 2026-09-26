"""One pipeline. A configuration only chooses which of its layers run.

`run_configuration` executes the enabled layers in a fixed order (cheapest first), times each,
hands every finding to the correlation engine together with the schema facts the enabled layers
produced, and scores the result against the ground-truth manifest. There is no per-configuration
branch anywhere in it: with fewer layers there is simply less evidence, and the correlation
engine passes findings through when it has nothing to correlate them with.
"""

import math
import resource
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from analyzers.correlate import SchemaFacts, correlate
from analyzers.dataquality.models import Window
from analyzers.finding import Finding
from analyzers.schema.actual import ActualSchema
from analyzers.schema.declared import DeclaredSchema
from experiments.groundtruth import Manifest, ScoreReport, score

from .layers import Configuration, Layer
from .metrics import ResultRow, build_rows


@dataclass(frozen=True)
class RunContext:
    app: str
    repetition: int
    #: Seed of this repetition's runtime workload: the one thing that varies between repetitions.
    seed: int
    app_dir: Path
    schema_path: Path
    app_database_url: str
    results_database_url: str
    #: Label of the clean, pre-injection profile series the data layer learns its ranges from.
    baseline_label: str
    #: The data window judged against that baseline.
    window: Window

    @property
    def schema_file(self) -> str:
        """How findings refer to the schema file: relative to the app directory."""
        return self.schema_path.relative_to(self.app_dir).as_posix()


@dataclass
class PipelineState:
    """What earlier layers of one run have produced, for later layers to use."""

    declared: DeclaredSchema | None = None
    actual: ActualSchema | None = None
    #: Scratch space for expensive shared work (e.g. the runtime capture), per run.
    cache: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LayerOutput:
    findings: list[Finding] = field(default_factory=list)
    declared: DeclaredSchema | None = None
    actual: ActualSchema | None = None


Provider = Callable[[RunContext, Configuration, PipelineState], LayerOutput]


@dataclass(frozen=True)
class RunResult:
    config: str
    app: str
    repetition: int
    findings: list[Finding]
    layer_findings: dict[str, list[Finding]]
    #: Seconds from the start of the run until each layer had produced its findings.
    available_at: dict[str, float]
    layer_wall_s: dict[str, float]
    layer_cpu_s: dict[str, float]
    correlation_wall_s: float
    wall_s: float
    cpu_s: float
    report: ScoreReport
    rows: list[ResultRow]
    load_session: str | None = None


def _cpu() -> float:
    """CPU seconds used so far by this process and its finished children (node, docker, ...)."""
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return time.process_time() + children.ru_utime + children.ru_stime


def run_configuration(
    config: Configuration,
    ctx: RunContext,
    manifest: Manifest,
    providers: Mapping[Layer, Provider],
    universe: Mapping[str, int],
) -> RunResult:
    state = PipelineState()
    started, cpu_started = time.perf_counter(), _cpu()

    layer_findings: dict[str, list[Finding]] = {}
    available_at: dict[str, float] = {}
    layer_wall: dict[str, float] = {}
    layer_cpu: dict[str, float] = {}
    for layer in config.ordered_layers():
        layer_started, layer_cpu_started = time.perf_counter(), _cpu()
        output = providers[layer](ctx, config, state)
        state.declared = output.declared if output.declared is not None else state.declared
        state.actual = output.actual if output.actual is not None else state.actual
        layer_findings[layer.value] = list(output.findings)
        layer_wall[layer.value] = time.perf_counter() - layer_started
        layer_cpu[layer.value] = _cpu() - layer_cpu_started
        available_at[layer.value] = time.perf_counter() - started

    correlation_started = time.perf_counter()
    everything = [f for findings in layer_findings.values() for f in findings]
    findings = correlate(
        everything, facts=SchemaFacts(declared=state.declared, actual=state.actual)
    ).findings
    correlation_wall = time.perf_counter() - correlation_started
    wall, cpu = time.perf_counter() - started, _cpu() - cpu_started

    report = score(findings, manifest)
    first_detection: dict[str, float] = {}
    for layer_name, layer_result in layer_findings.items():
        if layer_result:
            for match in score(layer_result, manifest).matches:
                seen = first_detection.get(match.entry_id, math.inf)
                first_detection[match.entry_id] = min(seen, available_at[layer_name])
    for match in report.matches:
        first_detection.setdefault(match.entry_id, wall)  # found only once the layers were combined

    return RunResult(
        config=config.name,
        app=ctx.app,
        repetition=ctx.repetition,
        findings=findings,
        layer_findings=layer_findings,
        available_at=available_at,
        layer_wall_s=layer_wall,
        layer_cpu_s=layer_cpu,
        correlation_wall_s=correlation_wall,
        wall_s=wall,
        cpu_s=cpu,
        report=report,
        rows=build_rows(
            report, manifest, findings, first_detection=first_detection, universe=universe
        ),
        load_session=state.cache.get("load_session"),
    )
