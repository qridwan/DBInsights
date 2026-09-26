import json
import random
from pathlib import Path

import pytest

from analyzers.core_bridge import analyze, core_cli_path
from analyzers.correlate import SchemaFacts, correlate, route_for_file, scoring, sql_filter_columns
from analyzers.finding import parse_findings
from analyzers.schema.actual import connect, read_actual_schema
from analyzers.schema.declared import DeclaredSchema
from experiments.groundtruth import Manifest, score
from tests.analyzers.conftest import actual, actual_index, column, table
from tests.analyzers.correlate_helpers import (
    TASK_FILE,
    actual_task_schema,
    orphan_finding,
    runtime_n_plus_one,
    static_missing_index,
    static_n_plus_one,
)

FIXTURES = Path(__file__).parents[3] / "fixtures" / "source"


def dump(result) -> str:
    return json.dumps([f.model_dump(mode="json") for f in result.findings], sort_keys=True)


def by_rule(result):
    return {f.rule_id: f for f in result.findings}


# ---- joining on the framework's convention and the queries' own SQL --------------------------


@pytest.mark.parametrize(
    ("file", "route"),
    [
        ("src/app/api/orders/route.ts", "/api/orders"),
        ("src/app/api/orders/[id]/invoice/route.ts", "/api/orders/[id]/invoice"),
        ("app/(shop)/cart/route.js", "/cart"),
        ("apps/web/src/app/api/@modal/x/route.tsx", "/api/x"),
        ("src/app/route.ts", "/"),
        ("src\\app\\api\\tasks\\route.ts", "/api/tasks"),
        ("src/app/app/dashboard/route.ts", "/app/dashboard"),
        ("packages/app/src/app/api/x/route.ts", "/api/x"),
    ],
)
def test_route_for_file_follows_the_app_router_convention(file, route):
    assert route_for_file(file) == route


@pytest.mark.parametrize(
    "file",
    ["src/lib/db.ts", "src/app/api/orders/page.tsx", "src/app/api/orders/helper.ts", "route.ts"],
)
def test_files_that_are_not_route_handlers_have_no_route(file):
    assert route_for_file(file) is None


def test_the_filter_columns_of_a_query_come_from_its_where_clause():
    sql = (
        'SELECT "t"."id" FROM "public"."Task" AS "t" '
        'WHERE "t"."assigneeId" = %s AND "t"."status" IN (%s) OFFSET %s'
    )
    assert sql_filter_columns(sql) == ["assigneeId", "status"]
    assert sql_filter_columns('SELECT "id" FROM "Task"') == []
    assert sql_filter_columns("THIS IS NOT SQL (((") == []


# ---- what counts as an index in the database -------------------------------------------------


def facts_with(*indexes, columns=("id", "assigneeId", "createdAt")):
    cols = [column(name, position=i + 1) for i, name in enumerate(columns)]
    return SchemaFacts(actual=actual(table("Task", cols, list(indexes))))


def test_only_plain_full_table_indexes_that_lead_with_the_column_count():
    plain = actual_index("plain", "assigneeId")
    assert facts_with(plain).actual_index_covering("Task", ["assigneeId"]) == plain
    assert facts_with(actual_index("composite", "assigneeId", "createdAt")).actual_index_covering(
        "Task", ["assigneeId"]
    )
    assert (
        facts_with(actual_index("trailing", "createdAt", "assigneeId")).actual_index_covering(
            "Task", ["assigneeId"]
        )
        is None
    )
    partial = actual_index("partial", "assigneeId", predicate="(\"createdAt\" > '2026-01-01')")
    assert facts_with(partial).actual_index_covering("Task", ["assigneeId"]) is None
    expression = actual_index("lower_idx", "lower(assigneeId)", referenced_columns=["assigneeId"])
    assert facts_with(expression).actual_index_covering("Task", ["assigneeId"]) is None
    assert facts_with(plain).actual_index_covering("Missing", ["assigneeId"]) is None


