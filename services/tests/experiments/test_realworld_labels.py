import csv

import pytest

pytest.importorskip("scipy")

from experiments.realworld import labels as lb  # noqa: E402
from experiments.realworld import worksheet as ws  # noqa: E402

# ---- statistics against values worked out by hand ------------------------------------------------


def test_wilson_matches_the_textbook_value_at_50_of_100():
    low, high = lb.wilson(50, 100)
    assert low == pytest.approx(0.4038, abs=1e-3) and high == pytest.approx(0.5962, abs=1e-3)


def test_wilson_stays_inside_the_unit_interval_at_the_extremes():
    assert lb.wilson(0, 10)[0] == 0.0 and lb.wilson(0, 10)[1] == pytest.approx(0.2775, abs=1e-3)
    assert lb.wilson(10, 10)[1] == pytest.approx(1.0)
    assert lb.wilson(0, 0) == (None, None)


def test_kappa_of_the_classic_two_rater_example_is_0_4():
    # 20 yes/yes, 15 no/no, 5 yes/no, 10 no/yes: observed 0.7, chance 0.5.
    a = ["y"] * 20 + ["n"] * 15 + ["y"] * 5 + ["n"] * 10
    b = ["y"] * 20 + ["n"] * 15 + ["n"] * 5 + ["y"] * 10
    assert lb.cohens_kappa(a, b) == pytest.approx(0.4)


def test_kappa_is_one_for_perfect_agreement_and_undefined_when_everyone_says_one_thing():
    assert lb.cohens_kappa(["TP", "FP", "TP"], ["TP", "FP", "TP"]) == pytest.approx(1.0)
    assert lb.cohens_kappa(["TP", "TP"], ["TP", "TP"]) is None
    assert lb.cohens_kappa([], []) is None


def test_kappa_is_below_zero_when_raters_systematically_disagree():
    assert lb.cohens_kappa(["TP", "FP"] * 5, ["FP", "TP"] * 5) < 0


# ---- worksheets ----------------------------------------------------------------------------------


def make_rows(spec):
    """spec: (repo, rule, label, cause, double, label_2)"""
    rows = []
    for i, (repo, rule, label, cause, double, label_2) in enumerate(spec):
        row = {c: "" for c in ws.WORKSHEET_COLUMNS}
        row.update(
            finding_id=f"R{i:03d}",
            repo=repo,
            rule_id=rule,
            label=label,
            fp_cause=cause,
            double_label=double,
            label_2=label_2,
            fp_cause_2="other" if label_2 == "FP" else "",
            rationale="because" if label == "UNSURE" else "",
        )
        rows.append(row)
    return rows


def write(tmp_path, rows):
    path = tmp_path / "w.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ws.WORKSHEET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def loaded(tmp_path, spec, **kw):
    return lb.load(write(tmp_path, make_rows(spec)), **kw)


N1, IDX, PAG = "N_PLUS_ONE_IN_LOOP", lb.INDEX_RULE, "MISSING_PAGINATION"


def test_a_conforming_worksheet_loads(tmp_path):
    rows = loaded(
        tmp_path, [("a/x", N1, "tp", "", "no", ""), ("a/x", N1, "FP", "analysis_error", "no", "")]
    )
    assert [r["label"] for r in rows] == ["TP", "FP"]


@pytest.mark.parametrize(
    ("spec", "fragment"),
    [
        ([("a/x", N1, "", "", "no", "")], "no label"),
        ([("a/x", N1, "MAYBE", "", "no", "")], "not one of"),
        ([("a/x", N1, "FP", "", "no", "")], "needs fp_cause"),
        ([("a/x", N1, "FP", "made_up", "no", "")], "needs fp_cause"),
        ([("a/x", N1, "TP", "analysis_error", "no", "")], "fp_cause given for a TP"),
        ([("a/x", N1, "TP", "", "yes", "")], "no second label"),
        ([("a/x", N1, "TP", "", "no", "FP")], "not in the double sample"),
    ],
)
def test_every_departure_from_the_protocol_is_reported(tmp_path, spec, fragment):
    with pytest.raises(lb.LabelError, match=fragment):
        loaded(tmp_path, spec)


def test_unsure_needs_a_rationale(tmp_path):
    rows = make_rows([("a/x", N1, "UNSURE", "", "no", "")])
    rows[0]["rationale"] = ""
    with pytest.raises(lb.LabelError, match="rationale"):
        lb.load(write(tmp_path, rows))


def test_every_problem_is_listed_not_just_the_first(tmp_path):
    with pytest.raises(lb.LabelError) as error:
        loaded(tmp_path, [("a/x", N1, "", "", "no", ""), ("a/x", N1, "MAYBE", "", "no", "")])
    assert str(error.value).count("\n") == 1


def test_partial_labelling_is_allowed_only_when_asked_and_is_reported(tmp_path):
    spec = [("a/x", N1, "TP", "", "no", ""), ("a/x", N1, "", "", "no", "")]
    with pytest.raises(lb.LabelError):
        loaded(tmp_path, spec)
    rows = loaded(tmp_path, spec, allow_partial=True)
    assert lb.summarize(rows)["label_coverage"] == {"findings": 2, "labelled": 1, "unlabelled": 1}


# ---- results -------------------------------------------------------------------------------------

