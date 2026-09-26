"""The correlation engine: many layers' findings in, single scored findings out.

Layers report independently: static analysis, the declared schema, runtime, the actual schema,
data quality. A problem often shows up in several of them, and they can disagree. This engine
joins their findings on what they are about, weighs the evidence, and emits one finding per
problem, carrying the evidence of every layer that contributed, each item naming its layer.

Hypotheses compete
------------------
At a *site* (one request route and one model) the engine may hold several explanations for the
same symptom, e.g. "N+1" and "missing index". Each hypothesis is scored from the evidence for
and against it (see `scoring`). A hypothesis whose log-odds fall below the belief line is
eliminated, and if another hypothesis at the site survives, the finding's TYPE changes to it:
contradicting evidence does not merely lower a confidence, it can replace the diagnosis. The
eliminated alternative is not lost: its evidence stays on the surviving finding, tagged
`ruled_out`, so the reasoning can be audited.

Every evidence item on an emitted finding carries `data.correlation`:
`{role, hypothesis, weightNats, posterior}`, with role one of `supports`, `contradicts`,
`ruled_out` (belongs to an eliminated alternative), or `context` (weight 0).

Rules implemented
-----------------
F1  Missing index vs N+1 (static + declared + runtime + actual schema).
    - A static MISSING_INDEX finding rests on the DECLARED schema. The ACTUAL schema can
      contradict it (an index exists in the database that schema.prisma does not declare) or
      confirm it. With no actual schema, the finding is left as it is.
    - Runtime repetition of one query shape within a request corroborates N+1.
F2  Orphaned rows (data quality + declared + actual schema). Orphans are explained when the
    database has no foreign-key constraint on the relation, and contradicted when it enforces
    one. This changes confidence only.
Everything else passes through unchanged: a layer with no counterpart has nothing to correlate.

Static and runtime findings are recognised as the same request through the Next.js App Router
convention (route.ts <-> /route); a static finding outside a route handler cannot be joined to
runtime and is judged by the schema layers alone.

Reproducible: the input is put in a canonical order, weights are combined order-independently,
and nothing random or time-dependent is involved.
"""

import hashlib
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from ..finding import Evidence, Finding
from . import scoring
from .facts import SchemaFacts, route_for_file, sql_filter_columns

N_PLUS_ONE = "N_PLUS_ONE_IN_LOOP"
RUNTIME_N_PLUS_ONE = "RUNTIME_N_PLUS_ONE"
MISSING_INDEX = "MISSING_INDEX_ON_FILTERED_FIELD"
ORPHANED_FOREIGN_KEY = "ORPHANED_FOREIGN_KEY"

Role = Literal["supports", "contradicts", "ruled_out", "context"]


@dataclass(frozen=True)
class Contribution:
    """One piece of evidence and what it does to a hypothesis."""

    layer: str
    role: Role
    weight: float
    evidence: Evidence
    #: Fingerprint of the input finding the evidence came from; None if the engine derived it.
    finding: str | None = None


@dataclass(frozen=True)
class HypothesisScore:
    rule_id: str
    contributions: tuple[Contribution, ...]
    logit: float
    posterior: float
    confidence: scoring.Confidence
    #: Whether the hypothesis became an output finding.
    emitted: bool = False


@dataclass(frozen=True)
class Decision:
    """How one site was resolved: every hypothesis considered and the verdict on each."""

    site: str
    hypotheses: tuple[HypothesisScore, ...]
    #: The rule id of the input finding whose diagnosis was replaced, if any.
    type_changed_from: str | None = None
    #: Fingerprints of input findings folded into output findings or eliminated.
    consumed: tuple[str, ...] = ()


@dataclass(frozen=True)
class CorrelationResult:
    findings: list[Finding]
    decisions: list[Decision] = field(default_factory=list)


# ---- reading findings --------------------------------------------------------------------------


def _order_key(f: Finding) -> tuple[Any, ...]:
    return (f.file, f.line, f.rule_id, f.fingerprint, f.model_dump_json())


def _evidence(f: Finding, source: str) -> Evidence | None:
    return next((e for e in f.evidence if e.source == source), None)


def _data(e: Evidence | None) -> dict[str, Any]:
    return dict(e.data or {}) if e else {}


def _static_model(f: Finding) -> str | None:
    model = _data(_evidence(f, "STATIC_SOURCE")).get("model")
    return model if isinstance(model, str) else None


def _runtime_site(f: Finding) -> tuple[str | None, str | None]:
    data = _data(_evidence(f, "RUNTIME"))
    route, model = data.get("route"), data.get("model")
    return (route if isinstance(route, str) else None, model if isinstance(model, str) else None)