def test_table_names_come_from_the_declared_schema_when_mapped():
    declared = DeclaredSchema.model_validate(
        {
            "models": [
                {
                    "name": "Ticket",
                    "blockType": "model",
                    "dbName": "tickets",
                    "fields": [],
                    "relations": [],
                    "indexes": [],
                    "line": 1,
                }
            ],
            "enums": [],
        }
    )
    facts = SchemaFacts(declared=declared)
    assert (facts.table_of("Ticket"), facts.table_of("Unknown")) == ("tickets", "Unknown")


# ---- the weights encode which evidence outweighs which ---------------------------------------


def test_a_database_index_outweighs_even_the_strongest_declared_suspicion():
    assert scoring.PRIOR_LOGIT["HIGH"] + scoring.INDEX_PRESENT_IN_DATABASE < scoring.BELIEVED_AT


def test_runtime_repetition_can_carry_a_weak_static_suspicion():
    assert (
        scoring.PRIOR_LOGIT["LOW"] + scoring.RUNTIME_REPETITION_LOGIT["HIGH"]
        >= scoring.STRONGLY_BELIEVED_AT
    )


def test_an_enforced_constraint_outweighs_the_strongest_orphan_report():
    assert scoring.PRIOR_LOGIT["HIGH"] + scoring.FOREIGN_KEY_ENFORCED < scoring.BELIEVED_AT


def test_weights_combine_independently_of_order_and_exactly():
    values = [1.5, -4.0, 0.5, 2.5, 1.0, -0.5]
    assert scoring.combine(values) == scoring.combine(reversed(values)) == 1.0
    assert scoring.combine([0.1] * 10) == 1.0, "fsum is exact where naive addition is not"


@pytest.mark.parametrize(
    ("logit", "label"),
    [
        (-5.0, "LOW"),
        (-0.5, "LOW"),
        (0.0, "MEDIUM"),
        (1.3, "MEDIUM"),
        (scoring.STRONGLY_BELIEVED_AT, "HIGH"),
        (4.0, "HIGH"),
    ],
)
def test_confidence_labels_are_cut_from_the_log_odds(logit, label):
    assert scoring.confidence_for(logit) == label


# ---- corroboration raises, contradiction lowers ----------------------------------------------


def test_runtime_corroboration_raises_a_static_n_plus_one():
    alone = correlate([static_n_plus_one(confidence="MEDIUM")])
    assert alone.findings[0].confidence == "MEDIUM", "no runtime data, no change"
    both = correlate(
        [static_n_plus_one(confidence="MEDIUM"), runtime_n_plus_one(confidence="HIGH")]
    )
    assert [f.confidence for f in both.findings] == ["HIGH"]
    assert both.decisions[0].hypotheses[0].posterior == pytest.approx(0.952574, abs=1e-6)


def test_one_finding_replaces_the_static_and_runtime_findings_it_merges():
    result = correlate([static_n_plus_one(), runtime_n_plus_one()])
    assert [f.rule_id for f in result.findings] == ["N_PLUS_ONE_IN_LOOP"]
    assert result.decisions[0].consumed == ("s-n1", "r-n1")


def test_the_actual_schema_confirming_a_missing_index_raises_it():
    static = static_missing_index(confidence="MEDIUM")
    [finding] = correlate(
        [static], facts=SchemaFacts(actual=actual_task_schema(indexed=False))
    ).findings
    assert finding.rule_id == "MISSING_INDEX_ON_FILTERED_FIELD"
    assert finding.confidence == "HIGH", "0.5 declared + 1.0 confirmed by the database"
    assert {e.source for e in finding.evidence} == {
        "STATIC_SOURCE",
        "DECLARED_SCHEMA",
        "ACTUAL_SCHEMA",
    }


def test_a_missing_index_the_database_already_has_is_eliminated_outright():
    result = correlate(
        [static_missing_index(confidence="HIGH")],
        facts=SchemaFacts(actual=actual_task_schema(indexed=True)),
    )
    assert result.findings == []
    [decision] = result.decisions
    assert decision.hypotheses[0].emitted is False and decision.consumed == ("s-mi",)


def test_a_partial_index_does_not_eliminate_a_missing_index_finding():
    result = correlate(
        [static_missing_index()],
        facts=SchemaFacts(actual=actual_task_schema(indexed=True, partial=True)),
    )
    assert [f.rule_id for f in result.findings] == ["MISSING_INDEX_ON_FILTERED_FIELD"]


