from datetime import UTC, datetime, timedelta

import pytest

from analyzers.anomaly import (
    ColumnSeries,
    IQRDetector,
    analyze_column,
    backtest,
    default_detectors,
    detect_anomalies,
    load_series,
    passes_vote,
    to_findings,
)
from analyzers.anomaly.series import (
    DISTRIBUTION_SHIFT,
    DUPLICATE_RATE,
    NULL_RATE,
    leave_one_out_distances,
    mean_shares,
    metrics_for,
    shares,
    total_variation,
)
from analyzers.dataquality import Window
from experiments.groundtruth import Manifest, score
from tests.analyzers.test_dataquality_store import make_run, month

START = datetime(2026, 1, 1, tzinfo=UTC)


def windows(n: int) -> tuple[Window, ...]:
    return tuple(
        Window(start=START + timedelta(days=30 * i), end=START + timedelta(days=30 * (i + 1)))
        for i in range(n)
    )


def make_series(null_rates, dup_rates=None, distributions=None, table="Customer", column="phone"):
    n = len(null_rates)
    return ColumnSeries(
        table=table,
        column=column,
        windows=windows(n),
        row_counts=(100,) * n,
        null_rates=tuple(null_rates),
        duplicate_rates=tuple(dup_rates or [0.0] * n),
        distributions=tuple(distributions or [None] * n),
    )


def judge(baseline, current, index=-1, **kw):
    detectors = kw.pop("detectors", default_detectors())
    vote = kw.pop("vote", "majority")
    return analyze_column(baseline, current, index % len(current.windows), detectors, vote)


CALM = [0.04, 0.05, 0.06, 0.04, 0.05, 0.05, 0.06, 0.04, 0.05, 0.05]


# ---- distances -------------------------------------------------------------------------------


def test_total_variation_is_the_share_of_the_distribution_that_moved():
    assert total_variation({"a": 0.5, "b": 0.5}, {"a": 0.5, "b": 0.5}) == 0
    assert total_variation({"a": 1.0}, {"b": 1.0}) == 1
    assert total_variation({"a": 0.5, "b": 0.5}, {"a": 0.9, "b": 0.1}) == pytest.approx(0.4)
    assert total_variation({"a": 0.5, "b": 0.5}, {"a": 0.5, "b": 0.3, "c": 0.2}) == pytest.approx(
        0.2
    )


def test_every_window_weighs_the_same_whatever_its_row_count():
    assert mean_shares([{"a": 1}, {"a": 1000, "b": 1000}]) == {"a": 0.75, "b": 0.25}


def test_leave_one_out_compares_each_window_with_the_mean_of_the_others():
    distances = leave_one_out_distances([{"a": 10}, {"a": 10}, {"b": 10}])
    assert distances == pytest.approx([0.5, 0.5, 1.0])
    assert leave_one_out_distances([{"a": 1}]) == []


def test_identical_distributions_are_exactly_zero_apart_not_a_rounding_error_apart():
    """Float shares of {a:1, b:9} accumulate rounding error: 'identical' windows were 1e-16 apart
    and a collapsed range then flagged the noise. Shares are exact rationals."""
    same = [{"a": 1, "b": 9}] * 10
    assert leave_one_out_distances(same) == [0.0] * 10
    assert total_variation(shares(same[0]), mean_shares(same)) == 0.0


def test_a_constant_distribution_never_alarms_on_itself():
    constant = [{"only": 7}] * 8
    baseline = make_series([0.0] * 8, distributions=constant, table="Post", column="updatedAt")
    current = make_series(
        [0.0] * 9, distributions=[*constant, {"only": 7}], table="Post", column="updatedAt"
    )
    (shift,) = [a for a in judge(baseline, current) if a.metric == DISTRIBUTION_SHIFT]
    assert (shift.observation, shift.anomalous) == (0.0, False)


def test_shares_of_an_empty_distribution_is_empty():
    assert shares({}) == {}


# ---- which metrics apply ---------------------------------------------------------------------


def test_duplicate_rate_is_for_near_unique_columns_and_distribution_for_categorical_ones():
    unique = make_series(CALM)
    categorical = make_series(CALM, distributions=[{"a": 5, "b": 5}] * 10)
    assert metrics_for(unique) == [NULL_RATE, DUPLICATE_RATE]
    assert metrics_for(categorical) == [NULL_RATE, DISTRIBUTION_SHIFT]


# ---- null and duplicate spikes ----------------------------------------------------------------


