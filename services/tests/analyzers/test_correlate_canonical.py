"""The M4.3 canonical case, written before the engine exists.

A static N+1 suspicion, plus runtime evidence of the query executing hundreds of times per
request, plus schema evidence that the joined column IS indexed, must resolve to an N+1
finding, NOT to a missing-index finding.
"""

from analyzers.correlate import SchemaFacts, correlate
from tests.analyzers.correlate_helpers import (
    TASK_FILE,
    actual_task_schema,
    runtime_n_plus_one,
    static_missing_index,
    static_n_plus_one,
)


def rule_ids(result):
    return [f.rule_id for f in result.findings]


def test_static_n_plus_one_plus_runtime_repetition_plus_indexed_column_resolves_to_n_plus_one():
    # The declared schema has no index on Task.assigneeId, so static analysis also suspects a
    # missing index at the very same call. The database, however, has one.
    findings = [
        static_n_plus_one(confidence="MEDIUM"),
        static_missing_index(confidence="MEDIUM"),
        runtime_n_plus_one(peak=300),
    ]
    result = correlate(findings, facts=SchemaFacts(actual=actual_task_schema(indexed=True)))

    assert rule_ids(result) == ["N_PLUS_ONE_IN_LOOP"], (
        "one finding, and it is not a missing-index finding"
    )
    assert "MISSING_INDEX_ON_FILTERED_FIELD" not in rule_ids(result)

    [resolved] = result.findings
    assert (resolved.file, resolved.line, resolved.confidence) == (TASK_FILE, 12, "HIGH")
    # Every layer that contributed is named on its own evidence item.
    assert {e.source for e in resolved.evidence} >= {
        "STATIC_SOURCE",
        "RUNTIME",
        "DECLARED_SCHEMA",
        "ACTUAL_SCHEMA",
    }

    # The missing-index hypothesis was raised, weighed, and eliminated by the database's own index.
    [decision] = result.decisions
    scores = {h.rule_id: h for h in decision.hypotheses}
    assert scores["MISSING_INDEX_ON_FILTERED_FIELD"].emitted is False
    assert scores["MISSING_INDEX_ON_FILTERED_FIELD"].posterior < 0.5
    assert scores["N_PLUS_ONE_IN_LOOP"].emitted is True
    assert scores["N_PLUS_ONE_IN_LOOP"].posterior > 0.9
    decisive = [
        c
        for c in scores["MISSING_INDEX_ON_FILTERED_FIELD"].contributions
        if c.role == "contradicts"
    ]
    assert [(c.layer, c.evidence.data["index"]) for c in decisive] == [
        ("ACTUAL_SCHEMA", "Task_assigneeId_idx")
    ]


def test_without_the_indexed_column_evidence_the_missing_index_suspicion_survives():
    findings = [static_n_plus_one(), static_missing_index(), runtime_n_plus_one(peak=300)]
    result = correlate(findings, facts=SchemaFacts(actual=actual_task_schema(indexed=False)))
    assert sorted(rule_ids(result)) == ["MISSING_INDEX_ON_FILTERED_FIELD", "N_PLUS_ONE_IN_LOOP"]


def test_the_indexed_column_can_change_a_missing_index_finding_into_an_n_plus_one_finding():
    # Static analysis saw only the unindexed filter (the loop is out of sight, e.g. in a helper).
    # Runtime sees the repetition; the database has the index. The finding's TYPE changes.
    result = correlate(
        [static_missing_index(), runtime_n_plus_one(peak=300)],
        facts=SchemaFacts(actual=actual_task_schema(indexed=True)),
    )
    [resolved] = result.findings
    assert resolved.rule_id == "RUNTIME_N_PLUS_ONE"
    assert (resolved.file, resolved.line) == (TASK_FILE, 12), (
        "anchored at the call the static rule found"
    )
    [decision] = result.decisions
    assert decision.type_changed_from == "MISSING_INDEX_ON_FILTERED_FIELD"