SPEC = (
    [("a/x", N1, "TP", "", "no", "")] * 6
    + [("b/y", N1, "FP", "analysis_error", "no", "")] * 2
    + [("b/y", N1, "UNSURE", "", "no", "")]
    + [("a/x", IDX, "TP", "", "no", "")] * 2
    + [("c/z", IDX, "FP", "index_outside_schema", "no", "")] * 2
    + [("c/z", IDX, "FP", "schema_misread", "no", "")]
)


def test_precision_excludes_unsure_and_says_how_many_there_were(tmp_path):
    rule = lb.summarize(loaded(tmp_path, SPEC))["per_rule"][N1]
    assert (rule["tp"], rule["fp"], rule["unsure"]) == (6, 2, 1)
    assert rule["precision"] == pytest.approx(6 / 8)
    assert rule["precision_if_unsure_all_fp"] == pytest.approx(6 / 9)
    assert rule["precision_if_unsure_all_tp"] == pytest.approx(7 / 9)
    assert rule["wilson_95"]["low"] < 0.75 < rule["wilson_95"]["high"]


def test_overall_precision_pools_all_rules_and_macro_average_weights_rules_equally(tmp_path):
    overall = lb.summarize(loaded(tmp_path, SPEC))["overall"]
    assert overall["precision"] == pytest.approx(8 / 13)
    assert overall["macro_average_precision"] == pytest.approx((6 / 8 + 2 / 5) / 2)


def test_the_repo_cluster_interval_is_reported_and_is_wider_than_wilson_here(tmp_path):
    rule = lb.summarize(loaded(tmp_path, SPEC))["per_rule"][N1]
    cluster = rule["repo_cluster_bootstrap_95"]
    wilson = rule["wilson_95"]
    assert cluster["low"] is not None
    assert cluster["high"] - cluster["low"] >= wilson["high"] - wilson["low"] - 1e-9


def test_agreement_uses_only_rows_with_both_labels_and_keeps_disagreements(tmp_path):
    spec = (
        [("a/x", N1, "TP", "", "yes", "TP")] * 4
        + [("a/x", N1, "FP", "other", "yes", "FP")] * 3
        + [("a/x", N1, "TP", "", "yes", "FP")] * 1
        + [("a/x", N1, "TP", "", "no", "")] * 5
    )
    result = lb.agreement(loaded(tmp_path, spec))
    assert result["with_both_labels"] == 8
    assert result["three_way_TP_FP_UNSURE"]["percent_agreement"] == pytest.approx(7 / 8)
    assert len(result["disagreements"]) == 1
    assert (
        result["disagreements"][0]["first"] == "TP" and result["disagreements"][0]["second"] == "FP"
    )


def test_false_positive_causes_are_grouped_by_what_went_wrong(tmp_path):
    causes = lb.fp_causes(loaded(tmp_path, SPEC))
    assert causes["false_positives"] == 5
    assert causes["by_cause"]["analysis_error"] == 2
    assert causes["by_cause"]["index_outside_schema"] == 2
    assert causes["by_rule_and_cause"][IDX]["schema_misread"] == 1


def test_the_index_divergence_is_the_share_of_index_findings_whose_index_existed_elsewhere(
    tmp_path,
):
    result = lb.index_divergence(loaded(tmp_path, SPEC))
    assert (result["labelled_findings"], result["index_in_database_not_in_schema"]) == (5, 2)
    assert result["rate"] == pytest.approx(0.4)
    assert result["repos_with_divergence"] == ["c/z"]
    assert "lower bound" in result["caveat"]


def test_confidence_from_the_key_lets_precision_be_split_by_it(tmp_path):
    rows = loaded(tmp_path, [("a/x", N1, "TP", "", "no", ""), ("a/x", N1, "FP", "other", "no", "")])
    rows[0]["confidence"], rows[1]["confidence"] = "HIGH", "LOW"
    by = lb.summarize(rows)["precision_by_confidence"][N1]
    assert by["HIGH"]["precision"] == 1.0 and by["LOW"]["precision"] == 0.0


# ---- against the controlled experiment -------------------------------------------------------


def test_a_rule_with_no_controlled_counterpart_is_said_to_be_incomparable(tmp_path):
    summary = lb.summarize(loaded(tmp_path, SPEC))
    out = lb.compare_with_controlled(summary, {N1: {"tp": 10, "fp": 0}})
    assert out[IDX]["comparable"] is False and "no injected" in out[IDX]["reason"]


def test_a_real_gap_from_a_perfect_controlled_precision_is_flagged_as_divergence(tmp_path):
    spec = [("a/x", N1, "TP", "", "no", "")] * 10 + [
        ("a/x", N1, "FP", "analysis_error", "no", "")
    ] * 30
    out = lb.compare_with_controlled(
        lb.summarize(loaded(tmp_path, spec)), {N1: {"tp": 12, "fp": 0}}
    )
    assert out[N1]["diverges"] is True
    assert out[N1]["difference"] == pytest.approx(0.25 - 1.0)


def test_similar_precision_is_not_flagged(tmp_path):
    spec = [("a/x", N1, "TP", "", "no", "")] * 9 + [("a/x", N1, "FP", "other", "no", "")]
    out = lb.compare_with_controlled(lb.summarize(loaded(tmp_path, spec)), {N1: {"tp": 9, "fp": 1}})
    assert out[N1]["diverges"] is False
