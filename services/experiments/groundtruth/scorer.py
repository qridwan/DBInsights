"""Scores findings against a ground-truth manifest.

This module is the only place results are computed. Everything downstream
(ablation, statistics, the thesis tables) consumes its output; nothing counts
TP/FP/FN by hand.

Matching
--------
A finding matches an entry when both hold:

1. Problem type: the finding's rule maps (via RULE_PROBLEM_TYPES) to the
   entry's problem type. Any rule of that type counts, so a problem reported
   by the static rule or by a runtime/correlated rule scores the same.
2. Location, any of:
   - code: same file, and the finding's [line, endLine] overlaps the entry's
     [line, endLine];
   - data: an evidence item's `data` names the entry's table (and column, when
     the entry has one) as `table` plus `column` or `columns`. Comparison is
     case-insensitive and ignores quoting and a `public.` schema prefix;
   - endpoint: an evidence item's `data.route` is the entry's endpoint path.
     Runtime findings have no source line and locate themselves this way.
     `/api/orders/[id]` (Next.js) and `/api/orders/:id` (manifest) are the
     same pattern; the HTTP method and query string are ignored.

Entries and findings are paired one-to-one by maximum bipartite matching, so
the result does not depend on input order. A matched pair is a true positive.
An unmatched entry is a false negative. An unmatched finding is a false
positive, unless it could have matched an entry that another finding already
claimed: then it is a duplicate, reported separately and not counted as FP.
Findings whose rule has no ground-truth problem type are unmapped false
positives: they count in the aggregate, not in any problem type.
"""

from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, computed_field
from pydantic.alias_generators import to_camel

from .finding import Finding
from .manifest import Manifest, ManifestEntry
from .problems import PROBLEM_CATEGORY, RULE_PROBLEM_TYPES, Category, ProblemType