# ---- scoring -----------------------------------------------------------------------------------


def _raising(f: Finding, weight: float) -> list[Contribution]:
    """The finding's own evidence. Its confidence is counted once, on the first item."""
    return [
        Contribution(e.source, "supports", weight if i == 0 else 0.0, e, f.fingerprint)
        for i, e in enumerate(f.evidence)
    ]


def _score(rule_id: str, contributions: Sequence[Contribution]) -> HypothesisScore:
    logit = scoring.combine(
        c.weight for c in contributions if c.role in ("supports", "contradicts")
    )
    return HypothesisScore(
        rule_id=rule_id,
        contributions=tuple(contributions),
        logit=logit,
        posterior=scoring.posterior(logit),
        confidence=scoring.confidence_for(logit),
    )


def _tag(c: Contribution, *, role: Role, hypothesis: HypothesisScore) -> Evidence:
    e = c.evidence
    correlation = {
        "role": role,
        "hypothesis": hypothesis.rule_id,
        "weightNats": c.weight,
        "posterior": hypothesis.posterior,
    }
    return Evidence(
        source=e.source,
        description=e.description,
        file=e.file,
        line=e.line,
        data={**(e.data or {}), "correlation": correlation},
    )


def _note(h: HypothesisScore) -> str:
    lines = [
        f"- {c.layer}: {c.evidence.description} ({c.weight:+.1f})"
        for c in h.contributions
        if c.weight != 0
    ]
    return (
        f"**Correlation:** {h.posterior:.2f} ({h.confidence}), from the evidence below, "
        "in nats of log-odds:\n" + "\n".join(lines)
    )


# ---- F1: missing index vs N+1 ------------------------------------------------------------------


def _evaluate_missing_index(f: Finding, facts: SchemaFacts) -> HypothesisScore | None:
    """Weighs a static missing-index finding against the actual schema; None if that has no view."""
    declared = _data(_evidence(f, "DECLARED_SCHEMA"))
    table, columns = declared.get("table"), declared.get("columns")
    if (
        facts.actual is None
        or not isinstance(table, str)
        or not columns
        or not facts.actual_has_table(table)
    ):
        return None

    contributions = _raising(f, scoring.PRIOR_LOGIT[f.confidence])
    index = facts.actual_index_covering(table, columns)
    if index is not None:
        contributions.append(
            Contribution(
                "ACTUAL_SCHEMA",
                "contradicts",
                scoring.INDEX_PRESENT_IN_DATABASE,
                Evidence(
                    source="ACTUAL_SCHEMA",
                    description=(
                        f"pg_catalog: index {index.name} on {table} leads with {index.columns[0]}"
                    ),
                    data={
                        "table": table,
                        "columns": list(columns),
                        "index": index.name,
                        "indexColumns": index.columns,
                        "definition": index.definition,
                    },
                ),
            )
        )
    else:
        names = sorted(i.name for i in facts.actual.table(table).indexes)  # type: ignore[union-attr]
        contributions.append(
            Contribution(
                "ACTUAL_SCHEMA",
                "supports",
                scoring.INDEX_ABSENT_FROM_DATABASE,
                Evidence(
                    source="ACTUAL_SCHEMA",
                    description=f"pg_catalog: no index on {table} leads with {', '.join(columns)}",
                    data={"table": table, "columns": list(columns), "indexes": names},
                ),
            )
        )
    return _score(MISSING_INDEX, contributions)


def _runtime_context(runtime: Finding, model: str, facts: SchemaFacts) -> list[Contribution]:
    """What the actual schema says about the columns the repeated query filters on."""
    sql = _data(_evidence(runtime, "SQL")).get("normalizedSql")
    if facts.actual is None or not isinstance(sql, str):
        return []
    table, columns = facts.table_of(model), sql_filter_columns(sql)
    if not columns or not facts.actual_has_table(table):
        return []
    index = facts.actual_index_covering(table, columns)
    if index is not None:
        text = (
            f"pg_catalog: the repeated query filters on {', '.join(columns)} and index "
            f"{index.name} serves it, so each execution is cheap and the cost is their number"
        )
        data = {"table": table, "columns": columns, "index": index.name}
    else:
        text = (
            f"pg_catalog: no index leads with {', '.join(columns)}, the repeated query's filter: "
            "each execution may scan the table"
        )
        data = {"table": table, "columns": columns, "index": None}
    return [
        Contribution(
            "ACTUAL_SCHEMA",
            "context",
            0.0,
            Evidence(source="ACTUAL_SCHEMA", description=text, data=data),
        )
    ]


