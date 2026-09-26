import math

import pytest

from experiments.realworld import select_repos as sel
from experiments.realworld import worksheet as ws

# ---- selection tests (PROTOCOL.md) --------------------------------------------------------------


def meta(**over):
    base = {
        "name": "shop-api",
        "description": "Order management backend",
        "topics": ["prisma", "postgres"],
        "owner": {"login": "acme"},
        "fork": False,
        "archived": False,
        "is_template": False,
        "license": {"spdx_id": "MIT"},
    }
    base.update(over)
    return base


def test_a_plain_permissive_repository_passes_the_metadata_tests():
    assert sel.metadata_tests(sel.Candidate("acme/shop-api"), meta()) is None


@pytest.mark.parametrize(
    ("over", "code"),
    [
        ({"fork": True}, "E1"),
        ({"archived": True}, "E1"),
        ({"is_template": True}, "E1"),
        ({"owner": {"login": "prisma"}}, "E2"),
        ({"name": "nextjs-starter"}, "E3"),
        ({"description": "A tutorial for Prisma"}, "E3"),
        ({"topics": ["prisma", "example"]}, "E3"),
        ({"license": {"spdx_id": "GPL-3.0"}}, "I4"),
        ({"license": {"spdx_id": "NOASSERTION"}}, "I4"),
        ({"license": None}, "I4"),
    ],
)
def test_each_exclusion_is_applied_and_named(over, code):
    assert sel.metadata_tests(sel.Candidate("acme/x"), meta(**over)).startswith(code)


def test_only_the_datasource_provider_decides_postgres():
    postgres = 'datasource db {\n  provider = "postgresql"\n  url = env("U")\n}\n'
    assert sel.provider_is_postgres(postgres)
    assert sel.provider_is_postgres(postgres.replace("postgresql", "postgres"))
    assert not sel.provider_is_postgres(postgres.replace("postgresql", "mysql"))
    # A provider on the generator must not be mistaken for the datasource's.
    generator = (
        'generator client {\n provider = "postgresql"\n}\ndatasource db {\n provider = "mysql"\n}'
    )
    assert not sel.provider_is_postgres(generator)


def test_models_are_counted_from_model_blocks_only():
    schema = "model A {\n id Int\n}\nmodel B {\n id Int\n}\nenum E {\n X\n}\n// model C {}\n"
    assert sel.count_models(schema) == 2


def test_typescript_loc_skips_dependencies_declarations_and_generated_code(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text("a\nb\nc\n")
    (tmp_path / "src" / "b.tsx").write_text("x\n")
    (tmp_path / "src" / "types.d.ts").write_text("d\n" * 50)
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "i.ts").write_text("n\n" * 99)
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "client.ts").write_text("g\n" * 99)
    assert sel.typescript_loc(tmp_path) == 4


# ---- worksheet ---------------------------------------------------------------------------------


def test_context_is_ten_lines_either_side_with_the_flagged_line_marked():
    text = "\n".join(f"line{n}" for n in range(1, 51))
    lines = ws.source_context(text, 25, None).splitlines()
    assert len(lines) == 21
    assert lines[0].endswith("| line15") and lines[-1].endswith("| line35")
    assert [row for row in lines if row.startswith(">")] == [lines[10]]


def test_context_covers_the_whole_flagged_span_and_stops_at_the_file_edges():
    text = "\n".join(f"l{n}" for n in range(1, 13))
    lines = ws.source_context(text, 3, 5).splitlines()
    assert lines[0].split("|")[1].strip() == "l1"
    assert lines[-1].split("|")[1].strip() == "l12"
    assert sum(row.startswith(">") for row in lines) == 3


def test_missing_source_is_said_not_hidden():
    assert "not available" in ws.source_context(None, 1, None)


def test_models_come_from_evidence_in_first_seen_order():
    evidence = [
        {"data": {"model": "Post"}},
        {"data": None},
        {"data": {"model": "User", "models": ["Post", "Tag"]}},
    ]
    assert ws.models_named(evidence) == ["Post", "User", "Tag"]


SCHEMA = "model User {\n  id Int @id\n}\n\nmodel Post {\n  id Int @id\n  @@index([id])\n}\n"


def test_schema_excerpt_extracts_only_the_named_models():
    excerpt = ws.schema_excerpt(SCHEMA, ["Post"])
    assert "model Post" in excerpt and "model User" not in excerpt and "@@index" in excerpt


def test_schema_excerpt_says_when_nothing_matches():
    assert "no model" in ws.schema_excerpt(SCHEMA, ["Ghost"])
    assert "no model" in ws.schema_excerpt(SCHEMA, [])


