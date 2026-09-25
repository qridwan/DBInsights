"""Problem taxonomy and the rule registry that maps detector output onto it."""

from enum import StrEnum


class Category(StrEnum):
    PERFORMANCE = "performance"
    DATA_QUALITY = "data_quality"
    SCHEMA_DIVERGENCE = "schema_divergence"


class ProblemType(StrEnum):
    N_PLUS_ONE = "n_plus_one"
    MISSING_INDEX = "missing_index"
    EXCESSIVE_RELATION_LOADING = "excessive_relation_loading"
    REPEATED_IDENTICAL_QUERY = "repeated_identical_query"
    UNPAGINATED_FIND_MANY = "unpaginated_find_many"
    NULL_SPIKE = "null_spike"
    DUPLICATE_SPIKE = "duplicate_spike"
    DISTRIBUTION_SHIFT = "distribution_shift"
    ORPHANED_FOREIGN_KEY = "orphaned_foreign_key"
    # RQ6 divergence, one type per direction.
    INDEX_NOT_DECLARED = "index_not_declared"  # actual has it, schema.prisma does not
    DECLARED_INDEX_NOT_APPLIED = (
        "declared_index_not_applied"  # schema.prisma has it, actual does not
    )


PROBLEM_CATEGORY: dict[ProblemType, Category] = {
    ProblemType.N_PLUS_ONE: Category.PERFORMANCE,
    ProblemType.MISSING_INDEX: Category.PERFORMANCE,
    ProblemType.EXCESSIVE_RELATION_LOADING: Category.PERFORMANCE,
    ProblemType.REPEATED_IDENTICAL_QUERY: Category.PERFORMANCE,
    ProblemType.UNPAGINATED_FIND_MANY: Category.PERFORMANCE,
    ProblemType.NULL_SPIKE: Category.DATA_QUALITY,
    ProblemType.DUPLICATE_SPIKE: Category.DATA_QUALITY,
    ProblemType.DISTRIBUTION_SHIFT: Category.DATA_QUALITY,
    ProblemType.ORPHANED_FOREIGN_KEY: Category.DATA_QUALITY,
    ProblemType.INDEX_NOT_DECLARED: Category.SCHEMA_DIVERGENCE,
    ProblemType.DECLARED_INDEX_NOT_APPLIED: Category.SCHEMA_DIVERGENCE,
}

# Every rule id that can report a ground-truth problem type. Several rules may
# report the same type (a static rule and its runtime counterpart); findings
# are matched on problem type, so any of them scores. Rules not listed here
# (e.g. UNBOUNDED_MUTATION) have no injected ground truth: their findings are
# scored as unmapped false positives.
#
# Ids marked "planned" belong to later milestones; a rule implemented there
# must use exactly this id or be added here.
RULE_PROBLEM_TYPES: dict[str, ProblemType] = {
    "N_PLUS_ONE_IN_LOOP": ProblemType.N_PLUS_ONE,
    "RUNTIME_N_PLUS_ONE": ProblemType.N_PLUS_ONE,  # planned: M3.3
    "MISSING_INDEX_ON_FILTERED_FIELD": ProblemType.MISSING_INDEX,
    "EXCESSIVE_RELATION_LOADING": ProblemType.EXCESSIVE_RELATION_LOADING,  # planned
    "REPEATED_IDENTICAL_QUERY": ProblemType.REPEATED_IDENTICAL_QUERY,  # planned: M3
    "MISSING_PAGINATION": ProblemType.UNPAGINATED_FIND_MANY,
    "NULL_SPIKE": ProblemType.NULL_SPIKE,  # planned: M4
    "DUPLICATE_SPIKE": ProblemType.DUPLICATE_SPIKE,  # planned: M4
    "DISTRIBUTION_SHIFT": ProblemType.DISTRIBUTION_SHIFT,  # planned: M4
    "ORPHANED_FOREIGN_KEY": ProblemType.ORPHANED_FOREIGN_KEY,  # planned: M4
    "INDEX_NOT_DECLARED": ProblemType.INDEX_NOT_DECLARED,  # planned: M3.1
    "DECLARED_INDEX_NOT_APPLIED": ProblemType.DECLARED_INDEX_NOT_APPLIED,  # planned: M3.1
}