def _evaluate_n_plus_one(
    static: Sequence[Finding], runtime: Sequence[Finding], model: str, facts: SchemaFacts
) -> tuple[HypothesisScore, Finding]:
    """Returns the N+1 hypothesis and the strongest runtime finding behind it."""
    contributions: list[Contribution] = []
    if static:
        best = max(static, key=lambda f: scoring.PRIOR_LOGIT[f.confidence])
        contributions += _raising(best, scoring.PRIOR_LOGIT[best.confidence])
        for other in (f for f in static if f is not best):
            contributions += [
                Contribution(e.source, "context", 0.0, e, other.fingerprint) for e in other.evidence
            ]
    best_runtime = max(runtime, key=lambda f: scoring.RUNTIME_REPETITION_LOGIT[f.confidence])
    contributions += _raising(
        best_runtime, scoring.RUNTIME_REPETITION_LOGIT[best_runtime.confidence]
    )
    contributions += _runtime_context(best_runtime, model, facts)
    return _score(N_PLUS_ONE if static else RUNTIME_N_PLUS_ONE, contributions), best_runtime


@dataclass
class _Site:
    static_n1: list[Finding] = field(default_factory=list)
    missing_index: list[Finding] = field(default_factory=list)
    runtime: list[Finding] = field(default_factory=list)


def _derived_fingerprint(rule_id: str, anchor: Finding, site: str) -> str:
    return hashlib.sha256("\x00".join([rule_id, anchor.fingerprint, site]).encode()).hexdigest()[
        :32
    ]


def _build_n_plus_one(
    h: HypothesisScore,
    *,
    anchor: Finding,
    runtime: Finding,
    static: bool,
    eliminated: Sequence[tuple[Finding, HypothesisScore]],
    site: str,
    route: str,
    model: str,
) -> Finding:
    data = _data(_evidence(runtime, "RUNTIME"))
    peak, affected, observed = (
        data.get(k) for k in ("maxExecutionsPerRequest", "requestsAffected", "requestsObserved")
    )
    parts = []
    if static:
        parts.append(
            f"Static analysis found a `{model}` query inside a loop at "
            f"`{anchor.file}:{anchor.line}`."
        )
    parts.append(
        f"At runtime the same query shape ran up to {peak} times within one request to `{route}` "
        f"({affected} of {observed} observed requests)."
    )
    for finding, score in eliminated:
        why = next(c.evidence.description for c in score.contributions if c.role == "contradicts")
        raised = finding.evidence[-1].description
        parts.append(
            f"A missing index was considered ({raised}) and ruled out: {why}. Each query is cheap; "
            "the cost is how many of them there are."
        )
    evidence = [_tag(c, role=c.role, hypothesis=h) for c in h.contributions]
    for _, score in eliminated:
        evidence += [_tag(c, role="ruled_out", hypothesis=score) for c in score.contributions]
    rule_id = h.rule_id
    return Finding(
        schema_version=1,
        rule_id=rule_id,
        severity="HIGH",
        confidence=h.confidence,
        file=anchor.file,
        line=anchor.line,
        end_line=anchor.end_line,
        title=f"N+1 query on {model}: up to {peak} executions per {route} request",
        body="\n\n".join(parts) + "\n\n" + _note(h),
        evidence=evidence,
        suggested_fix=anchor.suggested_fix
        if static
        else (runtime.suggested_fix or anchor.suggested_fix),
        fingerprint=anchor.fingerprint
        if rule_id == anchor.rule_id
        else _derived_fingerprint(rule_id, anchor, site),
    )


def _adjusted(f: Finding, h: HypothesisScore, extra_note: str = "") -> Finding:
    """The same finding and diagnosis, with the correlation's evidence and confidence."""
    return f.model_copy(
        update={
            "confidence": h.confidence,
            "evidence": [_tag(c, role=c.role, hypothesis=h) for c in h.contributions],
            "body": f"{f.body}\n\n{extra_note}{_note(h)}",
        }
    )


# ---- F2: orphaned rows -------------------------------------------------------------------------


