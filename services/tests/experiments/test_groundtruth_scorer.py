import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from experiments.groundtruth import Manifest, ProblemType, parse_findings, score

SERVICES = Path(__file__).parents[2]


def run(manifest_raw, findings_raw):
    return score(parse_findings(findings_raw), Manifest.model_validate(manifest_raw))


def by_type(report, problem_type):
    return next(s for s in report.per_problem_type if s.problem_type == problem_type)


def test_exact_match_is_a_true_positive(make_manifest, make_entry, make_finding):
    report = run(make_manifest(make_entry()), [make_finding()])
    s = by_type(report, ProblemType.N_PLUS_ONE)
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)
    assert (s.precision, s.recall, s.f1) == (1.0, 1.0, 1.0)
    assert report.matches[0].entry_id == "ecom-n1-01"


def test_finding_inside_entry_span_matches(make_manifest, make_entry, make_finding):
    report = run(make_manifest(make_entry(line=18, endLine=24)), [make_finding(line=21)])
    assert report.aggregate.tp == 1


def test_finding_span_overlapping_entry_line_matches(make_manifest, make_entry, make_finding):
    report = run(make_manifest(make_entry(line=22)), [make_finding(line=20, endLine=23)])
    assert report.aggregate.tp == 1


def test_line_outside_span_is_fp_and_fn(make_manifest, make_entry, make_finding):
    report = run(make_manifest(make_entry(line=20)), [make_finding(line=21)])
    s = by_type(report, ProblemType.N_PLUS_ONE)
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


def test_other_file_is_fp_and_fn(make_manifest, make_entry, make_finding):
    report = run(make_manifest(make_entry()), [make_finding(file="src/other.ts")])
    assert (report.aggregate.tp, report.aggregate.fp, report.aggregate.fn) == (0, 1, 1)


def test_wrong_problem_type_at_right_location_does_not_match(
    make_manifest, make_entry, make_finding
):
    report = run(make_manifest(make_entry()), [make_finding(ruleId="MISSING_PAGINATION")])
    assert by_type(report, ProblemType.N_PLUS_ONE).fn == 1
    assert by_type(report, ProblemType.UNPAGINATED_FIND_MANY).fp == 1


def test_any_rule_of_the_same_problem_type_matches(make_manifest, make_entry, make_finding):
    # A later layer (runtime, correlation) may report the same problem under
    # another rule id; matching is by problem type.
    report = run(make_manifest(make_entry()), [make_finding(ruleId="RUNTIME_N_PLUS_ONE")])
    assert report.aggregate.tp == 1


def test_second_finding_for_same_problem_is_a_duplicate_not_fp(
    make_manifest, make_entry, make_finding
):
    report = run(
        make_manifest(make_entry()),
        [make_finding(fingerprint="a"), make_finding(ruleId="RUNTIME_N_PLUS_ONE", fingerprint="b")],
    )
    s = by_type(report, ProblemType.N_PLUS_ONE)
    assert (s.tp, s.fp, s.fn, s.duplicates) == (1, 0, 0, 1)


def test_rules_without_ground_truth_count_as_unmapped_false_positives(
    make_manifest, make_entry, make_finding
):
    report = run(
        make_manifest(make_entry()),
        [make_finding(), make_finding(ruleId="UNBOUNDED_MUTATION", line=5)],
    )
    assert report.aggregate.fp == 1
    assert [(f.rule_id, f.problem_type) for f in report.false_positives] == [
        ("UNBOUNDED_MUTATION", None)
    ]


def test_unknown_rule_ids_are_unmapped_false_positives(make_manifest, make_finding):
    report = run(make_manifest(), [make_finding(ruleId="SOMETHING_NEW")])
    assert report.aggregate.fp == 1
    assert report.false_positives[0].problem_type is None


def test_one_to_one_assignment_is_maximal(make_manifest, make_entry, make_finding):
    # Finding A overlaps both entries, finding B only the first. A greedy
    # assignment of A to the first entry would leave B unmatched.
    entries = [
        make_entry(id="first", line=10, endLine=20),
        make_entry(id="second", line=20, endLine=30),
    ]
    findings = [
        make_finding(line=15, endLine=25, fingerprint="A"),
        make_finding(line=12, fingerprint="B"),
    ]
    report = run(make_manifest(*entries), findings)
    assert report.aggregate.tp == 2
    assert {(m.entry_id, m.fingerprint) for m in report.matches} == {
        ("first", "B"),
        ("second", "A"),
    }


