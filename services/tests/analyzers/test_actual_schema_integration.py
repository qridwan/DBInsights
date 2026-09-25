"""Reads a real PostgreSQL catalog. Skipped unless DBINSIGHT_TEST_DATABASE_URL is set."""

import os
import uuid

import pytest

pytestmark = pytest.mark.integration

URL = os.environ.get("DBINSIGHT_TEST_DATABASE_URL")


@pytest.fixture
def probe_schema():
    if not URL:
        pytest.skip("DBINSIGHT_TEST_DATABASE_URL not set")
    import psycopg

    name = f"dbinsight_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{name}"')
        conn.execute(f'SET search_path TO "{name}"')
        conn.execute("CREATE TYPE \"Mood\" AS ENUM ('HAPPY', 'SAD')")
        conn.execute('CREATE TABLE "Team" ("id" UUID PRIMARY KEY, "name" TEXT NOT NULL)')
        conn.execute(
            'CREATE TABLE "User" ("id" UUID PRIMARY KEY, "email" TEXT NOT NULL, '
            '"nick" VARCHAR(20), "mood" "Mood" NOT NULL, "tags" TEXT[], '
            '"createdAt" TIMESTAMP(3) NOT NULL, '
            '"teamId" UUID NOT NULL REFERENCES "Team"("id") ON DELETE CASCADE, '
            'CONSTRAINT "User_nick_check" CHECK (char_length("nick") > 1))'
        )
        conn.execute('CREATE UNIQUE INDEX "User_email_key" ON "User"("email")')
        conn.execute('CREATE INDEX "User_team_created_idx" ON "User"("teamId", "createdAt" DESC)')
        conn.execute('CREATE INDEX "User_email_lower_idx" ON "User"(lower("email"))')
        conn.execute(
            'CREATE INDEX "User_happy_idx" ON "User"("createdAt") WHERE "mood" = \'HAPPY\''
        )
        conn.execute('CREATE INDEX "User_email_incl_idx" ON "User"("email") INCLUDE ("nick")')
        try:
            yield name
        finally:
            conn.execute(f'DROP SCHEMA "{name}" CASCADE')


def test_reads_tables_columns_indexes_foreign_keys_and_constraints(probe_schema):
    from analyzers.schema.actual import connect, read_actual_schema

    with connect(URL) as conn:
        schema = read_actual_schema(conn, probe_schema)

    assert [t.name for t in schema.tables] == ["Team", "User"]
    user = schema.table("User")
    assert [(c.name, c.data_type, c.nullable) for c in user.columns] == [
        ("id", "uuid", False),
        ("email", "text", False),
        ("nick", "character varying(20)", True),
        ("mood", '"Mood"', False),
        ("tags", "text[]", True),
        ("createdAt", "timestamp(3) without time zone", False),
        ("teamId", "uuid", False),
    ]

    indexes = {i.name: i for i in user.indexes}
    assert indexes["User_pkey"].kind == "primary"
    assert indexes["User_email_key"].kind == "unique"
    assert indexes["User_team_created_idx"].columns == ["teamId", "createdAt"]
    assert indexes["User_email_lower_idx"].columns == ["lower(email)"]
    assert indexes["User_email_lower_idx"].referenced_columns == ["email"]
    assert indexes["User_email_lower_idx"].has_expression
    assert (
        indexes["User_happy_idx"].predicate is not None
        and "HAPPY" in indexes["User_happy_idx"].predicate
    )
    assert indexes["User_email_incl_idx"].columns == ["email"], (
        "INCLUDE columns are not key columns"
    )

    assert [(fk.columns, fk.referenced_table, fk.on_delete) for fk in user.foreign_keys] == [
        (["teamId"], "Team", "CASCADE")
    ]
    assert {c.type for c in user.constraints} == {"primary_key", "check", "foreign_key"}


def test_connection_is_read_only(probe_schema):
    import psycopg

    from analyzers.schema.actual import connect

    with connect(URL) as conn, pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        conn.execute(f'CREATE TABLE "{probe_schema}".nope (id int)')
