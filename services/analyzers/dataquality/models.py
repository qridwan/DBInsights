"""Data-quality profile records. One `ProfileRun` is one observation of an app's data."""

from datetime import UTC, datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True)


class Window(_Record):
    """Half-open interval [start, end) over a table's creation-time column (UTC)."""

    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def _ordered(self) -> "Window":
        if self.start >= self.end:
            raise ValueError("window start must be before its end")
        return self


class TableProfile(_Record):
    table: str
    row_count: int
    #: Column the window was applied to; None for snapshot (whole-table) runs.
    time_column: str | None


class ColumnProfile(_Record):
    table: str
    column: str
    data_type: str
    row_count: int
    null_count: int
    #: None when the table (or window) has no rows.
    null_rate: float | None
    distinct_count: int
    #: Fraction of non-null values that repeat another value:
    #: (non_null - distinct) / non_null. None when every value is null or there are no rows.
    duplicate_rate: float | None


class CategoryFrequency(_Record):
    table: str
    column: str
    value: str
    count: int


class IntegrityCheck(_Record):
    """One declared relation, checked against the data."""

    model: str
    relation: str
    table: str
    columns: list[str]
    referenced_table: str
    referenced_columns: list[str]
    #: Child rows whose foreign key is fully non-null (NULL keys are exempt, as in SQL).
    checked_rows: int
    orphan_rows: int
    orphan_rate: float | None
    #: Line of the relation in schema.prisma.
    line: int


class ProfileRun(_Record):
    run_id: str
    app: str
    label: str | None
    #: Wall-clock time the profile was taken.
    profiled_at: datetime
    #: Data-time window; None for a whole-table snapshot.
    window: Window | None
    max_categories: int
    #: table -> time column actually used for windowing.
    time_columns: dict[str, str]
    #: table -> why it was not profiled (windowed runs only).
    skipped_tables: dict[str, str]
    tables: list[TableProfile]
    columns: list[ColumnProfile]
    categories: list[CategoryFrequency]
    integrity: list[IntegrityCheck]

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "app": self.app,
            "label": self.label,
            "window": self.window.model_dump(mode="json") if self.window else None,
            "tables": len(self.tables),
            "columns": len(self.columns),
            "category_rows": len(self.categories),
            "integrity_checks": len(self.integrity),
            "skipped_tables": self.skipped_tables,
        }


def utcnow() -> datetime:
    return datetime.now(UTC)