def test_a_static_finding_alone_is_left_untouched_when_the_database_is_unknown():
    static = static_missing_index()
    result = correlate([static], facts=SchemaFacts())
    assert result.findings == [static] and result.decisions == []


def test_a_table_the_database_does_not_have_gives_no_opinion():
    static = static_missing_index(table_name="Ghost")
    assert correlate(
        [static], facts=SchemaFacts(actual=actual_task_schema(indexed=True))
    ).findings == [static]


# ---- orphans against the actual schema -------------------------------------------------------


def orders_schema(*, with_fk: bool):
    from analyzers.schema.actual import ActualForeignKey

    fks = (
        [
            ActualForeignKey(
                name="Order_customerId_fkey",
                columns=["customerId"],
                referenced_table="Customer",
                referenced_columns=["id"],
                on_delete="RESTRICT",
                on_update="CASCADE",
            )
        ]
        if with_fk
        else []
    )
    cols = [column("id"), column("customerId", position=2)]
    return actual(table("Order", cols, [actual_index("Order_pkey", "id", primary=True)], fks))


def test_orphans_are_explained_by_a_missing_constraint_and_more_confident_for_it():
    [finding] = correlate(
        [orphan_finding(confidence="MEDIUM")],
        facts=SchemaFacts(actual=orders_schema(with_fk=False)),
    ).findings
    assert finding.rule_id == "ORPHANED_FOREIGN_KEY" and finding.confidence == "HIGH"
    assert "no foreign-key constraint" in next(
        e.description for e in finding.evidence if e.source == "ACTUAL_SCHEMA"
    )


def test_orphans_despite_an_enforced_constraint_are_doubted():
    [finding] = correlate(
        [orphan_finding(confidence="HIGH")], facts=SchemaFacts(actual=orders_schema(with_fk=True))
    ).findings
    assert finding.rule_id == "ORPHANED_FOREIGN_KEY" and finding.confidence == "LOW"
    roles = {e.data["correlation"]["role"] for e in finding.evidence if e.source == "ACTUAL_SCHEMA"}
    assert roles == {"contradicts"}


# ---- evidence names its layer, its role and its weight ---------------------------------------


def test_every_evidence_item_names_its_layer_and_carries_its_role_weight_and_posterior():
    result = correlate(
        [static_n_plus_one(), static_missing_index(), runtime_n_plus_one()],
        facts=SchemaFacts(actual=actual_task_schema(indexed=True)),
    )
    [finding] = result.findings
    for e in finding.evidence:
        assert e.source in {
            "STATIC_SOURCE",
            "DECLARED_SCHEMA",
            "RUNTIME",
            "SQL",
            "ACTUAL_SCHEMA",
            "DATA_QUALITY",
        }
        correlation = e.data["correlation"]
        assert set(correlation) == {"role", "hypothesis", "weightNats", "posterior"}
    roles = {(e.source, e.data["correlation"]["role"]) for e in finding.evidence}
    assert ("RUNTIME", "supports") in roles and ("STATIC_SOURCE", "supports") in roles
    # The eliminated alternative is kept, tagged, so the reasoning can be audited.
    ruled_out = [e for e in finding.evidence if e.data["correlation"]["role"] == "ruled_out"]
    assert {e.source for e in ruled_out} == {"STATIC_SOURCE", "DECLARED_SCHEMA", "ACTUAL_SCHEMA"}
    assert {e.data["correlation"]["hypothesis"] for e in ruled_out} == {
        "MISSING_INDEX_ON_FILTERED_FIELD"
    }


def test_the_body_explains_the_resolution_in_words():
    [finding] = correlate(
        [static_n_plus_one(), static_missing_index(), runtime_n_plus_one(peak=300)],
        facts=SchemaFacts(actual=actual_task_schema(indexed=True)),
    ).findings
    assert "ran up to 300 times" in finding.body
    assert "ruled out" in finding.body and "Task_assigneeId_idx" in finding.body
    assert "Correlation:" in finding.body
    assert "up to 300 executions" in finding.title