def test_data_problem_matches_on_table_and_column_evidence(
    make_manifest, make_data_entry, make_finding
):
    finding = make_finding(
        ruleId="NULL_SPIKE",
        file="db",
        line=0,
        evidence=[
            {
                "source": "DATA_QUALITY",
                "description": "null rate",
                "data": {"table": "customer", "column": "email"},
            }
        ],
    )
    report = run(make_manifest(make_data_entry()), [finding])
    assert report.aggregate.tp == 1


def test_data_problem_column_mismatch_does_not_match(make_manifest, make_data_entry, make_finding):
    finding = make_finding(
        ruleId="NULL_SPIKE",
        evidence=[
            {
                "source": "DATA_QUALITY",
                "description": "x",
                "data": {"table": "Customer", "column": "name"},
            }
        ],
    )
    report = run(make_manifest(make_data_entry()), [finding])
    assert (report.aggregate.tp, report.aggregate.fp, report.aggregate.fn) == (0, 1, 1)


def test_entry_with_both_locations_matches_either(make_manifest, make_entry, make_finding):
    entry = make_entry(
        problemType="missing_index",
        expectedRuleId="MISSING_INDEX_ON_FILTERED_FIELD",
        table="Order",
        column="status",
    )
    static = make_finding(ruleId="MISSING_INDEX_ON_FILTERED_FIELD", fingerprint="s")
    runtime = make_finding(
        ruleId="MISSING_INDEX_ON_FILTERED_FIELD",
        file="db",
        line=0,
        fingerprint="r",
        evidence=[
            {
                "source": "RUNTIME",
                "description": "seq scan",
                "data": {"table": "Order", "column": "status"},
            }
        ],
    )
    assert run(make_manifest(entry), [static]).aggregate.tp == 1
    assert run(make_manifest(entry), [runtime]).aggregate.tp == 1


def test_metrics_are_undefined_rather_than_zero_without_denominators(make_manifest, make_entry):
    s = by_type(run(make_manifest(make_entry()), []), ProblemType.N_PLUS_ONE)
    assert (s.tp, s.fp, s.fn) == (0, 0, 1)
    assert s.precision is None
    assert s.recall == 0.0
    assert s.f1 is None


def test_aggregate_and_category_totals(make_manifest, make_entry, make_data_entry, make_finding):
    entries = [make_entry(), make_entry(id="n1-2", line=40), make_data_entry()]
    findings = [make_finding(), make_finding(ruleId="MISSING_PAGINATION", line=70)]
    report = run(make_manifest(*entries), findings)
    assert (report.aggregate.tp, report.aggregate.fp, report.aggregate.fn) == (1, 1, 2)
    categories = {c.category.value: (c.tp, c.fp, c.fn) for c in report.per_category}
    assert categories == {"performance": (1, 1, 1), "data_quality": (0, 0, 1)}
    assert report.aggregate.precision == 0.5
    assert report.aggregate.recall == pytest.approx(1 / 3)


def test_every_manifest_problem_type_is_reported_even_with_no_findings(
    make_manifest, make_entry, make_data_entry
):
    report = run(make_manifest(make_entry(), make_data_entry()), [])
    assert {s.problem_type for s in report.per_problem_type} == {
        ProblemType.N_PLUS_ONE,
        ProblemType.NULL_SPIKE,
    }


def test_scoring_is_deterministic(make_manifest, make_entry, make_finding):
    entries = [make_entry(id=f"e{i}", line=10 * i) for i in range(1, 6)]
    findings = [make_finding(line=10 * i, fingerprint=f"f{i}") for i in (5, 3, 1, 9)]
    first = run(make_manifest(*entries), findings).model_dump_json()
    second = run(make_manifest(*entries), list(reversed(findings))).model_dump_json()
    assert first == second


def test_findings_must_match_the_schema_version_1_contract(make_finding):
    with pytest.raises(ValidationError):
        parse_findings([make_finding(schemaVersion=2)])
    with pytest.raises(ValidationError):
        parse_findings([make_finding(extra="field")])


def test_cli_is_the_pipeline_entry_point(tmp_path, make_manifest, make_entry, make_finding):
    manifest_path = tmp_path / "manifest.json"
    findings_path = tmp_path / "findings.json"
    manifest_path.write_text(json.dumps(make_manifest(make_entry())))
    findings_path.write_text(json.dumps([make_finding()]))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "experiments.groundtruth",
            "--manifest",
            manifest_path,
            "--findings",
            findings_path,
        ],
        cwd=SERVICES,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["aggregate"]["tp"] == 1