def test_overlong_models_are_cut_and_say_so():
    big = "model Big {\n" + "  f Int\n" * 200 + "}\n"
    assert "more lines" in ws.schema_excerpt(big, ["Big"])


def findings(counts):
    return [
        {"finding_id": f"{rule}-{n:03d}", "rule_id": rule}
        for rule, count in counts.items()
        for n in range(count)
    ]


def test_double_label_sample_has_at_least_a_fifth_of_every_rule():
    data = findings({"A": 10, "B": 3, "C": 1})
    chosen = ws.double_label_sample(data)
    for rule, count in {"A": 10, "B": 3, "C": 1}.items():
        got = sum(i.startswith(rule + "-") for i in chosen)
        assert got >= math.ceil(0.2 * count) and got >= 1


def test_double_label_sample_is_reproducible():
    data = findings({"A": 40, "B": 25})
    assert ws.double_label_sample(data) == ws.double_label_sample(list(reversed(data)))


def test_worksheet_has_empty_label_columns_and_hides_confidence():
    assert "confidence" not in ws.WORKSHEET_COLUMNS and "severity" not in ws.WORKSHEET_COLUMNS
    for column in ("label", "fp_cause", "rationale", "label_2", "rationale_2"):
        assert column in ws.WORKSHEET_COLUMNS
    assert {"confidence", "severity"} <= set(ws.KEY_COLUMNS)


# ---- the harness, end to end on a local repository (no network) --------------------------------

import shutil  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

from experiments.realworld import analyze_repos  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "source"


def git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def local_repo(tmp_path, monkeypatch):
    """A git repository at the location the harness expects, already at its pinned commit."""
    monkeypatch.setattr(analyze_repos, "WORK", tmp_path)
    clone = analyze_repos.clone_dir("acme/shop")
    shutil.copytree(FIXTURES / "rules", clone / "src")
    shutil.copy(FIXTURES / "schema.prisma", clone / "prisma.schema.prisma")
    (clone / "prisma").mkdir()
    shutil.move(clone / "prisma.schema.prisma", clone / "prisma" / "schema.prisma")
    git(clone, "init", "--quiet")
    git(clone, "add", ".")
    git(clone, "commit", "--quiet", "-m", "pin")
    return clone, git(clone, "rev-parse", "HEAD")


def candidate(sha, schema="prisma/schema.prisma"):
    return {"repo": "acme/shop", "last_commit_sha": sha, "schema_path": schema}


def test_a_repository_is_analyzed_at_its_pin_and_findings_are_returned(local_repo):
    _, sha = local_repo
    result, found = analyze_repos.analyze_repo(candidate(sha), timeout=120)
    assert result["status"] == "ok" and result["error"] is None
    assert found, "the rules fixtures contain problems"
    assert all({"ruleId", "confidence", "file", "line", "fingerprint"} <= set(f) for f in found)
    assert result["commit_sha"] == sha


def test_findings_are_ordered_so_ids_are_stable(local_repo):
    _, sha = local_repo
    _, found = analyze_repos.analyze_repo(candidate(sha), timeout=120)
    keys = [(f["file"], f["line"], f["ruleId"], f["fingerprint"]) for f in found]
    assert keys == sorted(keys)


def test_an_unusable_repository_is_recorded_as_failed_not_dropped(local_repo):
    _, sha = local_repo
    result, found = analyze_repos.analyze_repo(candidate(sha, "does/not/exist.prisma"), timeout=120)
    assert result["status"] == "failed" and result["error"] and found == []


def test_worksheet_rows_come_from_the_pinned_commit(local_repo):
    clone, sha = local_repo
    _, found = analyze_repos.analyze_repo(candidate(sha), timeout=120)
    first = found[0]
    stored = {
        "finding_id": "R01-001",
        "repo": "acme/shop",
        "commit_sha": sha,
        "rule_id": first["ruleId"],
        "title": first["title"],
        "body": first["body"],
        "file": first["file"],
        "line": first["line"],
        "end_line": first.get("endLine"),
        "evidence": first["evidence"],
        "severity": first["severity"],
        "confidence": first["confidence"],
        "fingerprint": first["fingerprint"],
    }
    # The working tree changing after the analysis must not change what a labeller sees.
    (clone / first["file"]).write_text("// edited after the analysis\n")
    rows, key = ws.build([stored], [{"repo": "acme/shop", "schema_path": "prisma/schema.prisma"}])
    assert "edited after" not in rows[0]["source_context"]
    assert rows[0]["label"] == "" and rows[0]["rationale"] == ""
    assert key[0]["confidence"] == first["confidence"]
