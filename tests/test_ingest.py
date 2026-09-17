import shutil

import pytest
import yaml

from tft import config
from tft.catalog import Catalog
from tft.errors import CompileError, ExtractError
from tft.ingest import Ingest, Overrides

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


MAIN = r"""
\newcommand{\authorname}{Silvia Nieves Serrano}
\newcommand{\tfgtitle}{A database for biomechanical data}
\newcommand{\fecha}{Junio 2027}
TRABAJO FIN DE GRADO
\documentclass{article}
\begin{document}x\end{document}
"""

ABSTRACT = r"""
\chapter*{Abstract}
\addcontentsline{toc}{chapter}{Abstract}
This thesis presents a \textbf{database} for biomechanical data.

\vfill
\textbf{Keywords:} biomechanics, Databases.
"""


def _ingest(repo, sha=SHA, fail=False, main=MAIN, abstract=ABSTRACT):
    """An Ingest whose drivers are stubbed: no network, no TeX."""
    def fetch(project_id, dest):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "main.tex").write_text(main)
        (dest / "figure.png").write_bytes(b"png")

        if abstract is not None:
            (dest / "abstract.tex").write_text(abstract)

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
    return ingest.add(project_id=PROJECT, name="nieves-serrano-biomechanics-db")


def test_add_derives_the_slug_from_the_extracted_year(repo):
    folder = _add(repo, _ingest(repo))

    assert folder.name == "2027-nieves-serrano-biomechanics-db"


def test_add_fills_entry_yaml_from_the_source(repo):
    folder = _add(repo, _ingest(repo))
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert data["title"] == "A database for biomechanical data"
    assert data["author"] == "Silvia Nieves Serrano"
    assert data["year"] == 2027
    assert data["degree"] == "bachelor"
    assert data["keywords"] == ["biomechanics", "databases"]


def test_add_writes_the_abstract_as_the_summary(repo):
    folder = _add(repo, _ingest(repo))

    assert (folder / "summary.md").read_text().startswith(
        "This thesis presents a database for biomechanical data."
    )


def test_missing_metadata_names_the_field(repo):
    bare = "\\documentclass{article}\\begin{document}x\\end{document}"

    with pytest.raises(ExtractError, match="title"):
        _add(repo, _ingest(repo, main=bare, abstract=None))


def test_override_supplies_a_missing_field(repo):
    main = MAIN.replace(r"\newcommand{\tfgtitle}{A database for biomechanical data}", "")
    ingest = _ingest(repo, main=main)

    folder = ingest.add(
        project_id=PROJECT, name="nieves-serrano-biomechanics-db",
        overrides=Overrides(title="Supplied by hand"),
    )
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert data["title"] == "Supplied by hand"


def test_override_beats_the_source(repo):
    folder = _ingest(repo).add(
        project_id=PROJECT, name="x", overrides=Overrides(year=2030),
    )

    assert folder.name == "2030-x"


def test_extraction_failure_leaves_no_entry(repo):
    bare = "\\documentclass{article}\\begin{document}x\\end{document}"

    with pytest.raises(ExtractError):
        _add(repo, _ingest(repo, main=bare, abstract=None))

    assert not (repo / "content" / "theses").exists() or \
        list((repo / "content" / "theses").iterdir()) == []


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


def test_failed_copy_leaves_no_tmp_residue(repo, monkeypatch):
    """A copy failure must not leave the .tmp sibling behind."""
    folder = _add(repo, _ingest(repo))
    (folder / "thesis.pdf").write_bytes(b"%PDF-original\n")

    real_copyfile = shutil.copyfile

    def broken_copy(src, dst, *args, **kwargs):
        # Only the final PDF copy must fail; the source mirror (which also
        # uses copyfile, via copytree) must proceed normally.
        if str(dst).endswith(".tmp"):
            raise OSError("disk full")
        return real_copyfile(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", broken_copy)

    with pytest.raises(OSError):
        _ingest(repo, sha="e" * 40).sync("2027-nieves-serrano-biomechanics-db")

    assert (folder / "thesis.pdf").read_bytes() == b"%PDF-original\n"
    assert not any(folder.glob("*.tmp"))
