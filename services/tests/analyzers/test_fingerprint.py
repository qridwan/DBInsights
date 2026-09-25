import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from analyzers.sql import fingerprint, naive_normalize

REPO = Path(__file__).parents[3]
RECORDED = json.loads((REPO / "fixtures" / "sql" / "prisma-in-variants.json").read_text())


def recorded(name: str) -> dict[int, list[str]]:
    query = next(q for q in RECORDED["queries"] if q["name"] == name)
    return {v["size"]: v["sql"] for v in query["variants"]}


def test_prisma_in_list_with_1_5_and_50_ids_is_one_fingerprint():
    """The M3.2 acceptance test, on SQL recorded from real Prisma 7."""
    variants = recorded("findMany where id IN list")
    assert sorted(variants) == [1, 5, 50]
    statements = [sqls[0] for sqls in variants.values()]
    assert len(set(statements)) == 3, "Prisma really sends three different strings"
    assert len({fingerprint(sql).id for sql in statements}) == 1
    assert all(fingerprint(sql).parsed for sql in statements)


def test_literal_substitution_alone_fragments_the_same_query():
    """Documents the pg_stat_statements-style failure mode this module avoids."""
    statements = [sqls[0] for sqls in recorded("findMany where id IN list").values()]
    assert len({naive_normalize(sql) for sql in statements}) == 3


def test_every_statement_of_an_include_query_collapses_per_position():
    variants = recorded("findMany with include and IN list")
    for position in range(3):
        assert len({fingerprint(sqls[position]).id for sqls in variants.values()}) == 1


def test_batched_find_unique_keeps_the_single_row_shape_distinct():
    # Prisma batches concurrent findUnique calls into one IN query, but sends a
    # genuinely different statement (= $1 ... LIMIT) for a single call.
    variants = recorded("findUnique batched by Promise.all")
    assert fingerprint(variants[5][0]).id == fingerprint(variants[50][0]).id
    assert fingerprint(variants[1][0]).id != fingerprint(variants[5][0]).id


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ('SELECT * FROM "t" WHERE "id" = 1', 'SELECT * FROM "t" WHERE "id" = 2'),
        ('SELECT * FROM "t" WHERE "name" = \'a\'', 'SELECT * FROM "t" WHERE "name" = \'bb\''),
        ('SELECT * FROM "t" WHERE "id" = $1', 'SELECT * FROM "t" WHERE "id" = $7'),
        ('SELECT * FROM "t" WHERE "ok" = true', 'SELECT * FROM "t" WHERE "ok" = false'),
        ('SELECT * FROM "t" LIMIT 10 OFFSET 0', 'SELECT * FROM "t" LIMIT 50 OFFSET 100'),
        (
            'SELECT * FROM "t" WHERE "id" = ANY(ARRAY[1,2])',
            'SELECT * FROM "t" WHERE "id" = ANY(ARRAY[1,2,3,4])',
        ),
        ('INSERT INTO "t" ("a") VALUES ($1)', 'INSERT INTO "t" ("a") VALUES ($1), ($2), ($3)'),
        ('SELECT  *\nFROM "t" -- note\nWHERE "id" = 1', 'SELECT * FROM "t" WHERE "id" = 3'),
    ],
)
def test_values_arity_whitespace_and_comments_do_not_change_the_shape(a, b):
    assert fingerprint(a).id == fingerprint(b).id


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ('SELECT * FROM "t" WHERE "id" = 1', 'SELECT * FROM "u" WHERE "id" = 1'),
        ('SELECT * FROM "t" WHERE "id" = 1', 'SELECT * FROM "t" WHERE "other" = 1'),
        ('SELECT * FROM "t" WHERE "id" = $1', 'SELECT * FROM "t" WHERE "id" IN ($1, $2)'),
        ('SELECT * FROM "t" WHERE "id" > $1', 'SELECT * FROM "t" WHERE "id" < $1'),
        ('SELECT * FROM "t" ORDER BY "a"', 'SELECT * FROM "t" ORDER BY "b"'),
        ('SELECT * FROM "t"', 'SELECT * FROM "t" LIMIT 10'),
        ('SELECT "a" FROM "t"', 'SELECT "a", "b" FROM "t"'),
        ('SELECT * FROM "t" WHERE "x" IS NULL', 'SELECT * FROM "t" WHERE "x" = $1'),
    ],
)
def test_structural_differences_stay_distinct(a, b):
    assert fingerprint(a).id != fingerprint(b).id


def test_unparseable_sql_falls_back_but_still_collapses_lists():
    first = fingerprint("FROBNICATE widgets WHERE id IN ($1,$2)")
    second = fingerprint("FROBNICATE widgets WHERE id IN ($1,$2,$3,$4)")
    assert not first.parsed
    assert first.id == second.id


def test_fingerprints_are_deterministic():
    sql = recorded("findMany where id IN list")[50][0]
    assert fingerprint(sql) == fingerprint(sql)
    assert len(fingerprint(sql).id) == 16


LIVE_URL = os.environ.get("DBINSIGHT_ECOMMERCE_DATABASE_URL")


@pytest.mark.integration
@pytest.mark.skipif(
    not LIVE_URL or not shutil.which("pnpm"), reason="needs a seeded ecommerce DB and pnpm"
)
def test_freshly_generated_prisma_in_variants_collapse():
    """Generates the same logical Prisma query with 1, 5 and 50 ids now, via the collector."""
    completed = subprocess.run(
        ["pnpm", "--filter", "@dbinsight/collector", "exec", "tsx", "scripts/record-prisma-sql.ts"],
        cwd=REPO,
        env={**os.environ, "DATABASE_URL": LIVE_URL},
        capture_output=True,
        text=True,
        check=True,
    )
    queries = json.loads(completed.stdout[completed.stdout.index("{") :])["queries"]
    in_list = next(q for q in queries if q["name"] == "findMany where id IN list")
    statements = [v["sql"][0] for v in in_list["variants"]]
    assert [v["size"] for v in in_list["variants"]] == [1, 5, 50]
    assert len({fingerprint(sql).id for sql in statements}) == 1
