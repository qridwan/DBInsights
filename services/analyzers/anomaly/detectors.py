"""Interpretable anomaly detectors: is an observation outside the range its own history predicts?

Each detector takes a metric history (a list of past values of one metric for one
column) and a current observation. It learns an expected range from the history
alone and reports whether the observation falls outside it, together with the range
as evidence. There are three:

- `ZScoreDetector`: range = mean +/- k standard deviations of the whole history.
- `IQRDetector`: Tukey's fences, [Q1 - m*IQR, Q3 + m*IQR]; robust to outliers in the history.
- `MovingAverageDetector`: range = moving average +/- k moving standard deviations over the
  most recent points, so it follows a drifting level.

No fixed thresholds
-------------------
Nothing here contains a limit on the metric itself. There is no "NULL rate > 10%":
the bounds are always computed from the history, so the same observation can be normal
for one column and anomalous for another. A consequence, tested directly: every verdict
is invariant under an affine transform of history and observation together
(x -> a*x + b, a > 0). A limit on the metric's value could not have that property.

Parameters that are not thresholds
----------------------------------
The named constants below are *method parameters*: how many standard deviations count as
"outside" (3, the control-chart convention), Tukey's fence multiplier (1.5), how far back
the moving statistics look, and the minimum history needed before a learned range is
credible. They set the sensitivity of a method, not a judgement about any metric's value.
They are constructor arguments, and every detection reports the ones it used.

Degenerate history
------------------
If the history has no spread (a column that has always been exactly 0), the learned range
collapses to that one value and any different observation is outside it. This is reported
(`degenerate=True`) so consumers can weigh it: the range says "never seen anything else",
not "anything else is far".
"""

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import ClassVar, Literal, Protocol

#: Standard deviations either side of the centre that still count as expected (3-sigma rule).
DEFAULT_SIGMAS = 3.0
#: Tukey's multiplier for the inner fences.
DEFAULT_IQR_MULTIPLIER = 1.5
#: How many of the most recent points the moving average and deviation look back over.
DEFAULT_MOVING_WINDOW = 6
#: With less history than this a learned range is not credible; detectors decline to judge.
MIN_HISTORY = 5

Direction = Literal["above", "below"]


@dataclass(frozen=True)
class Detection:
    """One detector's verdict on one observation, with the learned range as evidence."""

    detector: str
    #: False when the history was too short to learn a range; `anomalous` is then False.
    evaluated: bool
    anomalous: bool
    observation: float
    #: The learned expected range (inclusive). None when not evaluated.
    lower: float | None
    upper: float | None
    #: Mean / median / moving average, and the spread used to build the range.
    center: float | None
    spread: float | None
    #: (observation - center) / spread; None when the spread is zero.
    deviation: float | None
    direction: Direction | None
    history_size: int
    #: The sensitivity parameters used.
    parameters: Mapping[str, float] = field(default_factory=dict)
    #: True when the history had no spread, so the range is a single value.
    degenerate: bool = False

    def as_evidence(self) -> dict[str, object]:
        return {
            "detector": self.detector,
            "anomalous": self.anomalous,
            "observation": self.observation,
            "expectedLower": self.lower,
            "expectedUpper": self.upper,
            "center": self.center,
            "spread": self.spread,
            "deviation": self.deviation,
            "direction": self.direction,
            "historySize": self.history_size,
            "parameters": dict(self.parameters),
            "degenerate": self.degenerate,
        }


class Detector(Protocol):
    name: str

    def detect(self, history: Sequence[float], observation: float) -> Detection: ...


def _checked(history: Sequence[float], observation: float) -> None:
    if not math.isfinite(observation) or not all(math.isfinite(v) for v in history):
        raise ValueError("history and observation must be finite numbers")


def _not_evaluated(
    name: str, history: Sequence[float], observation: float, parameters: dict
) -> Detection:
    return Detection(
        detector=name,
        evaluated=False,
        anomalous=False,
        observation=observation,
        lower=None,
        upper=None,
        center=None,
        spread=None,
        deviation=None,
        direction=None,
        history_size=len(history),
        parameters=parameters,
    )


