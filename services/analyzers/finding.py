"""Python mirror of the TypeScript `Finding` contract (packages/core/src/models.ts).

Shared by every Python layer: analyzers produce findings in this shape and the
ground-truth scorer consumes them.

Its shape must match schemaVersion 1 exactly; never change it without bumping
the version on both sides.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter
from pydantic.alias_generators import to_camel

Level = Literal["LOW", "MEDIUM", "HIGH"]
EvidenceSource = Literal[
    "STATIC_SOURCE", "DECLARED_SCHEMA", "ACTUAL_SCHEMA", "SQL", "RUNTIME", "DATA_QUALITY"
]


class _Contract(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True
    )


class Evidence(_Contract):
    source: EvidenceSource
    description: str
    file: str | None = None
    line: int | None = None
    data: dict[str, Any] | None = None


class Finding(_Contract):
    schema_version: Literal[1]
    rule_id: str
    severity: Level
    confidence: Level
    file: str
    line: int
    end_line: int | None = None
    title: str
    body: str
    evidence: list[Evidence]
    suggested_fix: str | None = None
    fingerprint: str


_FINDINGS = TypeAdapter(list[Finding])


def parse_findings(raw: Any) -> list[Finding]:
    """Validates a JSON-decoded list of findings (as emitted by `analyze()`)."""
    return _FINDINGS.validate_python(raw)
