import ast
import math
from pathlib import Path

import pytest

from analyzers.anomaly import (
    DEFAULT_SIGMAS,
    MIN_HISTORY,
    IQRDetector,
    MovingAverageDetector,
    ZScoreDetector,
    default_detectors,
    detectors_by_name,
)

HISTORY = [10, 12, 11, 13, 9]  # mean 11, sample std sqrt(2.5), quartiles 10 / 11 / 12


# ---- the learned ranges, computed by hand ------------------------------------------------------


def test_zscore_range_is_mean_plus_minus_k_sample_standard_deviations():
    d = ZScoreDetector().detect(HISTORY, 15)
    std = math.sqrt(2.5)
    assert (d.center, d.spread) == (11, pytest.approx(std))
    assert d.lower == pytest.approx(11 - 3 * std) and d.upper == pytest.approx(11 + 3 * std)
    assert d.parameters == {"sigmas": 3.0}
    assert (d.evaluated, d.anomalous, d.direction, d.history_size) == (True, False, None, 5)


@pytest.mark.parametrize(
    ("observation", "anomalous", "direction"),
    [(20, True, "above"), (15.7, False, None), (6.3, False, None), (6.2, True, "below")],
)
def test_zscore_verdicts_at_the_edges_of_the_range(observation, anomalous, direction):
    d = ZScoreDetector().detect(HISTORY, observation)
    assert (d.anomalous, d.direction) == (anomalous, direction)


def test_zscore_deviation_is_the_standardised_distance():
    d = ZScoreDetector().detect(HISTORY, 20)
    assert d.deviation == pytest.approx((20 - 11) / math.sqrt(2.5))


def test_iqr_range_is_tukeys_fences():
    d = IQRDetector().detect(HISTORY, 15)
    assert (d.center, d.spread, d.lower, d.upper) == (11, 2, 7, 15)
    assert d.anomalous is False, "the fence itself is still inside"
    assert IQRDetector().detect(HISTORY, 15.5).direction == "above"
    assert IQRDetector().detect(HISTORY, 6.9).direction == "below"


def test_moving_average_uses_only_the_most_recent_window():
    d = MovingAverageDetector(window=3).detect(HISTORY, 17)
    # last three points 11, 13, 9: mean 11, sample std 2, range 11 +/- 6.
    assert (d.center, d.spread, d.lower, d.upper) == (11, 2, 5, 17)
    assert d.anomalous is False
    assert MovingAverageDetector(window=3).detect(HISTORY, 17.5).direction == "above"


def test_moving_average_follows_a_drifting_level_where_the_global_range_does_not():
    drifting = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    latest_level = 10.5
    assert MovingAverageDetector(window=3).detect(drifting, latest_level).anomalous is False
    assert ZScoreDetector().detect(drifting, latest_level).anomalous is False  # wide global spread
    assert MovingAverageDetector(window=3).detect(drifting, 14).anomalous is True


def test_a_short_moving_window_and_the_default_agree_when_history_is_shorter_than_the_window():
    assert MovingAverageDetector().detect(HISTORY, 15).lower == pytest.approx(
        ZScoreDetector().detect(HISTORY, 15).lower
    )


# ---- history too short, or without spread -------------------------------------------------------


@pytest.mark.parametrize("detector", default_detectors(), ids=lambda d: d.name)
def test_detectors_decline_to_judge_on_too_little_history(detector):
    d = detector.detect(HISTORY[: MIN_HISTORY - 1], 1000)
    assert (d.evaluated, d.anomalous, d.lower, d.upper) == (False, False, None, None)
    assert d.history_size == MIN_HISTORY - 1


@pytest.mark.parametrize("detector", default_detectors(), ids=lambda d: d.name)
def test_constant_history_collapses_the_range_to_that_value(detector):
    same = detector.detect([0.0] * 6, 0.0)
    assert (same.anomalous, same.degenerate, same.lower, same.upper) == (False, True, 0.0, 0.0)
    different = detector.detect([0.0] * 6, 0.01)
    assert (
        different.anomalous,
        different.degenerate,
        different.direction,
        different.deviation,
    ) == (True, True, "above", None)


def test_identical_floats_are_exactly_constant():
    # Repeating 0.1 accumulates rounding error in a naive mean/std; the range must still collapse.
    d = ZScoreDetector().detect([0.1] * 7, 0.1)
    assert (d.spread, d.anomalous, d.degenerate) == (0.0, False, True)


@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_non_finite_numbers_are_rejected(bad):
    with pytest.raises(ValueError):
        ZScoreDetector().detect(HISTORY, bad)
    with pytest.raises(ValueError):
        ZScoreDetector().detect([*HISTORY, bad], 1.0)


