from analyzers.schema.actual import ActualForeignKey
from analyzers.schema.divergence import compare, to_findings
from experiments.groundtruth import Manifest, score


def simple(build, *, declared_indexes, actual_indexes, fields=None, columns=None):
    fields = fields or [
        build.field("id", "Int"),
        build.field("email"),
        build.field("createdAt", "DateTime"),
    ]
    columns = columns or [
        build.column("id", "integer"),
        build.column("email", "text"),
        build.column("createdAt", "timestamp(3) without time zone"),
    ]
    return compare(
        build.declared(build.model("User", fields, declared_indexes)),
        build.actual(build.table("User", columns, actual_indexes)),
    )


def test_identical_schemas_do_not_diverge(build):
    report = simple(
        build,
        declared_indexes=[
            build.index("id", "id"),
            build.index("unique", "email"),
            build.index("index", "createdAt"),
        ],
        actual_indexes=[
            build.actual_index("User_pkey", "id", primary=True),
            build.actual_index("User_email_key", "email", unique=True),
            build.actual_index("User_createdAt_idx", "createdAt"),
        ],
    )
    assert (
        report.indexes_not_declared
        == report.declared_indexes_not_applied
        == report.column_mismatches
        == []
    )


def test_index_in_actual_only(build):
    report = simple(
        build,
        declared_indexes=[build.index("id", "id")],
        actual_indexes=[
            build.actual_index("User_pkey", "id", primary=True),
            build.actual_index("hotfix_idx", "createdAt"),
        ],
    )
    assert [(d.index_name, d.columns) for d in report.indexes_not_declared] == [
        ("hotfix_idx", ["createdAt"])
    ]
    assert report.declared_indexes_not_applied == []


def test_index_in_declared_only(build):
    report = simple(
        build,
        declared_indexes=[build.index("id", "id"), build.index("index", "createdAt", line=42)],
        actual_indexes=[build.actual_index("User_pkey", "id", primary=True)],
    )
    assert [(d.columns, d.line) for d in report.declared_indexes_not_applied] == [
        (["createdAt"], 42)
    ]


def test_uniqueness_is_part_of_identity(build):
    report = simple(
        build,
        declared_indexes=[build.index("id", "id"), build.index("unique", "email")],
        actual_indexes=[
            build.actual_index("User_pkey", "id", primary=True),
            build.actual_index("User_email_idx", "email"),
        ],
    )
    assert len(report.indexes_not_declared) == len(report.declared_indexes_not_applied) == 1


def test_column_order_is_part_of_identity(build):
    report = simple(
        build,
        declared_indexes=[build.index("id", "id"), build.index("index", "email", "createdAt")],
        actual_indexes=[
            build.actual_index("User_pkey", "id", primary=True),
            build.actual_index("x", "createdAt", "email"),
        ],
    )
    assert len(report.indexes_not_declared) == len(report.declared_indexes_not_applied) == 1


def test_expression_and_partial_indexes_never_match_a_declared_index(build):
    report = simple(
        build,
        declared_indexes=[build.index("id", "id"), build.index("index", "email")],
        actual_indexes=[
            build.actual_index("User_pkey", "id", primary=True),
            build.actual_index("User_email_idx", "email"),
            build.actual_index("lower_email", "lower(email)", referenced_columns=["email"]),
            build.actual_index("recent", "email", predicate="(\"createdAt\" > '2026-01-01')"),
        ],
    )
    assert sorted(d.index_name for d in report.indexes_not_declared) == ["lower_email", "recent"]


def test_mapped_names_are_compared_by_database_name(build):
    fields = [build.field("id", "Int"), build.field("createdAt", "DateTime", dbName="created_at")]
    columns = [
        build.column("id", "integer"),
        build.column("created_at", "timestamp(3) without time zone"),
    ]
    report = compare(
        build.declared(
            build.model(
                "User",
                fields,
                [build.index("id", "id"), build.index("index", "createdAt")],
                dbName="users",
            )
        ),
        build.actual(
            build.table(
                "users",
                columns,
                [
                    build.actual_index("users_pkey", "id", primary=True),
                    build.actual_index("i", "created_at"),
                ],
            )
        ),
    )
    assert (
        report.indexes_not_declared
        == report.declared_indexes_not_applied
        == report.column_mismatches
        == []
    )


def test_column_type_nullability_and_missing_mismatches(build):
    report = simple(
        build,
        declared_indexes=[],
        actual_indexes=[],
        fields=[build.field("id", "Int"), build.field("email", optional=True), build.field("gone")],
        columns=[build.column("id", "bigint"), build.column("email", "text", nullable=False)],
    )
    assert sorted(
        (m.column, m.problem, m.declared, m.actual) for m in report.column_mismatches
    ) == [
        ("email", "nullability", "NULL", "NOT NULL"),
        ("gone", "missing", "String", None),
        ("id", "type", "integer", "bigint"),
    ]


