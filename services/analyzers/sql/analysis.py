"""Static analysis of SQL text: what can be judged from a statement alone.

This is the SQL-only layer of the ablation. It sees statement text and nothing else: no
ORM source, no schema, no timings, no counts, no request context. Two rules fit that:

- SQL_UNBOUNDED_SELECT: a SELECT with no LIMIT/FETCH that returns rows (not a lone aggregate).
  Whether it is a problem depends on the table size and on what bounds it upstream, neither of
  which the text reveals, so it is only ever a suspicion: MEDIUM when the statement has no WHERE
  at all (it reads the whole table), LOW when a filter narrows it.
- SQL_UNBOUNDED_MUTATION: an UPDATE or DELETE with no WHERE.

Where the text comes from is the important choice, and it decides what this layer can see:

- `repository`: SQL files in the source tree (migrations, hand-written queries). In an ORM
  application nearly all queries are generated at run time and do not appear here at all.
- `captured`: statements an application actually issued, as a query log would supply them,
  reduced to their text. No counts, no timings, no request grouping beyond the route.

Findings from captured SQL name the route they were issued on (`file = "route:<pattern>"`) and carry
it in their evidence, like runtime findings do.
"""

import hashlib
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from sqlglot import exp
from sqlglot.errors import SqlglotError

from ..finding import Evidence, Finding
from .fingerprint import parse

# SQLGlot warns about every DDL statement it parses only as a generic command (CREATE EXTENSION).
logging.getLogger("sqlglot").setLevel(logging.ERROR)

SQL_UNBOUNDED_SELECT = "SQL_UNBOUNDED_SELECT"
SQL_UNBOUNDED_MUTATION = "SQL_UNBOUNDED_MUTATION"

_SKIPPED_DIRECTORIES = {"node_modules", ".git", "dist", "build", ".next", "generated"}


@dataclass(frozen=True)
class SqlStatement:
    sql: str
    #: Set for statements found in a repository.
    file: str | None = None
    line: int = 0
    #: Set for captured statements: the route pattern they were issued on.
    route: str | None = None


# ---- getting statements -------------------------------------------------------------------------


def split_statements(text: str) -> list[tuple[int, str]]:
    """Splits SQL text on top-level semicolons, returning (starting line, statement).

    Understands `--` and `/* */` comments and single-quoted strings, so a semicolon inside one
    does not end a statement.
    """
    statements: list[tuple[int, str]] = []
    buffer: list[str] = []
    start_line = 0
    line, i, n = 1, 0, len(text)

    def flush() -> None:
        nonlocal buffer, start_line
        statement = "".join(buffer).strip()
        if statement:
            statements.append((start_line, statement))
        buffer, start_line = [], 0

    while i < n:
        ch = text[i]
        if text.startswith("--", i):
            end = text.find("\n", i)
            i = n if end == -1 else end  # the newline itself is handled below
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end == -1 else end + 2
            line += text.count("\n", i, end)
            i = end
            continue
        if ch == "'":
            j = i + 1
            while j < n:
                if text[j] == "'" and text[j + 1 : j + 2] == "'":
                    j += 2
                elif text[j] == "'":
                    break
                else:
                    j += 1
            chunk = text[i : j + 1]
            if not start_line:
                start_line = line
            buffer.append(chunk)
            line += chunk.count("\n")
            i = j + 1
            continue
        if ch == ";":
            flush()
        else:
            if not ch.isspace() and not start_line:
                start_line = line
            if start_line:
                buffer.append(ch)
        if ch == "\n":
            line += 1
        i += 1
    flush()
    return statements


def statements_from_repository(root: str | Path) -> list[SqlStatement]:
    """Every statement in the `.sql` files under `root`, in path and line order."""
    base = Path(root)
    found: list[SqlStatement] = []
    for path in sorted(base.rglob("*.sql")):
        relative = path.relative_to(base)
        if any(part in _SKIPPED_DIRECTORIES for part in relative.parts):
            continue
        for line, sql in split_statements(path.read_text(encoding="utf-8")):
            found.append(SqlStatement(sql=sql, file=relative.as_posix(), line=line))
    return found


