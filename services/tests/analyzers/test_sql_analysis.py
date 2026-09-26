import textwrap

import pytest

from analyzers.sql.analysis import (
    SQL_UNBOUNDED_MUTATION,
    SQL_UNBOUNDED_SELECT,
    SqlStatement,
    analyze_statements,
    split_statements,
    statements_from_repository,
)
from experiments.groundtruth import RULE_PROBLEM_TYPES, ProblemType


def captured(sql: str, route: str = "/api/things") -> SqlStatement:
    return SqlStatement(sql=sql, route=route)


def rules(sql: str) -> list[str]:
    return [f.rule_id for f in analyze_statements([captured(sql)])]


# ---- what is and is not unbounded ---------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        'SELECT "id" FROM "Thing" LIMIT $1 OFFSET $2',
        'SELECT "id" FROM "Thing" WHERE "id" = $1 LIMIT $2 OFFSET $3',
        'SELECT COUNT(*) FROM "Thing"',
        'SELECT COUNT(*), SUM("price") AS total FROM "Thing" WHERE "kind" = $1',
        "SELECT 1",
        'SELECT "id" FROM "Thing" FETCH FIRST 10 ROWS ONLY',
        'CREATE INDEX "Thing_kind_idx" ON "Thing"("kind")',
        'INSERT INTO "Thing" ("id") VALUES ($1)',
    ],
)
def test_bounded_or_aggregate_or_non_select_statements_are_not_flagged(sql):
    assert rules(sql) == []


@pytest.mark.parametrize(
    "sql",
    [
        'SELECT "id" FROM "Thing"',
        'SELECT "id" FROM "Thing" ORDER BY "id" OFFSET $1',
        'SELECT "id" FROM "Thing" WHERE "id" IN ($1,$2,$3) OFFSET $4',
        'SELECT "kind", COUNT(*) FROM "Thing" GROUP BY "kind"',
    ],
)
def test_a_select_without_a_limit_is_flagged(sql):
    assert rules(sql) == [SQL_UNBOUNDED_SELECT]


def test_confidence_is_lower_when_a_filter_narrows_the_statement():
    findings = analyze_statements(
        [
            captured('SELECT "id" FROM "Thing"'),
            captured('SELECT "id" FROM "Thing" WHERE "id" IN ($1)'),
        ]
    )
    by_filter = {"WHERE" in f.evidence[0].data["normalizedSql"]: f.confidence for f in findings}
    assert by_filter == {False: "MEDIUM", True: "LOW"}


@pytest.mark.parametrize(
    ("sql", "flagged"),
    [
        ('DELETE FROM "Thing"', True),
        ('UPDATE "Thing" SET "kind" = $1', True),
        ('DELETE FROM "Thing" WHERE "id" = $1', False),
        ('UPDATE "Thing" SET "kind" = $1 WHERE "id" = $2', False),
    ],
)
def test_mutations_without_a_where_are_flagged(sql, flagged):
    assert (rules(sql) == [SQL_UNBOUNDED_MUTATION]) is flagged


def test_unparseable_sql_is_skipped_not_fatal():
    assert rules("THIS IS (((( NOT SQL") == []


# ---- what the findings say ----------------------------------------------------------------------


def test_captured_findings_name_the_route_and_carry_sql_evidence():
    [finding] = analyze_statements([captured('SELECT "id" FROM "Thing"', route="/api/orders/[id]")])
    assert (finding.file, finding.line) == ("route:/api/orders/[id]", 0)
    assert [e.source for e in finding.evidence] == ["SQL"]
    assert finding.evidence[0].data["route"] == "/api/orders/[id]"
    assert finding.suggested_fix and finding.suggested_fix.startswith("```sql")
    assert finding.schema_version == 1


def test_repeating_the_same_statement_on_a_route_is_one_finding():
    same = captured('SELECT "id" FROM "Thing"')
    assert len(analyze_statements([same, same, captured('SELECT "id" FROM "Thing"')])) == 1
    other = captured('SELECT "id" FROM "Thing"', route="/api/other")
    assert len(analyze_statements([same, other])) == 2


def test_findings_are_deterministic_and_ordered_whatever_the_input_order():
    statements = [captured(f'SELECT "id" FROM "T{i}"', route=f"/api/{i}") for i in range(6)]
    forward = [f.model_dump_json() for f in analyze_statements(statements)]
    backward = [f.model_dump_json() for f in analyze_statements(list(reversed(statements)))]
    assert forward == backward


def test_the_unbounded_select_rule_maps_to_the_pagination_problem_type():
    assert RULE_PROBLEM_TYPES[SQL_UNBOUNDED_SELECT] is ProblemType.UNPAGINATED_FIND_MANY


# ---- statements found in a repository -----------------------------------------------------------


def test_statements_are_split_with_their_line_numbers():
    text = textwrap.dedent(
        """\
        -- a comment; with a semicolon
        CREATE TABLE "T" ("id" integer);

        DELETE FROM "T"; UPDATE "T" SET "x" = 'a;b'
          WHERE "id" = 1;
        """
    )
    found = [(line, sql.split()[0]) for line, sql in split_statements(text)]
    assert found == [(2, "CREATE"), (4, "DELETE"), (4, "UPDATE")]
    literal = split_statements(text)[2][1]
    assert "'a;b'" in literal, "a semicolon inside a string literal does not split"


def test_repository_statements_come_from_sql_files_with_paths_relative_to_the_root(tmp_path):
    (tmp_path / "prisma" / "migrations" / "001").mkdir(parents=True)
    (tmp_path / "prisma" / "migrations" / "001" / "migration.sql").write_text(
        'CREATE TABLE "T" ("id" integer);\nDELETE FROM "T";\n'
    )
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "ignored.sql").write_text('DELETE FROM "Never";')
    statements = statements_from_repository(tmp_path)
    assert [(s.file, s.line) for s in statements] == [
        ("prisma/migrations/001/migration.sql", 1),
        ("prisma/migrations/001/migration.sql", 2),
    ]
    findings = analyze_statements(statements)
    assert [(f.rule_id, f.file, f.line) for f in findings] == [
        (SQL_UNBOUNDED_MUTATION, "prisma/migrations/001/migration.sql", 2)
    ]
