from typing import Any

import pytest

from analyzers.schema.actual import (
    ActualColumn,
    ActualForeignKey,
    ActualIndex,
    ActualSchema,
    ActualTable,
)
from analyzers.schema.declared import DeclaredSchema


def field(name: str, type_: str = "String", **overrides: Any) -> dict[str, Any]:
    base = {
        "name": name,
        "type": type_,
        "kind": "scalar",
        "optional": False,
        "list": False,
        "attributes": [],
        "line": 1,
    }
    base.update(overrides)
    return base


def native(name: str, *numbers: int) -> dict[str, Any]:
    return {
        "name": f"db.{name}",
        "args": [{"value": {"kind": "number", "value": n}} for n in numbers],
        "line": 1,
    }


def index(kind: str, *fields: str, line: int = 1, **extra: Any) -> dict[str, Any]:
    return {
        "kind": kind,
        "fields": [{"name": f} for f in fields],
        "declaredOn": "block",
        "line": line,
        **extra,
    }


def model(
    name: str, fields: list[dict[str, Any]], indexes: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    return {
        "name": name,
        "blockType": "model",
        "fields": fields,
        "relations": [],
        "indexes": indexes,
        "line": 10,
        **extra,
    }


def declared(*models: dict[str, Any], enums: list[dict[str, Any]] | None = None) -> DeclaredSchema:
    return DeclaredSchema.model_validate({"models": list(models), "enums": enums or []})


def column(
    name: str, data_type: str = "text", nullable: bool = False, position: int = 1
) -> ActualColumn:
    return ActualColumn(
        name=name, data_type=data_type, nullable=nullable, default=None, position=position
    )


def actual_index(
    name: str, *columns: str, unique: bool = False, primary: bool = False, **extra: Any
) -> ActualIndex:
    referenced = extra.pop("referenced_columns", list(columns))
    return ActualIndex(
        name=name,
        columns=list(columns),
        referenced_columns=referenced,
        unique=unique or primary,
        primary=primary,
        method=extra.pop("method", "btree"),
        predicate=extra.pop("predicate", None),
        definition=extra.pop("definition", f"CREATE INDEX {name}"),
    )


def table(
    name: str,
    columns: list[ActualColumn],
    indexes: list[ActualIndex],
    fks: list[ActualForeignKey] | None = None,
) -> ActualTable:
    return ActualTable(
        name=name, columns=columns, indexes=indexes, foreign_keys=fks or [], constraints=[]
    )


def actual(*tables: ActualTable) -> ActualSchema:
    return ActualSchema(schema_name="public", tables=list(tables))


@pytest.fixture
def build():
    class Build:
        pass

    for fn in (field, native, index, model, declared, column, actual_index, table, actual):
        setattr(Build, fn.__name__, staticmethod(fn))
    return Build
