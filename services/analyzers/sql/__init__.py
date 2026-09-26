"""SQL analysis (SQLGlot): query fingerprinting and static analysis of SQL text."""

from .analysis import (
    SQL_UNBOUNDED_MUTATION,
    SQL_UNBOUNDED_SELECT,
    SqlStatement,
    analyze_statements,
    split_statements,
    statements_from_repository,
)
from .fingerprint import Fingerprint, fingerprint, naive_normalize, normalize, parse

__all__ = [
    "SQL_UNBOUNDED_MUTATION",
    "SQL_UNBOUNDED_SELECT",
    "Fingerprint",
    "SqlStatement",
    "analyze_statements",
    "fingerprint",
    "naive_normalize",
    "normalize",
    "parse",
    "split_statements",
    "statements_from_repository",
]