def test_the_repeated_querys_own_filter_column_is_checked_against_the_database():
    [finding] = correlate(
        [static_n_plus_one(), runtime_n_plus_one()],
        facts=SchemaFacts(actual=actual_task_schema(indexed=True)),
    ).findings
    context = [e for e in finding.evidence if e.data["correlation"]["role"] == "context"]
    assert [e.source for e in context] == ["ACTUAL_SCHEMA"]
    assert (
        "serves it" in context[0].description and context[0].data["index"] == "Task_assigneeId_idx"
    )
    [unindexed] = correlate(
        [static_n_plus_one(), runtime_n_plus_one()],
        facts=SchemaFacts(actual=actual_task_schema(indexed=False)),
    ).findings
    assert "may scan the table" in next(
        e.description for e in unindexed.evidence if e.data["correlation"]["role"] == "context"
    )


# ---- what is and is not joined ---------------------------------------------------------------


def test_findings_about_different_routes_or_models_are_not_correlated():
    other_route = correlate([static_n_plus_one(), runtime_n_plus_one(route="/api/other")])
    assert sorted(f.rule_id for f in other_route.findings) == [
        "N_PLUS_ONE_IN_LOOP",
        "RUNTIME_N_PLUS_ONE",
    ]
    other_model = correlate([static_n_plus_one(), runtime_n_plus_one(model="User")])
    assert sorted(f.rule_id for f in other_model.findings) == [
        "N_PLUS_ONE_IN_LOOP",
        "RUNTIME_N_PLUS_ONE",
    ]


def test_a_static_finding_outside_a_route_handler_cannot_join_runtime():
    lib = static_n_plus_one(file="src/lib/tasks.ts")
    assert sorted(f.rule_id for f in correlate([lib, runtime_n_plus_one()]).findings) == [
        "N_PLUS_ONE_IN_LOOP",
        "RUNTIME_N_PLUS_ONE",
    ]


def test_runtime_evidence_alone_passes_through_unchanged():
    runtime = runtime_n_plus_one()
    assert correlate([runtime]).findings == [runtime]


def test_findings_of_other_layers_pass_through_unchanged():
    from analyzers.finding import Evidence
    from tests.analyzers.correlate_helpers import finding

    spike = finding(
        "NULL_SPIKE",
        file="table:Customer",
        line=0,
        confidence="HIGH",
        fingerprint="nq",
        evidence=[
            Evidence(
                source="DATA_QUALITY",
                description="d",
                data={"table": "Customer", "column": "phone"},
            )
        ],
    )
    assert correlate([spike, static_n_plus_one()]).findings == sorted(
        [spike, static_n_plus_one()], key=lambda f: (f.file, f.line, f.rule_id)
    )


def test_several_static_findings_at_one_site_produce_one_finding():
    result = correlate(
        [
            static_n_plus_one(line=12, fingerprint="a"),
            static_n_plus_one(line=20, fingerprint="b"),
            runtime_n_plus_one(),
        ]
    )
    assert [(f.rule_id, f.line) for f in result.findings] == [("N_PLUS_ONE_IN_LOOP", 12)]
    assert result.decisions[0].consumed == ("a", "b", "r-n1")


# ---- fingerprints ----------------------------------------------------------------------------


def test_a_merged_finding_keeps_the_static_findings_identity_and_a_type_change_gets_its_own():
    [merged] = correlate([static_n_plus_one(), runtime_n_plus_one()]).findings
    assert merged.fingerprint == "s-n1"
    changed = correlate(
        [static_missing_index(), runtime_n_plus_one()],
        facts=SchemaFacts(actual=actual_task_schema(indexed=True)),
    )
    [resolved] = changed.findings
    assert resolved.fingerprint not in {"s-mi", "r-n1"}
    again = correlate(
        [runtime_n_plus_one(), static_missing_index()],
        facts=SchemaFacts(actual=actual_task_schema(indexed=True)),
    )
    assert again.findings[0].fingerprint == resolved.fingerprint


# ---- reproducibility -------------------------------------------------------------------------


