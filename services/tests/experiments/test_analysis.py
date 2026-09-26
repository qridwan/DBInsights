import math

import pytest

pytest.importorskip("scipy")

from experiments.analysis.compare import canonical_detection, compare  # noqa: E402
from experiments.analysis.data import Dataset, Outcome, RunRecord  # noqa: E402
from experiments.analysis.stats import (  # noqa: E402
    bootstrap_ci,
    cliffs_delta,
    holm,
    mcnemar_exact,
    mean_ci,
    wilcoxon_paired,
)

# ---- statistics, against values worked out by hand ---------------------------------------------


def test_mean_ci_uses_the_t_distribution():
    ci = mean_ci([1.0, 2.0, 3.0])
    # sd = 1, t(0.975, 2) = 4.3027, half-width = 4.3027 / sqrt(3)
    assert ci.mean == 2.0
    assert ci.low == pytest.approx(2 - 4.3027 / math.sqrt(3), abs=1e-3)
    assert ci.high == pytest.approx(2 + 4.3027 / math.sqrt(3), abs=1e-3)


def test_mean_ci_of_a_constant_is_a_point_and_says_so():
    ci = mean_ci([0.5] * 10)
    assert (ci.mean, ci.low, ci.high, ci.n_distinct) == (0.5, 0.5, 0.5, 1)


def test_mean_ci_of_nothing_is_undefined():
    assert mean_ci([]).mean is None


def test_mcnemar_exact_matches_the_binomial_by_hand():
    first = [False] * 8 + [True, True]
    second = [True] * 8 + [True, True]
    result = mcnemar_exact(first, second)
    assert (result.only_first, result.only_second, result.both) == (0, 8, 2)
    assert result.p_value == pytest.approx(2 * 0.5**8)
    assert result.risk_difference == pytest.approx(0.8)
    assert result.discordant_odds_ratio == math.inf


def test_mcnemar_with_no_disagreement_finds_nothing():
    result = mcnemar_exact([True, False, True], [True, False, True])
    assert result.p_value == 1.0 and result.risk_difference == 0


def test_mcnemar_is_symmetric_in_its_p_value():
    a = [True] * 6 + [False] * 2
    b = [False] * 6 + [True] * 2
    assert mcnemar_exact(a, b).p_value == pytest.approx(mcnemar_exact(b, a).p_value)


def test_mcnemar_rejects_unpaired_input():
    with pytest.raises(ValueError):
        mcnemar_exact([True], [True, False])


def test_cliffs_delta_extremes():
    assert cliffs_delta([1, 2, 3], [4, 5, 6]) == 1.0
    assert cliffs_delta([4, 5, 6], [1, 2, 3]) == -1.0
    assert cliffs_delta([1, 2, 3], [1, 2, 3]) == 0.0


def test_wilcoxon_exact_p_for_a_uniform_shift():
    first = [float(i) for i in range(1, 9)]
    second = [v + 10.5 + i * 0.01 for i, v in enumerate(first)]
    result = wilcoxon_paired(first, second)
    assert result.n_nonzero == 8
    assert result.p_value == pytest.approx(2 / 2**8)
    assert result.cliffs_delta == 1.0 or result.cliffs_delta > 0.9


def test_wilcoxon_with_identical_samples_is_not_significant():
    result = wilcoxon_paired([1.0, 2.0], [1.0, 2.0])
    assert result.p_value == 1.0 and result.n_nonzero == 0


def test_holm_adjustment():
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_holm_never_exceeds_one_and_keeps_order():
    adjusted = holm([0.5, 0.9])
    assert adjusted == pytest.approx([1.0, 1.0])


def test_bootstrap_is_reproducible_and_a_constant_has_no_width():
    def draw(rng):
        return rng.random()

    assert bootstrap_ci(draw, seed=1, resamples=500) == bootstrap_ci(draw, seed=1, resamples=500)
    assert bootstrap_ci(lambda rng: 0.25, seed=1, resamples=200) == (0.25, 0.25)


# ---- the comparisons, on a synthetic experiment -------------------------------------------------


def _dataset(detect: dict[str, int], reps: int = 3, problems: int = 10) -> Dataset:
    """`detect[config]` = how many of the `problems` that configuration finds (the first n)."""
    universe = {"n_plus_one": 20}
    dataset = Dataset(
        experiment_id="x",
        provenance={"universe": {"app": universe}},
    )
    dataset.entries["app"] = [f"p{i}" for i in range(problems)]
    dataset.problem_types = {f"p{i}": "n_plus_one" for i in range(problems)}
    for config, found in detect.items():
        for rep in range(1, reps + 1):
            dataset.runs.append(
                RunRecord(
                    config,
                    "app",
                    rep,
                    False,
                    1.0 + rep * 0.01 * (len(config)),
                    0.5,
                    found,
                    0,
                    problems - found,
                    10,
                    (True,) * found,
                )
            )
            for i in range(problems):
                hit = i < found
                dataset.outcomes.append(
                    Outcome(
                        config,
                        "app",
                        rep,
                        f"p{i}",
                        "n_plus_one",
                        hit,
                        3 if hit else None,
                        1.0 if hit else None,
                    )
                )
    return dataset


def test_a_configuration_that_finds_everything_beats_one_that_finds_nothing():
    dataset = _dataset({"A": 0, "B1": 0, "B2": 0, "C1": 0, "C2": 0, "C3": 10})
    by_id = {c["id"]: c for c in compare(dataset)}
    h1 = by_id["H1_A_vs_C3"]
    assert h1["detection_mcnemar_exact"]["only_second"] == 10
    assert h1["detection_mcnemar_exact"]["p_value"] == pytest.approx(2 * 0.5**10)
    assert h1["verdict"].startswith("supported")


def test_a_result_against_the_hypothesis_is_reported_as_contradicting_it():
    dataset = _dataset({"A": 10, "B1": 10, "B2": 10, "C1": 10, "C2": 10, "C3": 0})
    h1 = {c["id"]: c for c in compare(dataset)}["H1_A_vs_C3"]
    assert h1["verdict"].startswith("CONTRADICTED")


def test_no_difference_is_not_support():
    dataset = _dataset({c: 5 for c in ("A", "B1", "B2", "C1", "C2", "C3")})
    for result in compare(dataset):
        if result["primary"]:
            assert result["verdict"].startswith("not supported")
            assert result["detection_p_holm"] == 1.0


def test_only_the_four_named_tests_are_in_the_holm_family():
    dataset = _dataset({c: 5 for c in ("A", "B1", "B2", "C1", "C2", "C3", "A-log")})
    results = compare(dataset)
    assert [r["id"] for r in results if r["primary"]] == [
        "H5_B1_vs_B2",
        "RQ6_B2_vs_C1",
        "H3_C1_vs_C2",
        "H1_A_vs_C3",
    ]
    assert next(r for r in results if r["id"] == "S_Alog_vs_C3")["detection_p_holm"] is None


def test_canonical_detection_is_the_majority_over_repetitions():
    dataset = _dataset({"A": 10})
    dataset.outcomes = [
        Outcome("A", "app", rep, "p0", "n_plus_one", rep != 3, 3, 1.0) for rep in (1, 2, 3)
    ]
    assert canonical_detection(dataset, "A") == {("app", "p0"): True}
