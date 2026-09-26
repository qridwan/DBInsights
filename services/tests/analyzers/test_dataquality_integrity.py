import pytest

from analyzers.dataquality import check_integrity, to_findings
from analyzers.dataquality.integrity import ORPHANED_FOREIGN_KEY
from analyzers.dataquality.models import IntegrityCheck
from analyzers.schema.actual import connect, read_actual_schema
from experiments.groundtruth import Manifest, score

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def relation(field, referenced, fields, references, *, line=1, kind="self"):
    return {
        "field": field,
        "referencedModel": referenced,
        "fields": fields,
        "references": references,
        "foreignKeyOn": kind,
        "line": line,
    }


@pytest.fixture
def declared(build):
    f = build.field
    team = build.model("Team", [f("id", "Int")], [])
    user = build.model(
        "User",
        [f("id", "Int"), f("teamId", "Int", optional=True), f("mentorId", "Int", optional=True)],
        [],
        relations=[
            relation("team", "Team", ["teamId"], ["id"], line=21),
            relation("mentor", "User", ["mentorId"], ["id"], line=22),
            relation("posts", "Post", [], [], kind="referenced"),  # back-relation: not checked
            relation("groups", "Group", [], [], kind="implicit-many-to-many"),
        ],
    )
    edition = build.model("Edition", [f("year", "Int"), f("number", "Int")], [])
    article = build.model(
        "Article",
        [f("id", "Int"), f("editionYear", "Int"), f("editionNo", "Int", optional=True)],
        [],
        relations=[
            relation(
                "edition", "Edition", ["editionYear", "editionNo"], ["year", "number"], line=30
            )
        ],
    )
    # @@map / @map: model Account lives in table "accounts", column "owner_id".
    account = build.model(
        "Account",
        [f("id", "Int"), f("ownerId", "Int", dbName="owner_id")],
        [],
        dbName="accounts",
        relations=[relation("owner", "Team", ["ownerId"], ["id"], line=40)],
    )
    ghost = build.model(
        "Ghost",
        [f("id", "Int"), f("teamId", "Int")],
        [],
        relations=[relation("team", "Team", ["teamId"], ["id"], line=50)],
    )
    return build.declared(team, user, edition, article, account, ghost)


@pytest.fixture
def db(temp_schema):
    c = temp_schema.conn
    # Deliberately no FOREIGN KEY constraints: that is how orphans can exist.
    c.execute('CREATE TABLE "Team" ("id" integer PRIMARY KEY)')
    c.execute('INSERT INTO "Team" VALUES (1), (2)')
    c.execute(
        'CREATE TABLE "User" ("id" integer PRIMARY KEY, "teamId" integer, "mentorId" integer)'
    )
    c.execute(
        """INSERT INTO "User" VALUES
           (1, 1,    NULL),
           (2, 2,    1),
           (3, 99,   1),
           (4, NULL, 2),
           (5, 98,   99)"""
    )
    c.execute(
        'CREATE TABLE "Edition" ("year" integer, "number" integer, PRIMARY KEY ("year", "number"))'
    )
    c.execute('INSERT INTO "Edition" VALUES (2020, 1), (2020, 2)')
    c.execute(
        'CREATE TABLE "Article" ("id" integer PRIMARY KEY, "editionYear" integer, '
        '"editionNo" integer)'
    )
    c.execute(
        """INSERT INTO "Article" VALUES
           (1, 2020, 1), (2, 2020, 3), (3, 2021, 1), (4, 2020, NULL), (5, 2020, 2)"""
    )
    c.execute('CREATE TABLE "accounts" ("id" integer PRIMARY KEY, "owner_id" integer)')
    c.execute("INSERT INTO accounts VALUES (1, 1), (2, 77)")
    with connect(temp_schema.url) as conn:
        yield conn, read_actual_schema(conn, temp_schema.name)


def by_relation(checks):
    return {f"{c.model}.{c.relation}": c for c in checks}


def test_counts_orphans_among_non_null_keys(db, declared):
    conn, actual = db
    checks, _ = check_integrity(conn, declared, actual)
    team = by_relation(checks)["User.team"]
    # Non-null teamId: users 1,2,3,5. Team 99 and 98 do not exist. NULL (user 4) is exempt.
    assert (team.checked_rows, team.orphan_rows) == (4, 2)
    assert team.orphan_rate == 0.5
    assert (team.table, team.columns, team.referenced_table, team.line) == (
        "User",
        ["teamId"],
        "Team",
        21,
    )


def test_self_relations_are_checked(db, declared):
    conn, actual = db
    mentor = by_relation(check_integrity(conn, declared, actual)[0])["User.mentor"]
    # mentorId non-null: users 2,3,4,5 -> 1,1,2,99. Only 99 has no user.
    assert (mentor.checked_rows, mentor.orphan_rows) == (4, 1)


def test_composite_keys_match_on_every_column_and_partial_nulls_are_exempt(db, declared):
    conn, actual = db
    edition = by_relation(check_integrity(conn, declared, actual)[0])["Article.edition"]
    # (2020,1) ok, (2020,3) orphan, (2021,1) orphan, (2020,NULL) exempt, (2020,2) ok.
    assert (edition.checked_rows, edition.orphan_rows) == (4, 2)
    assert edition.columns == ["editionYear", "editionNo"]


