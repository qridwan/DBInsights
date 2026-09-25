import pytest

from analyzers.schema.declared import expected_column_type, expected_nullable

# Expected values were observed on PostgreSQL 16 by applying Prisma's own
# `migrate diff` output and reading format_type() back.
CASES = [
    ({"type": "String"}, "text"),
    ({"type": "Int"}, "integer"),
    ({"type": "BigInt"}, "bigint"),
    ({"type": "Float"}, "double precision"),
    ({"type": "Decimal"}, "numeric(65,30)"),
    ({"type": "Boolean"}, "boolean"),
    ({"type": "DateTime"}, "timestamp(3) without time zone"),
    ({"type": "Json"}, "jsonb"),
    ({"type": "Bytes"}, "bytea"),
    ({"type": "String", "list": True}, "text[]"),
    ({"type": "String", "native": ("Uuid",)}, "uuid"),
    ({"type": "String", "native": ("VarChar", 255)}, "character varying(255)"),
    ({"type": "String", "native": ("VarChar",)}, "character varying"),
    ({"type": "String", "native": ("Char", 3)}, "character(3)"),
    ({"type": "Decimal", "native": ("Decimal", 10, 2)}, "numeric(10,2)"),
    ({"type": "DateTime", "native": ("Timestamp",)}, "timestamp without time zone"),
    ({"type": "DateTime", "native": ("Timestamptz", 6)}, "timestamp(6) with time zone"),
    ({"type": "DateTime", "native": ("Date",)}, "date"),
    ({"type": "Int", "native": ("SmallInt",)}, "smallint"),
    ({"type": "Json", "native": ("Json",)}, "json"),
    ({"type": "Json", "native": ("JsonB",)}, "jsonb"),
]


@pytest.mark.parametrize(("spec", "expected"), CASES, ids=[e for _, e in CASES])
def test_expected_column_type_matches_what_prisma_creates(build, spec, expected):
    native = spec.pop("native", None)
    attributes = [build.native(*native)] if native else []
    schema = build.declared(build.model("T", [build.field("c", attributes=attributes, **spec)], []))
    assert expected_column_type(schema.models[0].fields[0], schema) == expected


def test_enum_columns_use_the_enum_type_name_or_its_map(build):
    schema = build.declared(
        build.model(
            "T", [build.field("a", "Mood", kind="enum"), build.field("b", "Level", kind="enum")], []
        ),
        enums=[
            {"name": "Mood", "values": ["HAPPY"], "line": 1},
            {"name": "Level", "dbName": "level", "values": ["A"], "line": 1},
        ],
    )
    assert [expected_column_type(f, schema) for f in schema.models[0].fields] == ["Mood", "level"]


def test_unknown_native_types_are_not_guessed(build):
    schema = build.declared(
        build.model("T", [build.field("c", attributes=[build.native("Geometry")])], [])
    )
    assert expected_column_type(schema.models[0].fields[0], schema) is None


@pytest.mark.parametrize(
    ("optional", "list_", "nullable"),
    [(False, False, False), (True, False, True), (False, True, True)],
)
def test_nullability_follows_optional_and_prisma_list_columns(build, optional, list_, nullable):
    schema = build.declared(build.model("T", [build.field("c", optional=optional, list=list_)], []))
    assert expected_nullable(schema.models[0].fields[0]) is nullable