def _evaluate_orphans(f: Finding, facts: SchemaFacts) -> HypothesisScore | None:
    data = _data(_evidence(f, "DATA_QUALITY"))
    table, columns, referenced = data.get("table"), data.get("columns"), data.get("referencedTable")
    if facts.actual is None or not (
        isinstance(table, str) and columns and isinstance(referenced, str)
    ):
        return None
    if not facts.actual_has_table(table):
        return None
    contributions = _raising(f, scoring.PRIOR_LOGIT[f.confidence])
    fk = facts.actual_foreign_key(table, columns, referenced)
    if fk is None:
        contributions.append(
            Contribution(
                "ACTUAL_SCHEMA",
                "supports",
                scoring.FOREIGN_KEY_NOT_ENFORCED,
                Evidence(
                    source="ACTUAL_SCHEMA",
                    description=(
                        f"pg_catalog: {table}({', '.join(columns)}) has no foreign-key constraint "
                        f"to {referenced}, so the database cannot prevent orphans"
                    ),
                    data={
                        "table": table,
                        "columns": list(columns),
                        "referencedTable": referenced,
                        "constraint": None,
                    },
                ),
            )
        )
    else:
        contributions.append(
            Contribution(
                "ACTUAL_SCHEMA",
                "contradicts",
                scoring.FOREIGN_KEY_ENFORCED,
                Evidence(
                    source="ACTUAL_SCHEMA",
                    description=(
                        f"pg_catalog: constraint {fk.name} enforces "
                        f"{table}({', '.join(columns)}) -> {referenced}; "
                        "orphans should be impossible"
                    ),
                    data={
                        "table": table,
                        "columns": list(columns),
                        "referencedTable": referenced,
                        "constraint": fk.name,
                        "onDelete": fk.on_delete,
                    },
                ),
            )
        )
    return _score(ORPHANED_FOREIGN_KEY, contributions)


# ---- the engine ----------------------------------------------------------------------------------


def correlate(
    findings: Sequence[Finding], *, facts: SchemaFacts | None = None
) -> CorrelationResult:
    facts = facts or SchemaFacts()
    ordered = sorted(findings, key=_order_key)
    consumed: set[int] = set()
    position = {id(f): i for i, f in enumerate(ordered)}
    output: list[Finding] = []
    decisions: list[Decision] = []

    def consume(*group: Finding) -> tuple[str, ...]:
        consumed.update(position[id(f)] for f in group)
        return tuple(f.fingerprint for f in group)

    # -- F1: sites keyed by (route, model) --
    sites: dict[tuple[str | None, str | None], _Site] = defaultdict(_Site)
    for f in ordered:
        if f.rule_id == RUNTIME_N_PLUS_ONE:
            sites[_runtime_site(f)].runtime.append(f)
        elif f.rule_id in (N_PLUS_ONE, MISSING_INDEX):
            site = sites[(route_for_file(f.file), _static_model(f))]
            (site.static_n1 if f.rule_id == N_PLUS_ONE else site.missing_index).append(f)

    for (route, model), site in sorted(
        sites.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or "")
    ):
        scored = [
            (f, s)
            for f in site.missing_index
            if (s := _evaluate_missing_index(f, facts)) is not None
        ]
        eliminated = [(f, s) for f, s in scored if not scoring.believed(s.logit)]
        merge = (
            bool(site.runtime)
            and route is not None
            and model is not None
            and (bool(site.static_n1) or bool(eliminated))
        )
        label = f"{route or 'file'}:{model}"

        hypotheses: list[HypothesisScore] = []
        group: list[Finding] = [f for f, _ in scored]
        changed_from = None
        if merge:
            n1, runtime = _evaluate_n_plus_one(site.static_n1, site.runtime, model, facts)  # type: ignore[arg-type]
            anchor = site.static_n1[0] if site.static_n1 else eliminated[0][0]
            changed_from = None if site.static_n1 else eliminated[0][0].rule_id
            output.append(
                _build_n_plus_one(
                    n1,
                    anchor=anchor,
                    runtime=runtime,
                    static=bool(site.static_n1),
                    eliminated=eliminated,
                    site=label,
                    route=route,
                    model=model,  # type: ignore[arg-type]
                )
            )
            hypotheses.append(replace(n1, emitted=True))
            group += [*site.static_n1, *site.runtime]
        for f, s in scored:
            emitted = scoring.believed(s.logit)
            hypotheses.append(replace(s, emitted=emitted))
            if emitted:
                output.append(_adjusted(f, s))
        if hypotheses:
            decisions.append(Decision(label, tuple(hypotheses), changed_from, consume(*group)))

    # -- F2: orphaned rows against the actual schema --
    for f in ordered:
        if f.rule_id != ORPHANED_FOREIGN_KEY:
            continue
        score = _evaluate_orphans(f, facts)
        if score is None:
            continue
        output.append(_adjusted(f, score))
        table = _data(_evidence(f, "DATA_QUALITY")).get("table")
        decisions.append(
            Decision(f"table:{table}", (replace(score, emitted=True),), None, consume(f))
        )

    output += [f for i, f in enumerate(ordered) if i not in consumed]
    output.sort(key=_order_key)
    return CorrelationResult(findings=output, decisions=decisions)