def _verdict(
    name: str,
    observation: float,
    center: float,
    spread: float,
    lower: float,
    upper: float,
    history_size: int,
    parameters: dict,
) -> Detection:
    direction: Direction | None = (
        "below" if observation < lower else "above" if observation > upper else None
    )
    return Detection(
        detector=name,
        evaluated=True,
        anomalous=direction is not None,
        observation=observation,
        lower=lower,
        upper=upper,
        center=center,
        spread=spread,
        deviation=(observation - center) / spread if spread else None,
        direction=direction,
        history_size=history_size,
        parameters=parameters,
        degenerate=spread == 0,
    )


@dataclass(frozen=True)
class ZScoreDetector:
    """Outside mean +/- `sigmas` sample standard deviations of the whole history."""

    name: ClassVar[str] = "zscore"
    sigmas: float = DEFAULT_SIGMAS
    min_history: int = MIN_HISTORY

    def detect(self, history: Sequence[float], observation: float) -> Detection:
        _checked(history, observation)
        parameters = {"sigmas": self.sigmas}
        if len(history) < max(self.min_history, 2):
            return _not_evaluated(self.name, history, observation, parameters)
        center, spread = statistics.mean(history), statistics.stdev(history)
        return _verdict(
            self.name,
            observation,
            center,
            spread,
            center - self.sigmas * spread,
            center + self.sigmas * spread,
            len(history),
            parameters,
        )


@dataclass(frozen=True)
class IQRDetector:
    """Outside Tukey's fences: [Q1 - multiplier*IQR, Q3 + multiplier*IQR]."""

    name: ClassVar[str] = "iqr"
    multiplier: float = DEFAULT_IQR_MULTIPLIER
    min_history: int = MIN_HISTORY

    def detect(self, history: Sequence[float], observation: float) -> Detection:
        _checked(history, observation)
        parameters = {"multiplier": self.multiplier}
        if len(history) < max(self.min_history, 2):
            return _not_evaluated(self.name, history, observation, parameters)
        q1, median, q3 = statistics.quantiles(history, n=4, method="inclusive")
        spread = q3 - q1
        return _verdict(
            self.name,
            observation,
            median,
            spread,
            q1 - self.multiplier * spread,
            q3 + self.multiplier * spread,
            len(history),
            parameters,
        )


@dataclass(frozen=True)
class MovingAverageDetector:
    """Outside the moving average +/- `sigmas` moving standard deviations (last `window` points)."""

    name: ClassVar[str] = "moving_average"
    window: int = DEFAULT_MOVING_WINDOW
    sigmas: float = DEFAULT_SIGMAS
    min_history: int = MIN_HISTORY

    def detect(self, history: Sequence[float], observation: float) -> Detection:
        _checked(history, observation)
        parameters = {"window": float(self.window), "sigmas": self.sigmas}
        if len(history) < max(self.min_history, 2):
            return _not_evaluated(self.name, history, observation, parameters)
        recent = list(history)[-self.window :]
        if len(recent) < 2:
            return _not_evaluated(self.name, history, observation, parameters)
        center, spread = statistics.mean(recent), statistics.stdev(recent)
        return _verdict(
            self.name,
            observation,
            center,
            spread,
            center - self.sigmas * spread,
            center + self.sigmas * spread,
            len(history),
            parameters,
        )


def default_detectors() -> list[Detector]:
    return [ZScoreDetector(), IQRDetector(), MovingAverageDetector()]


DETECTOR_NAMES = (ZScoreDetector.name, IQRDetector.name, MovingAverageDetector.name)


def detectors_by_name(names: Sequence[str]) -> list[Detector]:
    available: dict[str, Detector] = {d.name: d for d in default_detectors()}
    unknown = [n for n in names if n not in available]
    if unknown:
        raise ValueError(f"unknown detector(s) {unknown}; choose from {sorted(available)}")
    return [available[n] for n in names]