# ---- rules --------------------------------------------------------------------------------------


def _is_lone_aggregate(select: exp.Select) -> bool:
    """`SELECT COUNT(*) ...` without GROUP BY returns one row whatever the table's size."""
    if select.args.get("group"):
        return False
    projections = select.expressions
    return bool(projections) and all(isinstance(p.unalias(), exp.AggFunc) for p in projections)


def _classify(statement: SqlStatement) -> tuple[str, str] | None:
    """(rule id, confidence) if the statement trips a rule."""
    try:
        tree = parse(statement.sql)
    except SqlglotError:
        return None
    if isinstance(tree, exp.Update | exp.Delete):
        return (SQL_UNBOUNDED_MUTATION, "HIGH") if tree.args.get("where") is None else None
    # SQLGlot spells the FROM argument `from_` in recent versions and `from` in older ones.
    source = tree.args.get("from_") or tree.args.get("from") if tree else None
    if not isinstance(tree, exp.Select) or source is None:
        return None
    if tree.args.get("limit") or tree.args.get("fetch") or _is_lone_aggregate(tree):
        return None
    return SQL_UNBOUNDED_SELECT, ("LOW" if tree.args.get("where") else "MEDIUM")


_TITLES = {
    SQL_UNBOUNDED_SELECT: "SELECT without LIMIT returns every matching row",
    SQL_UNBOUNDED_MUTATION: "UPDATE/DELETE without WHERE affects every row",
}
_BODIES = {
    SQL_UNBOUNDED_SELECT: (
        "The statement has no LIMIT or FETCH, so the rows it returns grow with the table. "
        "From the SQL text alone it is not possible to tell whether something upstream bounds it."
    ),
    SQL_UNBOUNDED_MUTATION: (
        "The statement has no WHERE clause, so it changes or removes every row."
    ),
}
_FIXES = {
    SQL_UNBOUNDED_SELECT: (
        "```sql\n-- Bound the result:\nSELECT ... FROM ... ORDER BY ... LIMIT 100;\n```"
    ),
    SQL_UNBOUNDED_MUTATION: "```sql\n-- State which rows:\nDELETE FROM ... WHERE ...;\n```",
}


def _finding(rule_id: str, confidence: str, statement: SqlStatement) -> Finding:
    if statement.route is not None:
        file, line = f"route:{statement.route}", 0
        data = {"route": statement.route, "normalizedSql": statement.sql}
        where = statement.route
    else:
        file, line = statement.file or "", statement.line
        data = {"normalizedSql": statement.sql}
        where = f"{file}:{line}"
    return Finding(
        schema_version=1,
        rule_id=rule_id,
        severity="MEDIUM",
        confidence=confidence,  # type: ignore[arg-type]
        file=file,
        line=line,
        title=_TITLES[rule_id],
        body=f"{_BODIES[rule_id]} ({where})",
        evidence=[
            Evidence(
                source="SQL",
                description=" ".join(statement.sql.split())[:200],
                file=statement.file,
                line=statement.line or None,
                data=data,
            )
        ],
        suggested_fix=_FIXES[rule_id],
        fingerprint=hashlib.sha256(
            "\x00".join([rule_id, file, re.sub(r"\s+", " ", statement.sql)]).encode()
        ).hexdigest()[:32],
    )


def analyze_statements(statements: Iterable[SqlStatement]) -> list[Finding]:
    """Findings for every statement that trips a rule; a repeat on one route counts once."""
    seen: set[str] = set()
    findings: list[Finding] = []
    for statement in statements:
        verdict = _classify(statement)
        if verdict is None:
            continue
        finding = _finding(verdict[0], verdict[1], statement)
        if finding.fingerprint not in seen:
            seen.add(finding.fingerprint)
            findings.append(finding)
    return sorted(findings, key=lambda f: (f.file, f.line, f.rule_id, f.fingerprint))
