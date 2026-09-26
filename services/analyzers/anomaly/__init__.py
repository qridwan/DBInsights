"""Anomaly detection over data-quality profile history, with ranges learned from that history."""

from .detectors import (
    DEFAULT_IQR_MULTIPLIER,
    DEFAULT_MOVING_WINDOW,
    DEFAULT_SIGMAS,
    DETECTOR_NAMES,
    MIN_HISTORY,
    Detection,
    Detector,
    IQRDetector,
    MovingAverageDetector,
    ZScoreDetector,
    default_detectors,
    detectors_by_name,
)
from .pipeline import (
    MetricAnalysis,
    analyze_column,
    backtest,
    detect_anomalies,
    passes_vote,
    to_findings,
)
from .series import ColumnSeries, load_series

__all__ = [
    "DEFAULT_IQR_MULTIPLIER",
    "DEFAULT_MOVING_WINDOW",
    "DEFAULT_SIGMAS",
    "DETECTOR_NAMES",
    "MIN_HISTORY",
    "ColumnSeries",
    "Detection",
    "Detector",
    "IQRDetector",
    "MetricAnalysis",
    "MovingAverageDetector",
    "ZScoreDetector",
    "analyze_column",
    "backtest",
    "default_detectors",
    "detect_anomalies",
    "detectors_by_name",
    "load_series",
    "passes_vote",
    "to_findings",
]
