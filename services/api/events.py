"""Runtime events as sent by @dbinsight/collector (packages/collector/src/types.ts)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _Event(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True
    )


class StatementEvent(_Event):
    sql: str
    param_count: int = Field(ge=0)
    kind: Literal["query", "execute"]
    duration_ms: float = Field(ge=0)
    rows: int | None


class OperationEvent(_Event):
    schema_version: Literal[1]
    app: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    request_id: str | None
    route: str | None
    model: str | None
    operation: str = Field(min_length=1)
    started_at: datetime
    duration_ms: float = Field(ge=0)
    rows_returned: int | None
    error: bool
    statements: list[StatementEvent]
