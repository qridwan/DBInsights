"""Query fingerprinting: one id per logical query shape.

Why not literal substitution
----------------------------
pg_stat_statements-style normalization replaces each constant with a
placeholder but keeps everything else, including the *number* of items in an
IN list. ORM-generated SQL varies exactly there: Prisma sends
`WHERE id IN ($1)`, `IN ($1,...,$5)` and `IN ($1,...,$50)` for one logical
query with 1, 5 and 50 ids. Literal substitution gives three fingerprints, so
per-request repetition is under-counted and runtime N+1 detection produces
false negatives. `naive_normalize` implements that approach so the failure
can be demonstrated in tests.

What this module does
---------------------
It parses the statement with SQLGlot and normalizes the syntax tree:
- every literal and bind parameter becomes one placeholder;
- IN lists, ARRAY[...] constructors and multi-row VALUES collapse to a single
  element, so arity no longer matters;
- the SQL is regenerated from the tree, which removes comments and
  whitespace differences.
Identifiers, operators, joins, predicates, ordering and LIMIT/OFFSET presence
all stay part of the shape: queries that differ in any of them keep distinct
fingerprints.

If SQLGlot cannot parse a statement, a lexical fallback (which still
collapses IN lists) is used and `Fingerprint.parsed` is False.
"""

import hashlib
import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

_DIALECT = "postgres"

# SQLGlot's tokenizer reads "$1,$" in "IN ($1,$2)" as the start of a
# dollar-quoted string. Separating the comma fixes it without touching the query.
_ADJACENT_PARAMETER = re.compile(r",(?=\$\d)")


@dataclass(frozen=True)
class Fingerprint:
    #: Stable 16-hex-character id of the normalized shape.
    id: str
    #: The normalized SQL the id was computed from.
    normalized: str
    #: False when SQLGlot could not parse the statement and the lexical fallback was used.
    parsed: bool


def _placeholder() -> exp.Expression:
    return exp.Placeholder()


def _normalize_node(node: exp.Expression) -> exp.Expression:
    if isinstance(node, exp.Literal | exp.Parameter | exp.Placeholder | exp.Boolean):
        return _placeholder()
    if isinstance(node, exp.In) and node.expressions:
        node.set("expressions", [_placeholder()])
    elif isinstance(node, exp.Array) and node.expressions:
        node.set("expressions", [_placeholder()])
    elif isinstance(node, exp.Values) and len(node.expressions) > 1:
        node.set("expressions", node.expressions[:1])
    return node


def normalize(sql: str) -> tuple[str, bool]:
    """Returns (normalized SQL, parsed-by-SQLGlot)."""
    try:
        tree = sqlglot.parse_one(_ADJACENT_PARAMETER.sub(", ", sql), read=_DIALECT)
    except SqlglotError:
        return _lexical_normalize(sql), False
    normalized = tree.transform(_normalize_node, copy=True)
    return normalized.sql(dialect=_DIALECT, comments=False), True


def fingerprint(sql: str) -> Fingerprint:
    normalized, parsed = normalize(sql)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return Fingerprint(id=digest, normalized=normalized, parsed=parsed)


# ---------------------------------------------------------------------------
# Lexical normalizers
# ---------------------------------------------------------------------------

_STRING = re.compile(r"'(?:[^']|'')*'")
_NUMBER = re.compile(r"(?<![\w$\"])-?\d+(?:\.\d+)?\b")
_PARAMETER = re.compile(r"\$\d+")
_WHITESPACE = re.compile(r"\s+")
_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_PLACEHOLDER_LIST = re.compile(r"\(\s*\?(?:\s*,\s*\?)*\s*\)")


def naive_normalize(sql: str) -> str:
    """pg_stat_statements-style: constants become `?`, list arity is kept.

    Kept only to demonstrate why it is not used: it fragments ORM IN lists.
    """
    text = _COMMENT.sub(" ", sql)
    text = _STRING.sub("?", text)
    text = _PARAMETER.sub("?", text)
    text = _NUMBER.sub("?", text)
    return _WHITESPACE.sub(" ", text).strip()


def _lexical_normalize(sql: str) -> str:
    """Fallback for unparseable SQL: naive normalization plus list collapse."""
    return _PLACEHOLDER_LIST.sub("(?)", naive_normalize(sql))
