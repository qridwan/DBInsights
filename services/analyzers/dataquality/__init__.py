"""Data-quality profiling: statistics per table and column, and referential integrity."""

from .integrity import ORPHANED_FOREIGN_KEY, check_integrity, to_findings
from .models import (
    CategoryFrequency,
    ColumnProfile,
    IntegrityCheck,
    ProfileRun,
    TableProfile,
    Window,
)
from .profile import DEFAULT_MAX_CATEGORIES, DataProfile, detect_time_column, profile_database
from .store import ProfileStore

__all__ = [
    "DEFAULT_MAX_CATEGORIES",
    "ORPHANED_FOREIGN_KEY",
    "CategoryFrequency",
    "ColumnProfile",
    "DataProfile",
    "IntegrityCheck",
    "ProfileRun",
    "ProfileStore",
    "TableProfile",
    "Window",
    "check_integrity",
    "detect_time_column",
    "profile_database",
    "to_findings",
]
