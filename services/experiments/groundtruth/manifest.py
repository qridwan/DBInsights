"""Ground-truth manifest: one JSON file per test application."""

from pathlib import Path
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from .problems import PROBLEM_CATEGORY, RULE_PROBLEM_TYPES, Category, ProblemType


class _Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True
    )


class ManifestEntry(_Model):
    id: str = Field(min_length=1)
    problem_type: ProblemType
    category: Category

    # Code location, relative to the application root (the analyzer's sourceDir).
    file: str | None = None
    line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    #: HTTP endpoint that exercises the problem, e.g. "GET /api/orders".
    endpoint: str | None = None

    # Data location: actual database table and column names.
    table: str | None = None
    column: str | None = None

    expected_rule_id: str
    description: str = Field(min_length=1)
    injected_at: AwareDatetime

    @model_validator(mode="after")
    def _check(self) -> Self:
        expected_category = PROBLEM_CATEGORY[self.problem_type]
        if self.category is not expected_category:
            raise ValueError(
                f"problemType '{self.problem_type}' belongs to category "
                f"'{expected_category}', not '{self.category}'"
            )

        rule_type = RULE_PROBLEM_TYPES.get(self.expected_rule_id)
        if rule_type is None:
            raise ValueError(
                f"unknown rule '{self.expected_rule_id}'; add it to RULE_PROBLEM_TYPES"
            )
        if rule_type is not self.problem_type:
            raise ValueError(
                f"rule '{self.expected_rule_id}' detects '{rule_type}', not '{self.problem_type}'"
            )

        if self.category is Category.PERFORMANCE:
            for name, value in (
                ("file", self.file),
                ("line", self.line),
                ("endpoint", self.endpoint),
            ):
                if value is None:
                    raise ValueError(f"performance entries require '{name}'")
        elif self.table is None:
            raise ValueError(f"{self.category} entries require 'table'")

        if (self.file is None) != (self.line is None):
            raise ValueError("'file' and 'line' must be given together")
        if self.end_line is not None and (self.line is None or self.end_line < self.line):
            raise ValueError("'endLine' must be >= 'line'")
        if self.column is not None and self.table is None:
            raise ValueError("'column' requires 'table'")
        return self


class Manifest(_Model):
    schema_version: Literal[1]
    #: Application name, e.g. "ecommerce".
    app: str = Field(min_length=1)
    entries: list[ManifestEntry]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        seen: set[str] = set()
        for entry in self.entries:
            if entry.id in seen:
                raise ValueError(f"duplicate entry id '{entry.id}'")
            seen.add(entry.id)
        return self


def load_manifest(path: str | Path) -> Manifest:
    return Manifest.model_validate_json(Path(path).read_text(encoding="utf-8"))