class _Report(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


class Counts(_Report):
    tp: int = 0
    fp: int = 0
    fn: int = 0
    duplicates: int = 0

    @computed_field
    @property
    def precision(self) -> float | None:
        return _ratio(self.tp, self.tp + self.fp)

    @computed_field
    @property
    def recall(self) -> float | None:
        return _ratio(self.tp, self.tp + self.fn)

    @computed_field
    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None:
            return None
        return 0.0 if p + r == 0 else 2 * p * r / (p + r)


class ProblemTypeScore(Counts):
    problem_type: ProblemType


class CategoryScore(Counts):
    category: Category


class FindingRef(_Report):
    rule_id: str
    problem_type: ProblemType | None
    file: str
    line: int
    fingerprint: str


class Match(_Report):
    entry_id: str
    rule_id: str
    file: str
    line: int
    fingerprint: str


class ScoreReport(_Report):
    app: str
    per_problem_type: list[ProblemTypeScore]
    per_category: list[CategoryScore]
    aggregate: Counts
    matches: list[Match]
    missed: list[str]
    false_positives: list[FindingRef]
    duplicates: list[FindingRef]


# ---------------------------------------------------------------------------
# Location matching
# ---------------------------------------------------------------------------


def _normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _normalize_identifier(name: str) -> str:
    name = name.strip().strip('"').casefold()
    return name.removeprefix("public.").strip('"')


def _data_locations(finding: Finding) -> list[tuple[str, frozenset[str]]]:
    locations: list[tuple[str, frozenset[str]]] = []
    for evidence in finding.evidence:
        data: dict[str, Any] = evidence.data or {}
        table = data.get("table")
        if not isinstance(table, str):
            continue
        columns: set[str] = set()
        if isinstance(data.get("column"), str):
            columns.add(_normalize_identifier(data["column"]))
        if isinstance(data.get("columns"), list):
            columns.update(_normalize_identifier(c) for c in data["columns"] if isinstance(c, str))
        locations.append((_normalize_identifier(table), frozenset(columns)))
    return locations


def _code_matches(entry: ManifestEntry, finding: Finding) -> bool:
    if entry.file is None or entry.line is None:
        return False
    if _normalize_path(entry.file) != _normalize_path(finding.file):
        return False
    entry_end = entry.end_line or entry.line
    finding_end = finding.end_line or finding.line
    return finding.line <= entry_end and entry.line <= finding_end


def _data_matches(entry: ManifestEntry, finding: Finding) -> bool:
    if entry.table is None:
        return False
    table = _normalize_identifier(entry.table)
    column = _normalize_identifier(entry.column) if entry.column else None
    return any(
        found_table == table and (column is None or column in found_columns)
        for found_table, found_columns in _data_locations(finding)
    )


def _route_pattern(route: str) -> str:
    """'GET /api/orders/:id?x=1' or '/api/orders/[id]' -> '/api/orders/:'."""
    path = route.split(" ", 1)[-1].split("?", 1)[0].rstrip("/") or "/"
    segments = [
        ":" if s.startswith(":") or (s.startswith("[") and s.endswith("]")) else s
        for s in path.split("/")
    ]
    return "/".join(segments)


def _endpoint_matches(entry: ManifestEntry, finding: Finding) -> bool:
    if entry.endpoint is None:
        return False
    expected = _route_pattern(entry.endpoint)
    return any(
        isinstance((evidence.data or {}).get("route"), str)
        and _route_pattern(evidence.data["route"]) == expected
        for evidence in finding.evidence
    )


def _matches(entry: ManifestEntry, finding: Finding) -> bool:
    if RULE_PROBLEM_TYPES.get(finding.rule_id) is not entry.problem_type:
        return False
    return (
        _code_matches(entry, finding)
        or _data_matches(entry, finding)
        or _endpoint_matches(entry, finding)
    )


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------


def _maximum_matching(candidates: Sequence[Sequence[int]], finding_count: int) -> list[int | None]:
    """Kuhn's augmenting-path algorithm. Returns, per finding, the matched entry index."""
    owner: list[int | None] = [None] * finding_count  # finding -> entry

    def augment(entry: int, visited: set[int]) -> bool:
        for finding in candidates[entry]:
            if finding in visited:
                continue
            visited.add(finding)
            current = owner[finding]
            if current is None or augment(current, visited):
                owner[finding] = entry
                return True
        return False

    for entry in range(len(candidates)):
        augment(entry, set())
    return owner


def _finding_order(finding: Finding) -> tuple[str, int, str, str]:
    return (_normalize_path(finding.file), finding.line, finding.rule_id, finding.fingerprint)


def _ref(finding: Finding) -> FindingRef:
    return FindingRef(
        rule_id=finding.rule_id,
        problem_type=RULE_PROBLEM_TYPES.get(finding.rule_id),
        file=finding.file,
        line=finding.line,
        fingerprint=finding.fingerprint,
    )


def _ordered(items: Iterable[ProblemType]) -> list[ProblemType]:
    present = set(items)
    return [problem_type for problem_type in ProblemType if problem_type in present]


def score(findings: Sequence[Finding], manifest: Manifest) -> ScoreReport:
    entries = sorted(manifest.entries, key=lambda entry: entry.id)
    ordered = sorted(findings, key=_finding_order)

    candidates = [
        [i for i, finding in enumerate(ordered) if _matches(entry, finding)] for entry in entries
    ]
    owner = _maximum_matching(candidates, len(ordered))
    claimable = {finding for entry_candidates in candidates for finding in entry_candidates}

    matched_entries = {entry for entry in owner if entry is not None}
    matches = [
        Match(
            entry_id=entries[entry].id,
            rule_id=finding.rule_id,
            file=finding.file,
            line=finding.line,
            fingerprint=finding.fingerprint,
        )
        for finding, entry in zip(ordered, owner, strict=True)
        if entry is not None
    ]
    missed = [entry.id for i, entry in enumerate(entries) if i not in matched_entries]
    unmatched = [i for i, entry in enumerate(owner) if entry is None]
    false_positives = [_ref(ordered[i]) for i in unmatched if i not in claimable]
    duplicates = [_ref(ordered[i]) for i in unmatched if i in claimable]

    tally: dict[ProblemType, dict[str, int]] = {}

    def bump(problem_type: ProblemType, key: str) -> None:
        tally.setdefault(problem_type, {"tp": 0, "fp": 0, "fn": 0, "duplicates": 0})[key] += 1

    for entry in matched_entries:
        bump(entries[entry].problem_type, "tp")
    for entry_id in missed:
        bump(next(e for e in entries if e.id == entry_id).problem_type, "fn")
    for ref in false_positives:
        if ref.problem_type is not None:
            bump(ref.problem_type, "fp")
    for ref in duplicates:
        if ref.problem_type is not None:
            bump(ref.problem_type, "duplicates")

    per_problem_type = [ProblemTypeScore(problem_type=t, **tally[t]) for t in _ordered(tally)]

    per_category: list[CategoryScore] = []
    for category in Category:
        rows = [s for s in per_problem_type if PROBLEM_CATEGORY[s.problem_type] is category]
        if rows:
            per_category.append(
                CategoryScore(
                    category=category,
                    tp=sum(s.tp for s in rows),
                    fp=sum(s.fp for s in rows),
                    fn=sum(s.fn for s in rows),
                    duplicates=sum(s.duplicates for s in rows),
                )
            )

    aggregate = Counts(
        tp=len(matches),
        fp=len(false_positives),
        fn=len(missed),
        duplicates=len(duplicates),
    )

    return ScoreReport(
        app=manifest.app,
        per_problem_type=per_problem_type,
        per_category=per_category,
        aggregate=aggregate,
        matches=matches,
        missed=missed,
        false_positives=false_positives,
        duplicates=duplicates,
    )
