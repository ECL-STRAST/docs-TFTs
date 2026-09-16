import pytest
import yaml

from tft import cli

MINIMAL = {
    "type": "thesis",
    "title": "A database for biomechanical data",
    "author": "Silvia Nieves Serrano",
    "year": 2027,
    "degree": "bachelor",
    "topics": ["biomechanics"],
    "language": "en",
}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'tft'\n")
    (tmp_path / "taxonomy").mkdir()
    (tmp_path / "taxonomy" / "topics.yaml").write_text(yaml.safe_dump(["biomechanics"]))
    monkeypatch.chdir(tmp_path)

    return tmp_path


def _entry(repo, slug, data=None, doc=True):
    folder = repo / "content" / "theses" / slug
    folder.mkdir(parents=True)
    (folder / "entry.yaml").write_text(yaml.safe_dump(data or MINIMAL, sort_keys=False))
    (folder / "summary.md").write_text("Text.\n")

    if doc:
        (folder / "thesis.pdf").write_bytes(b"%PDF-1.4\n")

    return folder


def test_find_root_walks_up(repo):
    nested = repo / "content" / "theses"
    nested.mkdir(parents=True)

    assert cli.find_root(nested) == repo


def test_validate_succeeds_on_a_sound_catalog(repo, capsys):
    _entry(repo, "2027-x")

    assert cli.main(["validate"]) == 0
    assert "ok" in capsys.readouterr().out


def test_validate_fails_and_lists_problems(repo, capsys):
    _entry(repo, "2027-x", doc=False)

    assert cli.main(["validate"]) == 1
    assert "thesis.pdf" in capsys.readouterr().out


def test_add_reports_a_missing_token(repo, monkeypatch, capsys):
    monkeypatch.delenv("OVERLEAF_GIT_TOKEN", raising=False)

    code = cli.main([
        "add", "--overleaf", "abc", "--name", "nieves-serrano-biomechanics-db",
        "--year", "2027", "--title", "T", "--author", "A",
    ])

    assert code == 1
    assert "OVERLEAF_GIT_TOKEN" in capsys.readouterr().err


def test_add_builds_the_slug_from_year_and_name(repo, monkeypatch):
    seen = {}

    def fake_add(self, project_id, slug, year, title, author, type="thesis", degree=None):
        seen["slug"] = slug
        return repo

    monkeypatch.setattr("tft.ingest.Ingest.add", fake_add)

    code = cli.main([
        "add", "--overleaf", "abc", "--name", "nieves-serrano-biomechanics-db",
        "--year", "2027", "--title", "T", "--author", "A",
    ])

    assert code == 0
    assert seen["slug"] == "2027-nieves-serrano-biomechanics-db"


def test_sync_reports_no_change(repo, monkeypatch, capsys):
    _entry(repo, "2027-x")
    monkeypatch.setattr("tft.ingest.Ingest.sync", lambda self, slug: False)

    assert cli.main(["sync", "2027-x"]) == 0
    assert "unchanged" in capsys.readouterr().out