def scenario():
    return [
        static_n_plus_one(),
        static_missing_index(),
        runtime_n_plus_one(peak=300),
        # Ties: equally confident candidates at the same site, so any dependence on arrival order
        # would change which one anchors the finding and what evidence is kept.
        static_n_plus_one(line=20, fingerprint="s-n1-b"),
        runtime_n_plus_one(peak=280, fingerprint="r-n1-b"),
        static_n_plus_one(line=31, fingerprint="s-n1-c", confidence="HIGH"),
        static_n_plus_one(file="src/app/api/x/route.ts", line=3, model="User", fingerprint="s2"),
        runtime_n_plus_one(route="/api/x", model="User", confidence="MEDIUM", fingerprint="r2"),
        orphan_finding(),
        static_missing_index(
            model="User", table_name="User", file="src/lib/u.ts", line=5, fingerprint="s3"
        ),
    ]


def facts():
    return SchemaFacts(actual=actual_task_schema(indexed=True))


def test_identical_input_gives_identical_scores_across_runs():
    runs = [correlate(scenario(), facts=facts()) for _ in range(5)]
    assert len({dump(r) for r in runs}) == 1
    posteriors = {tuple(h.posterior for d in r.decisions for h in d.hypotheses) for r in runs}
    assert len(posteriors) == 1


def test_the_order_findings_arrive_in_does_not_change_the_result():
    baseline = correlate(scenario(), facts=facts())
    rng = random.Random(20260927)
    for _ in range(25):
        shuffled = scenario()
        rng.shuffle(shuffled)
        result = correlate(shuffled, facts=facts())
        assert dump(result) == dump(baseline)
        assert [
            (d.site, [(h.rule_id, h.logit, h.posterior) for h in d.hypotheses])
            for d in result.decisions
        ] == [
            (d.site, [(h.rule_id, h.logit, h.posterior) for h in d.hypotheses])
            for d in baseline.decisions
        ]