def test_a_null_spike_is_flagged_by_the_learned_range():
    baseline = make_series(CALM)
    current = make_series([*CALM, 0.63])
    (null,) = [a for a in judge(baseline, current) if a.metric == NULL_RATE]
    assert (null.anomalous, null.direction, null.fired, null.evaluated) == (True, "above", 3, 3)
    assert null.observation == 0.63


def test_the_same_rate_is_not_a_spike_for_a_column_that_normally_has_it():
    baseline = make_series([0.55, 0.60, 0.65, 0.58, 0.62, 0.60, 0.57, 0.63, 0.61, 0.59])
    (null,) = [
        a
        for a in judge(baseline, make_series([*baseline.null_rates, 0.63]))
        if a.metric == NULL_RATE
    ]
    assert null.anomalous is False


def test_a_drop_is_anomalous_but_never_a_finding():
    baseline = make_series([0.55, 0.60, 0.65, 0.58, 0.62, 0.60, 0.57, 0.63, 0.61, 0.59])
    analyses = judge(baseline, make_series([*baseline.null_rates, 0.0]))
    (null,) = [a for a in analyses if a.metric == NULL_RATE]
    assert (null.anomalous, null.direction) == (True, "below")
    assert to_findings(analyses) == []


def test_a_duplicate_spike_on_a_near_unique_column():
    baseline = make_series(CALM, dup_rates=[0.0, 0.01, 0.0, 0.02, 0.0, 0.01, 0.0, 0.0, 0.01, 0.0])
    current = make_series([*CALM, 0.05], dup_rates=[*baseline.duplicate_rates, 0.24])
    findings = to_findings(judge(baseline, current))
    assert [f.rule_id for f in findings] == ["DUPLICATE_SPIKE"]


def test_missing_values_are_skipped_not_treated_as_zero():
    baseline = make_series([None, 0.05, None, 0.06, 0.04, 0.05, 0.05, None, 0.06, 0.05, 0.04])
    current = make_series([*baseline.null_rates, None])
    assert [a for a in judge(baseline, current) if a.metric == NULL_RATE] == []
    seen = make_series([*baseline.null_rates, 0.05])
    (null,) = [a for a in judge(baseline, seen) if a.metric == NULL_RATE]
    assert null.detections[0].history_size == 8, "only the eight defined values are history"


def test_too_little_history_means_no_judgement_and_no_finding():
    baseline = make_series([0.05, 0.05, 0.06])
    analyses = judge(baseline, make_series([0.05, 0.05, 0.06, 0.9]))
    assert all(a.evaluated == 0 and not a.anomalous for a in analyses)
    assert to_findings(analyses) == []


# ---- distribution shift -----------------------------------------------------------------------

BASE_DISTRIBUTIONS = [
    {"CARD": 69, "PAYPAL": 25, "BANK": 5},
    {"CARD": 67, "PAYPAL": 28, "BANK": 5},
    {"CARD": 71, "PAYPAL": 25, "BANK": 4},
    {"CARD": 68, "PAYPAL": 26, "BANK": 6},
    {"CARD": 70, "PAYPAL": 24, "BANK": 6},
    {"CARD": 66, "PAYPAL": 29, "BANK": 5},
    {"CARD": 69, "PAYPAL": 26, "BANK": 5},
    {"CARD": 72, "PAYPAL": 23, "BANK": 5},
]


def distribution_series(*extra):
    dists = [*BASE_DISTRIBUTIONS, *extra]
    return make_series(
        [0.0] * len(dists), distributions=dists, table="Order", column="paymentMethod"
    )


def test_a_distribution_shift_is_flagged_and_explained():
    baseline, current = (
        distribution_series(),
        distribution_series({"BANK": 73, "CARD": 21, "PAYPAL": 6}),
    )
    (shift,) = [a for a in judge(baseline, current) if a.metric == DISTRIBUTION_SHIFT]
    assert (shift.anomalous, shift.direction) == (True, "above")
    assert shift.observation == pytest.approx(0.68, abs=0.02), "about two thirds of the mix moved"
    top = shift.explanation["categories"][0]
    assert (
        top["value"] == "BANK"
        and top["baselineShare"] < 0.07
        and top["currentShare"] == pytest.approx(0.73)
    )


def test_ordinary_variation_in_the_mix_is_not_a_shift():
    baseline, current = (
        distribution_series(),
        distribution_series({"CARD": 68, "PAYPAL": 27, "BANK": 5}),
    )
    (shift,) = [a for a in judge(baseline, current) if a.metric == DISTRIBUTION_SHIFT]
    assert shift.anomalous is False


