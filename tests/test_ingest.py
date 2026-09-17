import shutil

import pytest
import yaml

from tft import config
from tft.catalog import Catalog
from tft.errors import CompileError
from tft.ingest import Ingest

PROJECT = "698b41fa174f9aec00db94cb"
SHA = "a3f19c2000000000000000000000000000000000"


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "public" / "taxonomy").mkdir(parents=True)
    (tmp_path / "public" / "taxonomy" / "topics.yaml").write_text(yaml.safe_dump(["vr"]))
    (tmp_path / "public" / "tft.toml").write_text(
        f'[paths]\nprivate = "{tmp_path / "private"}"\n'
    )

    return tmp_path / "public"


def _ingest(repo, sha=SHA, fail=False):
    """An Ingest whose drivers are stubbed: no network, no TeX."""
    def fetch(project_id, dest):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "main.tex").write_text("\\documentclass{article}\n\\begin{document}x\\end{document}\n")
        (dest / "figure.png").write_bytes(b"png")
        return sha

    def build(src, main, out):
        if fail:
            raise CompileError("boom")
        out.mkdir(parents=True, exist_ok=True)
        pdf = out / "main.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        return pdf

    cfg = config.load(repo)

    return Ingest(cfg, Catalog(cfg), fetch=fetch, build=build)


def _add(repo, ingest):
    return ingest.add(
        project_id=PROJECT, slug="2027-nieves-serrano-biomechanics-db", year=2027,
        title="A database for biomechanical data", author="Silvia Nieves Serrano",
        degree="bachelor",
    )


def test_add_installs_pdf_and_stubs(repo):
    folder = _add(repo, _ingest(repo))

    assert (folder / "thesis.pdf").read_bytes().startswith(b"%PDF")
    assert (folder / "summary.md").is_file()


def test_add_records_project_and_commit(repo):
    folder = _add(repo, _ingest(repo))

    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert data["overleaf"]["project_id"] == PROJECT
    assert data["overleaf"]["commit"] == SHA


def test_add_mirrors_sources_without_git(repo):
    _add(repo, _ingest(repo))

    mirror = repo.parent / "private" / "sources" / "theses" / "2027-nieves-serrano-biomechanics-db"

    assert (mirror / "main.tex").is_file()
    assert (mirror / "figure.png").is_file()
    assert not (mirror / ".git").exists()


def test_recorded_mirror_is_a_url_not_a_local_path(repo):
    folder = _add(repo, _ingest(repo))

    data = yaml.safe_load((folder / "entry.yaml").read_text())
    expected = (
        f"{config.DEFAULT_MIRROR_BASE}/theses/2027-nieves-serrano-biomechanics-db"
    )

    assert data["overleaf"]["mirror"] == expected


def test_mirror_base_override_is_honoured(repo):
    (repo / "tft.toml").write_text(
        (repo / "tft.toml").read_text() + 'mirror_base = "https://example.org/sources"\n'
    )

    folder = _add(repo, _ingest(repo))

    data = yaml.safe_load((folder / "entry.yaml").read_text())
    assert data["overleaf"]["mirror"] == (
        "https://example.org/sources/theses/2027-nieves-serrano-biomechanics-db"
    )

    # The actual files still land at the local private-repo path.
    mirror_dir = repo.parent / "private" / "sources" / "theses" / "2027-nieves-serrano-biomechanics-db"
    assert (mirror_dir / "main.tex").is_file()


def test_add_leaves_nothing_behind_when_the_compile_fails(repo):
    with pytest.raises(CompileError):
        _add(repo, _ingest(repo, fail=True))

    assert not (repo / "content" / "theses" / "2027-nieves-serrano-biomechanics-db").exists()


def test_sync_is_a_no_op_at_the_same_sha(repo):
    _add(repo, _ingest(repo))

    assert _ingest(repo).sync("2027-nieves-serrano-biomechanics-db") is False


def test_sync_refreshes_pdf_and_sha(repo):
    folder = _add(repo, _ingest(repo))
    later = "b" * 40

    assert _ingest(repo, sha=later).sync("2027-nieves-serrano-biomechanics-db") is True

    data = yaml.safe_load((folder / "entry.yaml").read_text())
    assert data["overleaf"]["commit"] == later


def test_failed_sync_keeps_the_previous_pdf(repo):
    folder = _add(repo, _ingest(repo))
    (folder / "thesis.pdf").write_bytes(b"%PDF-original\n")

    with pytest.raises(CompileError):
        _ingest(repo, sha="c" * 40, fail=True).sync("2027-nieves-serrano-biomechanics-db")

    assert (folder / "thesis.pdf").read_bytes() == b"%PDF-original\n"


def test_failed_mirror_keeps_the_pdf_and_yaml(repo):
    """A mirror failure must not leave folder/entry.yaml disagreeing."""
    folder = _add(repo, _ingest(repo))
    (folder / "thesis.pdf").write_bytes(b"%PDF-original\n")

    # Replace the private checkout with a file: _mirror's mkdir then
    # fails, before either the PDF or entry.yaml can be touched.
    private = repo.parent / "private"
    shutil.rmtree(private)
    private.write_text("blocker")

    with pytest.raises(NotADirectoryError):
        _ingest(repo, sha="d" * 40).sync("2027-nieves-serrano-biomechanics-db")

    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert (folder / "thesis.pdf").read_bytes() == b"%PDF-original\n"
    assert data["overleaf"]["commit"] == SHA
