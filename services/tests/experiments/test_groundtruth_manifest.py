import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from experiments.groundtruth import Category, Manifest, ProblemType, load_manifest

MANIFEST_DIR = Path(__file__).parents[2] / "experiments" / "groundtruth" / "manifests"
REPO_ROOT = Path(__file__).parents[3]
COMMITTED = sorted(MANIFEST_DIR.glob("*.json"))


def test_valid_manifest(make_manifest, make_entry, make_data_entry):
    m = Manifest.model_validate(make_manifest(make_entry(), make_data_entry()))
    assert [e.problem_type for e in m.entries] == [ProblemType.N_PLUS_ONE, ProblemType.NULL_SPIKE]
    assert m.entries[0].category is Category.PERFORMANCE


def test_duplicate_ids_rejected(make_manifest, make_entry):
    with pytest.raises(ValidationError, match="duplicate entry id"):
        Manifest.model_validate(make_manifest(make_entry(), make_entry()))


def test_category_must_match_problem_type(make_manifest, make_entry):
    with pytest.raises(ValidationError, match="belongs to category 'performance'"):
        Manifest.model_validate(make_manifest(make_entry(category="data_quality")))


def test_expected_rule_must_belong_to_problem_type(make_manifest, make_entry):
    with pytest.raises(ValidationError, match="detects 'unpaginated_find_many'"):
        Manifest.model_validate(make_manifest(make_entry(expectedRuleId="MISSING_PAGINATION")))


def test_unknown_rule_rejected(make_manifest, make_entry):
    with pytest.raises(ValidationError, match="unknown rule"):
        Manifest.model_validate(make_manifest(make_entry(expectedRuleId="MADE_UP")))


@pytest.mark.parametrize("missing", ["file", "line", "endpoint"])
def test_performance_entries_need_code_location_and_endpoint(make_manifest, make_entry, missing):
    raw = make_entry()
    del raw[missing]
    with pytest.raises(ValidationError, match=missing):
        Manifest.model_validate(make_manifest(raw))


def test_data_entries_need_a_table(make_manifest, make_data_entry):
    raw = make_data_entry()
    del raw["table"]
    with pytest.raises(ValidationError, match="table"):
        Manifest.model_validate(make_manifest(raw))


def test_line_span_must_be_ordered(make_manifest, make_entry):
    with pytest.raises(ValidationError, match="endLine"):
        Manifest.model_validate(make_manifest(make_entry(line=20, endLine=10)))


def test_unknown_fields_rejected(make_manifest, make_entry):
    with pytest.raises(ValidationError, match="Extra inputs"):
        Manifest.model_validate(make_manifest(make_entry(severity="HIGH")))


def test_injected_at_must_be_a_timestamp(make_manifest, make_entry):
    with pytest.raises(ValidationError, match="injectedAt"):
        Manifest.model_validate(make_manifest(make_entry(injectedAt="last week")))


def test_load_manifest_from_file(tmp_path, make_manifest, make_entry):
    path = tmp_path / "m.json"
    path.write_text(json.dumps(make_manifest(make_entry())))
    assert load_manifest(path).entries[0].id == "ecom-n1-01"


def test_anchor_requires_a_code_location(make_manifest, make_data_entry):
    with pytest.raises(ValidationError, match="anchor"):
        Manifest.model_validate(make_manifest(make_data_entry(anchor="x")))


@pytest.mark.parametrize("path", COMMITTED, ids=lambda p: p.name)
def test_committed_manifests_validate(path):
    load_manifest(path)


@pytest.mark.parametrize("path", COMMITTED, ids=lambda p: p.name)
def test_committed_manifest_locations_point_at_their_anchors(path):
    manifest = load_manifest(path)
    assert manifest.source_root, "committed manifests must declare sourceRoot"
    root = REPO_ROOT / manifest.source_root
    for entry in manifest.entries:
        if entry.file is None or entry.line is None:
            continue
        lines = (root / entry.file).read_text(encoding="utf-8").splitlines()
        assert entry.anchor, f"{entry.id}: committed code entries need an anchor"
        assert entry.anchor in lines[entry.line - 1], (
            f"{entry.id}: line {entry.line} no longer holds its anchor"
        )
        assert (entry.end_line or entry.line) <= len(lines), f"{entry.id}: endLine past end of file"