def test_a_brand_new_category_counts_as_movement():
    baseline, current = (
        distribution_series(),
        distribution_series({"CARD": 40, "PAYPAL": 20, "BANK": 5, "CRYPTO": 35}),
    )
    (shift,) = [a for a in judge(baseline, current) if a.metric == DISTRIBUTION_SHIFT]
    assert shift.anomalous is True
    assert "CRYPTO" in {c["value"] for c in shift.explanation["categories"]}


def test_a_window_without_a_stored_distribution_is_not_judged():
    baseline = distribution_series()
    current = make_series(
        [0.0] * 9, distributions=[*BASE_DISTRIBUTIONS, None], table="Order", column="paymentMethod"
    )
    assert [a for a in judge(baseline, current) if a.metric == DISTRIBUTION_SHIFT] == []


# ---- the vote --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fired", "evaluated", "any_", "majority", "all_"),
    [
        (0, 3, False, False, False),
        (1, 3, True, False, False),
        (2, 3, True, True, False),
        (3, 3, True, True, True),
        (1, 2, True, False, False),
        (2, 2, True, True, True),
        (0, 0, False, False, False),
    ],
)
def test_vote_rules(fired, evaluated, any_, majority, all_):
    assert (
        passes_vote(fired, evaluated, "any"),
        passes_vote(fired, evaluated, "majority"),
        passes_vote(fired, evaluated, "all"),
    ) == (any_, majority, all_)


def test_detectors_can_disagree_and_the_vote_decides():
    # One large outlier inflates the standard deviation, so z-score and the moving average stay
    # wide; the IQR ignores it and its range collapses. Only IQR flags a value of 5.
    history = [1.0] * 9 + [10.0]
    baseline, current = make_series(history), make_series([*history, 5.0])
    fired = {d.detector: d.anomalous for d in judge(baseline, current)[0].detections}
    assert fired == {"zscore": False, "iqr": True, "moving_average": False}
    outcomes = {
        vote: judge(baseline, current, vote=vote)[0].anomalous
        for vote in ("any", "majority", "all")
    }
    assert outcomes == {"any": True, "majority": False, "all": False}


def test_confidence_rises_with_agreement():
    history = [1.0] * 9 + [10.0]
    baseline = make_series(history)
    one_of_three = to_findings(judge(baseline, make_series([*history, 5.0]), vote="any"))
    assert [f.confidence for f in one_of_three] == ["LOW"]
    all_three = to_findings(judge(make_series(CALM), make_series([*CALM, 0.63])))
    assert [f.confidence for f in all_three] == ["HIGH"]


def test_a_detector_subset_can_be_chosen():
    baseline, current = make_series(CALM), make_series([*CALM, 0.63])
    (null,) = [
        a for a in judge(baseline, current, detectors=[IQRDetector()]) if a.metric == NULL_RATE
    ]
    assert [d.detector for d in null.detections] == ["iqr"]


# ---- findings -----------------------------------------------------------------------------------


def null_spike_finding():
    return to_findings(judge(make_series(CALM), make_series([*CALM, 0.63])))[0]


def test_finding_reports_each_detectors_learned_range_as_evidence():
    finding = null_spike_finding()
    assert (finding.rule_id, finding.file, finding.line, finding.severity) == (
        "NULL_SPIKE",
        "table:Customer",
        0,
        "MEDIUM",
    )
    assert [e.source for e in finding.evidence] == ["DATA_QUALITY"] * 3
    zscore = next(e for e in finding.evidence if e.data["detector"] == "zscore")
    assert (zscore.data["table"], zscore.data["column"], zscore.data["metric"]) == (
        "Customer",
        "phone",
        "null_rate",
    )
    assert zscore.data["expectedLower"] < 0.05 < zscore.data["expectedUpper"] < 0.63
    assert zscore.data["historySize"] == 10 and zscore.data["parameters"] == {"sigmas": 3.0}
    assert "learned range" in zscore.description
    assert finding.suggested_fix.startswith("```sql")


def test_fingerprint_is_stable_across_windows_and_values():
    a = null_spike_finding()
    baseline = make_series([*CALM, 0.05])
    b = to_findings(judge(baseline, make_series([*CALM, 0.05, 0.9])))[0]
    assert a.fingerprint == b.fingerprint


def test_distribution_finding_carries_the_moved_categories():
    baseline, current = (
        distribution_series(),
        distribution_series({"BANK": 73, "CARD": 21, "PAYPAL": 6}),
    )
    (finding,) = to_findings(judge(baseline, current))
    assert finding.rule_id == "DISTRIBUTION_SHIFT"
    assert finding.evidence[-1].data["categories"][0]["value"] == "BANK"