def test_prisma_bookkeeping_and_implicit_join_tables_are_ignored(build):
    tag = build.model("Tag", [build.field("id", "Int")], [build.index("id", "id")])
    tag["relations"] = [
        {
            "field": "posts",
            "referencedModel": "Post",
            "fields": [],
            "references": [],
            "foreignKeyOn": "implicit-many-to-many",
            "line": 1,
        }
    ]
    post = build.model("Post", [build.field("id", "Int")], [build.index("id", "id")])
    post["relations"] = [
        {
            "field": "tags",
            "referencedModel": "Tag",
            "fields": [],
            "references": [],
            "foreignKeyOn": "implicit-many-to-many",
            "line": 1,
        }
    ]
    pk = lambda t: build.actual_index(f"{t}_pkey", "id", primary=True)  # noqa: E731
    report = compare(
        build.declared(tag, post),
        build.actual(
            build.table("Tag", [build.column("id", "integer")], [pk("Tag")]),
            build.table("Post", [build.column("id", "integer")], [pk("Post")]),
            build.table(
                "_PostToTag", [build.column("A", "integer"), build.column("B", "integer")], []
            ),
            build.table("_prisma_migrations", [build.column("id", "text")], []),
            build.table("legacy_audit", [build.column("id", "integer")], []),
        ),
    )
    assert report.tables_not_declared == ["legacy_audit"]


def test_foreign_key_divergence_is_reported_but_not_a_finding(build):
    fields = [
        build.field("id", "Int"),
        build.field("teamId", "Int"),
        build.field("team", "Team", kind="relation"),
    ]
    user = build.model("User", fields, [build.index("id", "id")])
    user["relations"] = [
        {
            "field": "team",
            "referencedModel": "Team",
            "fields": ["teamId"],
            "references": ["id"],
            "foreignKeyOn": "self",
            "line": 3,
        }
    ]
    report = compare(
        build.declared(
            user, build.model("Team", [build.field("id", "Int")], [build.index("id", "id")])
        ),
        build.actual(
            build.table(
                "User",
                [build.column("id", "integer"), build.column("teamId", "integer")],
                [build.actual_index("User_pkey", "id", primary=True)],
            ),
            build.table(
                "Team",
                [build.column("id", "integer")],
                [build.actual_index("Team_pkey", "id", primary=True)],
                [
                    ActualForeignKey(
                        name="x",
                        columns=["id"],
                        referenced_table="User",
                        referenced_columns=["id"],
                        on_delete="CASCADE",
                        on_update="CASCADE",
                    )
                ],
            ),
        ),
    )
    assert [(f.table, f.columns, f.referenced_table) for f in report.foreign_keys_not_applied] == [
        ("User", ["teamId"], "Team")
    ]
    assert [(f.table, f.referenced_table) for f in report.foreign_keys_not_declared] == [
        ("Team", "User")
    ]
    assert to_findings(report, "schema.prisma") == []


def test_findings_carry_both_evidence_sources_and_score_against_ground_truth(build):
    report = simple(
        build,
        declared_indexes=[build.index("id", "id"), build.index("index", "createdAt", line=42)],
        actual_indexes=[
            build.actual_index("User_pkey", "id", primary=True),
            build.actual_index(
                "User_email_lower_idx",
                "lower(email)",
                referenced_columns=["email"],
                definition="CREATE INDEX ... (lower(email))",
            ),
        ],
    )
    findings = to_findings(report, "prisma/schema.prisma")
    assert sorted(f.rule_id for f in findings) == [
        "DECLARED_INDEX_NOT_APPLIED",
        "INDEX_NOT_DECLARED",
    ]
    for finding in findings:
        assert {e.source for e in finding.evidence} == {"DECLARED_SCHEMA", "ACTUAL_SCHEMA"}
        assert finding.suggested_fix and finding.suggested_fix.startswith("```")

    manifest = Manifest.model_validate(
        {
            "schemaVersion": 1,
            "app": "t",
            "entries": [
                {
                    "id": "a",
                    "problemType": "index_not_declared",
                    "category": "schema_divergence",
                    "table": "User",
                    "column": "email",
                    "expectedRuleId": "INDEX_NOT_DECLARED",
                    "description": "d",
                    "injectedAt": "2026-09-26T00:00:00Z",
                },
                {
                    "id": "b",
                    "problemType": "declared_index_not_applied",
                    "category": "schema_divergence",
                    "table": "User",
                    "column": "createdAt",
                    "expectedRuleId": "DECLARED_INDEX_NOT_APPLIED",
                    "description": "d",
                    "injectedAt": "2026-09-26T00:00:00Z",
                },
            ],
        }
    )
    result = score(findings, manifest)
    assert (result.aggregate.tp, result.aggregate.fp, result.aggregate.fn) == (2, 0, 0)


def test_fingerprints_are_stable_and_line_independent(build):
    def run(line):
        return simple(
            build,
            declared_indexes=[
                build.index("id", "id"),
                build.index("index", "createdAt", line=line),
            ],
            actual_indexes=[build.actual_index("User_pkey", "id", primary=True)],
        )

    first, second = (to_findings(run(line), "schema.prisma")[0] for line in (5, 50))
    assert first.line != second.line
    assert first.fingerprint == second.fingerprint
