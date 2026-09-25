"""The DECLARED schema: schema.prisma, as parsed by the TypeScript core.

A Python mirror of `SchemaModel` (packages/core/src/schema/types.ts). It is
one of two evidence sources for RQ6 and is deliberately a separate type from
`ActualSchema`; nothing merges the two.
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from ..core_bridge import parse_schema


class _Mirror(BaseModel):
    # Mirrors TS output: ignore fields added on the TS side later rather than
    # failing, but never invent any.
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore", frozen=True
    )


class DeclaredAttribute(_Mirror):
    name: str
    args: list[dict[str, Any]] = []
    line: int


class DeclaredField(_Mirror):
    name: str
    type: str
    kind: Literal["scalar", "enum", "relation", "composite", "unsupported"]
    optional: bool
    list: bool
    db_name: str | None = None
    attributes: list[DeclaredAttribute] = []
    line: int

    @property
    def column(self) -> str:
        return self.db_name or self.name


class DeclaredIndexField(_Mirror):
    name: str
    sort: Literal["Asc", "Desc"] | None = None
    length: int | None = None
    ops: str | None = None


class DeclaredIndex(_Mirror):
    kind: Literal["id", "unique", "index", "fulltext"]
    fields: list[DeclaredIndexField]
    declared_on: Literal["field", "block"]
    name: str | None = None
    map: str | None = None
    type: str | None = None
    line: int


class DeclaredRelation(_Mirror):
    field: str
    referenced_model: str
    fields: list[str]
    references: list[str]
    foreign_key_on: Literal["self", "referenced", "implicit-many-to-many", "unknown"]
    name: str | None = None
    line: int


class DeclaredModel(_Mirror):
    name: str
    block_type: Literal["model", "view"]
    db_name: str | None = None
    fields: list[DeclaredField]
    relations: list[DeclaredRelation]
    indexes: list[DeclaredIndex]
    line: int

    @property
    def table(self) -> str:
        return self.db_name or self.name

    def field(self, name: str) -> DeclaredField | None:
        return next((f for f in self.fields if f.name == name), None)


class DeclaredEnum(_Mirror):
    name: str
    db_name: str | None = None
    values: list[str]
    line: int


class DeclaredSchema(_Mirror):
    models: list[DeclaredModel]
    enums: list[DeclaredEnum]

    def model(self, name: str) -> DeclaredModel | None:
        return next((m for m in self.models if m.name == name), None)

    def enum(self, name: str) -> DeclaredEnum | None:
        return next((e for e in self.enums if e.name == name), None)


def load_declared_schema(schema_path: str | Path) -> DeclaredSchema:
    """Parses schema.prisma through the TypeScript core (no DB access)."""
    return DeclaredSchema.model_validate(parse_schema(schema_path))


# ---------------------------------------------------------------------------
# Column types Prisma creates on PostgreSQL, written as `format_type()` prints
# them. Verified against `prisma migrate diff` output and a live Postgres 16.
# ---------------------------------------------------------------------------

_SCALAR_TYPES = {
    "String": "text",
    "Boolean": "boolean",
    "Int": "integer",
    "BigInt": "bigint",
    "Float": "double precision",
    "Decimal": "numeric(65,30)",
    "DateTime": "timestamp(3) without time zone",
    "Json": "jsonb",
    "Bytes": "bytea",
}

# Native type attribute -> format_type() template; {args} receives "(p[,s])" when given.
_NATIVE_TYPES: dict[str, str] = {
    "Text": "text",
    "Uuid": "uuid",
    "Boolean": "boolean",
    "Integer": "integer",
    "SmallInt": "smallint",
    "BigInt": "bigint",
    "Oid": "oid",
    "Real": "real",
    "DoublePrecision": "double precision",
    "Money": "money",
    "Date": "date",
    "Json": "json",
    "JsonB": "jsonb",
    "ByteA": "bytea",
    "Xml": "xml",
    "Inet": "inet",
    "Citext": "citext",
    "VarChar": "character varying{args}",
    "Char": "character{args}",
    "Bit": "bit{args}",
    "VarBit": "bit varying{args}",
    "Decimal": "numeric{args}",
    "Timestamp": "timestamp{args} without time zone",
    "Timestamptz": "timestamp{args} with time zone",
    "Time": "time{args} without time zone",
    "Timetz": "time{args} with time zone",
}


def _numeric_args(attribute: DeclaredAttribute) -> list[int]:
    values: list[int] = []
    for argument in attribute.args:
        value = argument.get("value", {})
        if value.get("kind") == "number":
            values.append(int(value["value"]))
    return values


def expected_column_type(field: DeclaredField, schema: DeclaredSchema) -> str | None:
    """The `format_type()` string Prisma would create, or None if not derivable."""
    native = next((a for a in field.attributes if a.name.startswith("db.")), None)
    if native is not None:
        template = _NATIVE_TYPES.get(native.name.removeprefix("db."))
        if template is None:
            return None
        args = _numeric_args(native)
        base = template.format(args=f"({','.join(map(str, args))})" if args else "")
    elif field.kind == "enum":
        enum = schema.enum(field.type)
        base = enum.db_name if enum and enum.db_name else field.type
    elif field.kind == "scalar":
        base = _SCALAR_TYPES.get(field.type)
        if base is None:
            return None
    else:
        return None
    return f"{base}[]" if field.list else base


def expected_nullable(field: DeclaredField) -> bool:
    # Prisma creates scalar lists without NOT NULL.
    return field.optional or field.list