def test_findings_score_against_ground_truth_entries():
    manifest = Manifest.model_validate(
        {
            "schemaVersion": 1,
            "app": "t",
            "entries": [
                {
                    "id": "n1",
                    "problemType": "null_spike",
                    "category": "data_quality",
                    "table": "Customer",
                    "column": "phone",
                    "expectedRuleId": "NULL_SPIKE",
                    "description": "d",
                    "injectedAt": "2026-09-26T00:00:00Z",
                }
            ],
        }
    )
    result = score([null_spike_finding()], manifest)
    assert (result.aggregate.tp, result.aggregate.fp, result.aggregate.fn) == (1, 0, 0)


# ---- choosing baseline and current windows ---------------------------------------------------


def test_the_latest_window_is_judged_by_default_and_a_series_can_be_judged_against_its_own_past():
    series = {("Customer", "phone"): make_series([*CALM, 0.63])}
    analyses = detect_anomalies(series, series, history_before_window=True)
    assert [(a.metric, a.anomalous) for a in analyses] == [
        (NULL_RATE, True),
        (DUPLICATE_RATE, False),
    ]
    # Uncut, the spike itself is learned as 'normal': the z-score range balloons
    # (the robust IQR range does not, which is why the vote still flags it).
    contaminated = detect_anomalies(series, series, history_before_window=False)

    def zscore(found):
        (null,) = [a for a in found if a.metric == NULL_RATE]
        return next(d for d in null.detections if d.detector == "zscore")

    clean_range, dirty_range = zscore(analyses), zscore(contaminated)
    assert (clean_range.history_size, dirty_range.history_size) == (10, 11)
    assert dirty_range.upper > 5 * clean_range.upper


def test_a_specific_window_can_be_chosen():
    series = {("Customer", "phone"): make_series([*CALM, 0.63, 0.05])}
    spike_window = series[("Customer", "phone")].windows[10].start
    analyses = detect_anomalies(
        series, series, window_start=spike_window, history_before_window=True
    )
    assert [a.anomalous for a in analyses if a.metric == NULL_RATE] == [True]


def test_only_columns_present_in_both_series_are_analyzed():
    baseline = {("A", "x"): make_series(CALM, table="A", column="x")}
    current = {("B", "y"): make_series(CALM, table="B", column="y")}
    assert detect_anomalies(baseline, current) == []


# ---- backtest --------------------------------------------------------------------------------


def test_backtest_judges_each_window_only_against_earlier_ones():
    quiet = make_series([0.05, 0.06, 0.04, 0.05, 0.05, 0.06, 0.04, 0.05, 0.05, 0.05, 0.05, 0.05])
    result = backtest({quiet.key: quiet})
    # windows 5..11 judged, two metrics each, three detectors
    assert result["per_detector"]["zscore"]["evaluations"] == 14
    assert result["vote_result"]["evaluations"] == 14


def test_backtest_reports_a_spike_as_an_alarm_at_its_window():
    spiky = make_series([0.05, 0.06, 0.04, 0.05, 0.05, 0.06, 0.04, 0.05, 0.9, 0.05, 0.05, 0.05])
    result = backtest({spiky.key: spiky})
    assert [
        (a["window_start"][:10], a["metric"], a["direction"]) for a in result["false_alarms"]
    ] == [(windows(9)[8].start.date().isoformat(), NULL_RATE, "above")]
    assert result["per_detector"]["zscore"]["alarms_above"] >= 1


def test_backtest_of_a_series_shorter_than_min_history_evaluates_nothing():
    short = make_series(CALM[:4])
    assert backtest({short.key: short})["vote_result"]["evaluations"] == 0


# ---- loading from the profile store ----------------------------------------------------------


def test_series_are_loaded_aligned_and_ordered_from_stored_profiles(profile_store):
    for m, rate, dist in (
        (3, 0.6, {"gold": 50, "silver": 50}),
        (1, 0.04, {"gold": 60, "silver": 40}),
        (2, 0.05, None),
    ):
        run = make_run(
            window=month(m), null_rate=rate, label="clean", app="shop", distribution=dist or {}
        )
        profile_store.save(run)
    series = load_series(profile_store, "shop", "clean")
    phone = series[("Customer", "phone")]
    assert [w.start.month for w in phone.windows] == [1, 2, 3]
    assert phone.null_rates == (0.04, 0.05, 0.6) and phone.duplicate_rates == (0.05, 0.05, 0.05)
    assert phone.row_counts == (100, 100, 100)
    tier = series[("Customer", "tier")] if ("Customer", "tier") in series else None
    assert tier is None, "category rows without a column profile do not create a series"
    assert load_series(profile_store, "shop", "other-label") == {}
