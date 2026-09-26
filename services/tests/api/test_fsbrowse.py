import pytest
from fastapi.testclient import TestClient

from api.dashboard import app as dashboard
from api.dashboard import fsbrowse
from api.dashboard.fsbrowse import BrowseError, browse
from tests.api.auth_fakes import make, sign_in


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "shop" / "prisma").mkdir(parents=True)
    (tmp_path / "shop" / "prisma" / "schema.prisma").write_text("model A {}\n")
    (tmp_path / "shop" / ".git").mkdir()
    (tmp_path / "flat").mkdir()
    (tmp_path / "flat" / "schema.prisma").write_text("model B {}\n")
    (tmp_path / "plain").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file.txt").write_text("not a folder")
    return tmp_path


def by_name(result):
    return {e["name"]: e for e in result["entries"]}


def test_only_folders_are_listed_and_files_are_never_named(tree):
    names = list(by_name(browse(str(tree))))
    assert names == ["flat", "plain", "shop"]
    assert "file.txt" not in names


def test_prisma_projects_and_git_repositories_are_marked(tree):
    entries = by_name(browse(str(tree)))
    assert entries["shop"]["is_project"] and entries["shop"]["is_git"]
    assert entries["flat"]["is_project"] and not entries["flat"]["is_git"]
    assert not entries["plain"]["is_project"]


def test_the_folder_being_viewed_is_marked_too(tree):
    assert browse(str(tree / "shop"))["is_project"] is True
    assert browse(str(tree))["is_project"] is False


def test_dependency_and_hidden_folders_are_skipped_unless_asked(tree):
    assert ".hidden" not in by_name(browse(str(tree)))
    assert ".hidden" in by_name(browse(str(tree), show_hidden=True))
    assert "node_modules" not in by_name(browse(str(tree), show_hidden=True)), (
        "never useful to pick"
    )


def test_the_parent_lets_you_walk_up_and_the_root_has_none(tree):
    assert browse(str(tree / "shop"))["parent"] == str(tree)
    assert browse("/")["parent"] is None


def test_without_a_path_it_starts_at_the_home_folder(monkeypatch, tree):
    monkeypatch.setattr(fsbrowse.Path, "home", classmethod(lambda cls: tree))
    result = browse(None)
    assert result["path"] == str(tree.resolve()) and result["home"] == str(tree)


def test_relative_segments_are_resolved_to_a_real_absolute_path(tree):
    assert browse(str(tree / "shop" / ".." / "plain"))["path"] == str((tree / "plain").resolve())


@pytest.mark.parametrize("bad", ["file.txt", "missing"])
def test_a_path_that_is_not_a_folder_is_refused(tree, bad):
    with pytest.raises(BrowseError, match="not a folder"):
        browse(str(tree / bad))


def test_a_null_byte_in_the_path_is_refused():
    with pytest.raises(BrowseError):
        browse("/tmp\x00/etc")


def test_an_unreadable_folder_is_a_403_not_a_crash(tree):
    locked = tree / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        with pytest.raises(BrowseError) as e:
            browse(str(locked))
        assert e.value.status == 403
    finally:
        locked.chmod(0o755)


def test_a_huge_folder_is_cut_off_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(fsbrowse, "MAX_ENTRIES", 5)
    for i in range(12):
        (tmp_path / f"d{i:02}").mkdir()
    result = browse(str(tmp_path))
    assert len(result["entries"]) == 5 and result["truncated"] is True


# ---- the endpoint --------------------------------------------------------------------------


@pytest.fixture
def client():
    service, _, mail, _ = make()
    dashboard.app.state.auth = service
    dashboard.app.state.store = object()
    admin = sign_in(service, mail, "admin@example.com")  # the first verified account
    user = sign_in(service, mail, "user@example.com")
    with TestClient(dashboard.app) as c:
        c.admin, c.user = admin, user
        yield c


def test_administrators_can_browse(client, tree):
    response = client.get("/v1/fs/browse", params={"path": str(tree)}, headers=client.admin)
    assert response.status_code == 200 and "shop" in {e["name"] for e in response.json()["entries"]}


def test_ordinary_users_cannot_list_server_folders(client, tree):
    response = client.get("/v1/fs/browse", params={"path": str(tree)}, headers=client.user)
    assert response.status_code == 403


def test_signed_out_visitors_get_a_401(client, tree):
    assert client.get("/v1/fs/browse", params={"path": str(tree)}).status_code == 401


def test_errors_carry_their_message(client, tree):
    response = client.get(
        "/v1/fs/browse", params={"path": str(tree / "nope")}, headers=client.admin
    )
    assert response.status_code == 422 and "not a folder" in response.json()["detail"]