def test_mapped_table_and_column_names_are_used(db, declared):
    conn, actual = db
    owner = by_relation(check_integrity(conn, declared, actual)[0])["Account.owner"]
    assert (owner.table, owner.columns, owner.checked_rows, owner.orphan_rows) == (
        "accounts",
        ["owner_id"],
        2,
        1,
    )


def test_back_relations_and_implicit_many_to_many_are_not_checked(db, declared):
    conn, actual = db
    checks, _ = check_integrity(conn, declared, actual)
    assert set(by_relation(checks)) == {
        "User.team",
        "User.mentor",
        "Article.edition",
        "Account.owner",
    }


def test_relations_that_cannot_be_checked_are_reported_not_hidden(db, declared):
    conn, actual = db
    _, skipped = check_integrity(conn, declared, actual)
    assert skipped == {"Ghost.team": "table or columns missing from the database"}


def test_a_clean_relation_reports_zero_orphans(temp_schema, build):
    c = temp_schema.conn
    c.execute('CREATE TABLE "Team" ("id" integer PRIMARY KEY)')
    c.execute('CREATE TABLE "User" ("id" integer PRIMARY KEY, "teamId" integer)')
    c.execute('INSERT INTO "Team" VALUES (1)')
    c.execute('INSERT INTO "User" VALUES (1, 1), (2, NULL)')
    f = build.field
    schema = build.declared(
        build.model("Team", [f("id", "Int")], []),
        build.model(
            "User",
            [f("id", "Int"), f("teamId", "Int", optional=True)],
            [],
            relations=[relation("team", "Team", ["teamId"], ["id"])],
        ),
    )
    with connect(temp_schema.url) as conn:
        checks, _ = check_integrity(conn, schema, read_actual_schema(conn, temp_schema.name))
    assert [(x.checked_rows, x.orphan_rows) for x in checks] == [(1, 0)]
    assert to_findings(checks, "prisma/schema.prisma") == []


def test_an_empty_child_table_has_an_undefined_rate(temp_schema, build):
    c = temp_schema.conn
    c.execute('CREATE TABLE "Team" ("id" integer PRIMARY KEY)')
    c.execute('CREATE TABLE "User" ("id" integer PRIMARY KEY, "teamId" integer)')
    f = build.field
    schema = build.declared(
        build.model("Team", [f("id", "Int")], []),
        build.model(
            "User",
            [f("id", "Int"), f("teamId", "Int")],
            [],
            relations=[relation("team", "Team", ["teamId"], ["id"])],
        ),
    )
    with connect(temp_schema.url) as conn:
        checks, _ = check_integrity(conn, schema, read_actual_schema(conn, temp_schema.name))
    assert (checks[0].checked_rows, checks[0].orphan_rate) == (0, None)


# ---- findings (no database) ---------------------------------------------------------------


def check(orphans, checked=100, **overrides):
    values = {
        "model": "User",
        "relation": "team",
        "table": "User",
        "columns": ["teamId"],
        "referenced_table": "Team",
        "referenced_columns": ["id"],
        "checked_rows": checked,
        "orphan_rows": orphans,
        "orphan_rate": orphans / checked if checked else None,
        "line": 21,
    }
    values.update(overrides)
    return IntegrityCheck(**values)


def test_findings_only_for_relations_with_orphans():
    findings = to_findings(
        [check(0), check(7, model="Article", relation="edition", table="Article")], "schema.prisma"
    )
    assert [f.rule_id for f in findings] == [ORPHANED_FOREIGN_KEY]
    assert findings[0].title.startswith("7 orphaned Article(teamId) rows")


def test_finding_carries_data_and_declared_schema_evidence():
    [finding] = to_findings([check(7)], "prisma/schema.prisma")
    assert (finding.severity, finding.confidence, finding.line) == ("MEDIUM", "HIGH", 21)
    assert [e.source for e in finding.evidence] == ["DATA_QUALITY", "DECLARED_SCHEMA"]
    data = finding.evidence[0].data
    assert (data["table"], data["column"], data["orphanRows"], data["checkedRows"]) == (
        "User",
        "teamId",
        7,
        100,
    )
    assert finding.suggested_fix.startswith("```sql")


def test_fingerprint_ignores_counts_and_line_numbers():
    [a] = to_findings([check(7, line=21)], "schema.prisma")
    [b] = to_findings([check(700, checked=9000, line=99)], "schema.prisma")
    assert a.fingerprint == b.fingerprint


def test_integrity_findings_score_against_a_ground_truth_entry():
    manifest = Manifest.model_validate(
        {
            "schemaVersion": 1,
            "app": "t",
            "entries": [
                {
                    "id": "o1",
                    "problemType": "orphaned_foreign_key",
                    "category": "data_quality",
                    "table": "User",
                    "column": "teamId",
                    "expectedRuleId": "ORPHANED_FOREIGN_KEY",
                    "description": "d",
                    "injectedAt": "2026-09-26T00:00:00Z",
                }
            ],
        }
    )
    result = score(to_findings([check(7)], "schema.prisma"), manifest)
    assert (result.aggregate.tp, result.aggregate.fp, result.aggregate.fn) == (1, 0, 0)