def test_separate_processes_with_different_hash_seeds_print_byte_identical_output(tmp_path):
    """'Across runs' means across interpreter runs: set/dict ordering must not leak into results."""
    import os
    import subprocess
    import sys

    path = tmp_path / "findings.json"
    path.write_text(
        json.dumps(
            [f.model_dump(mode="json", by_alias=True, exclude_none=True) for f in scenario()]
        )
    )
    services = Path(__file__).parents[2]

    def run(seed: str, *flags: str) -> str:
        return subprocess.run(
            [sys.executable, "-m", "analyzers.correlate", "--findings", str(path), *flags],
            cwd=services,
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    outputs = {run(seed) for seed in ("0", "1", "42", "random")}
    reports = {run(seed, "--report") for seed in ("0", "7", "random")}
    assert len(outputs) == 1 and len(reports) == 1
    assert json.loads(outputs.pop()), "and it is not vacuously empty"


def test_a_sites_score_depends_only_on_that_sites_evidence():
    alone = correlate([static_n_plus_one(), runtime_n_plus_one()])
    elsewhere = [
        static_n_plus_one(file="src/app/api/x/route.ts", line=3, model="User", fingerprint="s2"),
        runtime_n_plus_one(route="/api/x", model="User", confidence="MEDIUM", fingerprint="r2"),
        orphan_finding(),
        static_missing_index(
            model="User", table_name="User", file="src/lib/u.ts", line=5, fingerprint="s3"
        ),
    ]
    crowded = correlate([static_n_plus_one(), runtime_n_plus_one(), *elsewhere], facts=facts())
    task_site = next(d for d in crowded.decisions if d.site.endswith(":Task"))
    assert task_site.hypotheses[0].posterior == alone.decisions[0].hypotheses[0].posterior


def test_the_strongest_evidence_at_a_site_dominates_rather_than_accumulating():
    """Several static findings at one site are context for each other, not independent votes."""
    weak = correlate([static_n_plus_one(confidence="MEDIUM"), runtime_n_plus_one()])
    with_more = correlate(
        [
            static_n_plus_one(confidence="MEDIUM"),
            static_n_plus_one(line=20, fingerprint="b"),
            static_n_plus_one(line=30, fingerprint="c"),
            runtime_n_plus_one(),
        ]
    )
    assert with_more.decisions[0].hypotheses[0].logit == weak.decisions[0].hypotheses[0].logit
    strong = correlate(
        [
            static_n_plus_one(confidence="MEDIUM"),
            static_n_plus_one(line=20, fingerprint="b", confidence="HIGH"),
            runtime_n_plus_one(),
        ]
    )
    assert strong.decisions[0].hypotheses[0].logit == weak.decisions[0].hypotheses[0].logit + 1.0


# ---- against the scorer ----------------------------------------------------------------------


def n1_manifest():
    return Manifest.model_validate(
        {
            "schemaVersion": 1,
            "app": "t",
            "entries": [
                {
                    "id": "n1",
                    "problemType": "n_plus_one",
                    "category": "performance",
                    "file": TASK_FILE,
                    "line": 12,
                    "endpoint": "GET /api/tasks",
                    "expectedRuleId": "N_PLUS_ONE_IN_LOOP",
                    "description": "d",
                    "injectedAt": "2026-09-27T00:00:00Z",
                }
            ],
        }
    )


def test_correlation_removes_the_double_report_the_scorer_would_count_as_a_duplicate():
    layered = score([static_n_plus_one(), runtime_n_plus_one()], n1_manifest())
    assert (layered.aggregate.tp, layered.aggregate.duplicates) == (1, 1)
    merged = score(correlate([static_n_plus_one(), runtime_n_plus_one()]).findings, n1_manifest())
    assert (
        merged.aggregate.tp,
        merged.aggregate.fp,
        merged.aggregate.fn,
        merged.aggregate.duplicates,
    ) == (1, 0, 0, 0)


def test_eliminating_a_declared_schema_false_positive_removes_a_false_positive():
    manifest = n1_manifest()  # no missing_index entry: a missing-index finding here would be an FP
    before = score([static_n_plus_one(), static_missing_index(), runtime_n_plus_one()], manifest)
    after = score(
        correlate(
            [static_n_plus_one(), static_missing_index(), runtime_n_plus_one()],
            facts=SchemaFacts(actual=actual_task_schema(indexed=True)),
        ).findings,
        manifest,
    )
    assert (before.aggregate.fp, after.aggregate.fp) == (1, 0)
    assert after.aggregate.tp == 1


# ---- real static analysis, a real actual schema ----------------------------------------------


@pytest.mark.skipif(not core_cli_path().exists(), reason="packages/core not built")
def test_end_to_end_with_the_typescript_core_and_a_real_database_index(temp_schema):
    source = FIXTURES / "correlate"
    static = parse_findings(analyze(source, source / "schema.prisma"))
    assert {f.rule_id for f in static} == {
        "N_PLUS_ONE_IN_LOOP",
        "MISSING_INDEX_ON_FILTERED_FIELD",
    }, "declared schema has no index on Task.assigneeId, so static analysis suspects one"

    c = temp_schema.conn
    c.execute('CREATE TABLE "User" ("id" integer PRIMARY KEY, "name" text NOT NULL)')
    c.execute('CREATE TABLE "Task" ("id" integer PRIMARY KEY, "assigneeId" integer NOT NULL)')
    c.execute(
        'CREATE INDEX "Task_assigneeId_idx" ON "Task" ("assigneeId")'
    )  # the database has it anyway
    with connect(temp_schema.url) as conn:
        real = SchemaFacts(actual=read_actual_schema(conn, temp_schema.name))

    runtime = runtime_n_plus_one(route="/api/tasks", model="Task", peak=50)
    result = correlate([*static, runtime], facts=real)

    assert [f.rule_id for f in result.findings] == ["N_PLUS_ONE_IN_LOOP"]
    [resolved] = result.findings
    assert (resolved.file, resolved.line, resolved.confidence) == (
        "src/app/api/tasks/route.ts",
        8,
        "HIGH",
    )
    assert {e.source for e in resolved.evidence} >= {
        "STATIC_SOURCE",
        "DECLARED_SCHEMA",
        "RUNTIME",
        "ACTUAL_SCHEMA",
    }

    # Without the index in the database, the missing-index suspicion stands next to the N+1.
    c.execute('DROP INDEX "Task_assigneeId_idx"')
    with connect(temp_schema.url) as conn:
        bare = SchemaFacts(actual=read_actual_schema(conn, temp_schema.name))
    assert sorted(f.rule_id for f in correlate([*static, runtime], facts=bare).findings) == [
        "MISSING_INDEX_ON_FILTERED_FIELD",
        "N_PLUS_ONE_IN_LOOP",
    ]
