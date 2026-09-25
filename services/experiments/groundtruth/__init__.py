"""Ground-truth manifests and the scorer: the single source of TP/FP/FN results."""

from .finding import Evidence, Finding, parse_findings
from .manifest import Manifest, ManifestEntry, load_manifest
from .problems import PROBLEM_CATEGORY, RULE_PROBLEM_TYPES, Category, ProblemType
from .scorer import CategoryScore, Counts, ProblemTypeScore, ScoreReport, score

__all__ = [
    "PROBLEM_CATEGORY",
    "RULE_PROBLEM_TYPES",
    "Category",
    "CategoryScore",
    "Counts",
    "Evidence",
    "Finding",
    "Manifest",
    "ManifestEntry",
    "ProblemType",
    "ProblemTypeScore",
    "ScoreReport",
    "load_manifest",
    "parse_findings",
    "score",
]
