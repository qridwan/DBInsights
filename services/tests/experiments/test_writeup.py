import pytest

pytest.importorskip("scipy")

from experiments.writeup import build as wb  # noqa: E402


def ns():
    return {
        "a": {
            "b": wb.Val(0.717, "src:a.b"),
            "none": wb.Val(None, "src:none"),
            "ci": wb.Val((0.5, 0.4, 0.6), "src:ci"),
        },
        "g": {"x": wb.Val(3, "src:g.x")},
    }


def render(text):
    return wb.render(text, ns(), {})


def test_a_number_is_looked_up_formatted_and_recorded_with_its_source():
    text, used = render("recall {{a.b|pct1}} and {{g.x|int}}")
    assert text == "recall 71.7% and 3"
    assert used == [("a.b", "71.7%", "src:a.b"), ("g.x", "3", "src:g.x")]


def test_an_interval_prints_with_its_bounds():
    assert render("{{a.ci|ci}}")[0] == "50.0% (95% CI 40.0% to 60.0%)"


@pytest.mark.parametrize(
    ("template", "fragment"),
    [
        ("{{a.missing}}", "no such number"),
        ("{{a}}", "group, not a number"),
        ("{{a.none}}", "undefined"),
        ("{{block:nope}}", "unknown block"),
    ],
)
def test_a_claim_cannot_quote_a_number_the_results_do_not_contain(template, fragment):
    with pytest.raises(wb.TemplateError, match=fragment):
        render(template)


def test_p_values_use_scientific_notation_only_when_tiny():
    assert wb.FORMATS["p"](0.0625) == "0.062"
    assert wb.FORMATS["p"](2.3e-10) == "2.3e-10"


def test_the_appendix_lists_each_placeholder_once():
    _, used = render("{{a.b|pct1}} {{a.b|pct1}} {{g.x}}")
    body = wb.appendix(used)
    assert body.count("`a.b`") == 1 and body.count("`g.x`") == 1


def test_the_real_chapter_builds_with_every_number_resolved(tmp_path):
    if (
        not (wb.RESULTS / "results.json").exists()
        or not (wb.RESULTS / "collector_overhead.json").exists()
    ):
        pytest.skip("results not generated")
    out = wb.build(tmp_path / "results.md")
    text = out.read_text()
    assert "{{" not in text
    assert "## 3. RQ3" in text and "contradicts hypothesis H3" in text
    assert "Threats to validity" in text
    assert "Appendix: where every number comes from" in text
    if not (wb.RESULTS / "labels_results.json").exists():
        assert "Not yet measured" in text
