"""The read-only view of a finding that the explanation layer is allowed to see.

A `Finding` is never passed into the layer's prompt-building or model-calling code. This module
turns it into a `FindingView`: frozen, made only of strings, integers and tuples, holding just
what an explanation needs. The view has no fingerprint, and no path back to the Finding it came
from, so nothing done with it can reach the finding's type, severity or confidence.

Severity and confidence ARE included, as fixed context, so the explanation can be phrased
appropriately (for example hedged when confidence is low). They are read-only text; the model is
told they are settled and must not be disputed, and its reply cannot carry them (contract.py).
"""

import json
from dataclasses import dataclass

from analyzers.finding import Finding

#: Longest evidence `data` payload passed to the model, in characters. Keeps prompts bounded.
MAX_DATA_CHARS = 2000


@dataclass(frozen=True)
class EvidenceView:
    source: str
    description: str
    file: str | None
    line: int | None
    #: Canonical JSON of the evidence's structured data, or None.
    data: str | None


@dataclass(frozen=True)
class FindingView:
    rule_id: str
    title: str
    body: str
    file: str
    line: int
    severity: str
    confidence: str
    evidence: tuple[EvidenceView, ...]
    suggested_fix: str | None


def _canonical(data: dict | None) -> str | None:
    if data is None:
        return None
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    if len(text) > MAX_DATA_CHARS:
        return text[:MAX_DATA_CHARS] + "...(truncated)"
    return text


def project(finding: Finding) -> FindingView:
    return FindingView(
        rule_id=finding.rule_id,
        title=finding.title,
        body=finding.body,
        file=finding.file,
        line=finding.line,
        severity=finding.severity,
        confidence=finding.confidence,
        evidence=tuple(
            EvidenceView(e.source, e.description, e.file, e.line, _canonical(e.data))
            for e in finding.evidence
        ),
        suggested_fix=finding.suggested_fix,
    )