# ---- there are no fixed thresholds ---------------------------------------------------------------


@pytest.mark.parametrize("detector", default_detectors(), ids=lambda d: d.name)
def test_the_same_observation_is_normal_or_anomalous_depending_only_on_history(detector):
    """0.15 is unremarkable for a column that hovers around it, a spike for one that never does."""
    hovering = [0.13, 0.17, 0.15, 0.14, 0.16, 0.15, 0.16, 0.14]
    quiet = [0.01, 0.03, 0.02, 0.02, 0.01, 0.03, 0.02, 0.02]
    assert detector.detect(hovering, 0.15).anomalous is False
    assert detector.detect(quiet, 0.15).anomalous is True


OBSERVATIONS = [4, 8, 9.5, 11, 12.5, 14, 16, 20]
LONG_HISTORY = [10, 12, 11, 13, 9, 10.5, 11.5, 12.5, 9.5, 11]


@pytest.mark.parametrize("detector", default_detectors(), ids=lambda d: d.name)
@pytest.mark.parametrize("scale", [0.001, 2.5, 1000])
@pytest.mark.parametrize("shift", [-7.0, 0.0, 123.4, 1e6])
def test_verdicts_are_invariant_under_affine_transforms(detector, scale, shift):
    """x -> scale*x + shift on history and observation together changes no verdict. A limit on
    the metric's value (e.g. 'above 0.1') cannot have this property."""
    for observation in OBSERVATIONS:
        original = detector.detect(LONG_HISTORY, observation)
        margin = min(abs(observation - original.lower), abs(observation - original.upper))
        assert margin > 1e-3, "test data must not sit on a range boundary"
        transformed = detector.detect(
            [scale * v + shift for v in LONG_HISTORY], scale * observation + shift
        )
        assert (transformed.anomalous, transformed.direction) == (
            original.anomalous,
            original.direction,
        )


def test_sensitivity_parameters_change_the_range_and_are_reported():
    strict = ZScoreDetector(sigmas=1.0).detect(HISTORY, 13)
    lenient = ZScoreDetector(sigmas=4.0).detect(HISTORY, 13)
    assert (strict.anomalous, lenient.anomalous) == (True, False)
    assert strict.as_evidence()["parameters"] == {"sigmas": 1.0}
    assert IQRDetector(multiplier=0.0).detect(HISTORY, 12.5).anomalous is True
    assert MovingAverageDetector(window=3, sigmas=2.0).detect(HISTORY, 0).parameters == {
        "window": 3.0,
        "sigmas": 2.0,
    }


def test_evidence_reports_the_learned_range():
    evidence = ZScoreDetector().detect(HISTORY, 20).as_evidence()
    assert evidence["anomalous"] is True and evidence["direction"] == "above"
    assert evidence["expectedLower"] < 11 < evidence["expectedUpper"] < 20
    assert evidence["historySize"] == 5 and evidence["degenerate"] is False


def test_detectors_are_selected_by_name():
    assert [d.name for d in detectors_by_name(["iqr", "zscore"])] == ["iqr", "zscore"]
    with pytest.raises(ValueError, match="unknown"):
        detectors_by_name(["isolation_forest"])


# ---- no hardcoded numeric limits anywhere in the anomaly code ------------------------------------

ANOMALY_DIR = Path(__file__).parents[2] / "analyzers" / "anomaly"
#: Structural numbers only: indexes, pairs, quartile count, half an L1 distance, digest length.
STRUCTURAL = {0, 1, 2, 4, 32, 0.5}


def numeric_literals_outside_named_constants(path: Path) -> list[tuple[int, object]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    named: set[int] = set()
    for (
        node
    ) in tree.body:  # module-level NAME = <literal> definitions are the documented parameters
        if isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if all(isinstance(t, ast.Name) and t.id.isupper() for t in targets):
                named.update(id(n) for n in ast.walk(node))
    return [
        (n.lineno, n.value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, int | float)
        and not isinstance(n.value, bool)
        and id(n) not in named
        and n.value not in STRUCTURAL
    ]


@pytest.mark.parametrize("module", ["detectors.py", "series.py", "pipeline.py"])
def test_numeric_literals_are_only_named_method_parameters_or_structural(module):
    assert numeric_literals_outside_named_constants(ANOMALY_DIR / module) == []


def test_the_default_sensitivity_parameters_are_the_documented_named_ones():
    assert ZScoreDetector().sigmas == DEFAULT_SIGMAS == MovingAverageDetector().sigmas
