import json

import pytest
import yaml

from tft import config
from tft.catalog import Catalog
from tft.site import Site

MINIMAL = {
    "type": "thesis",
    "title": "A database for biomechanical data",
    "author": "Silvia Nieves Serrano",
    "year": 2027,
    "degree": "bachelor",
    "topics": ["biomechanics"],
    "language": "en",
}

FULL = MINIMAL | {
    "supervisors": ["Rodrigo Garcia Carmona"],
    "topics": ["biomechanics", "rehabilitation"],
    "repos": {
        "code": ["https://github.com/ECL-STRAST/libremotion-chloe"],
        "docs": "https://github.com/ECL-STRAST/libremotion-chloe-docs",
    },
    "slides": "slides.pdf",
}


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "taxonomy").mkdir()
    (tmp_path / "taxonomy" / "topics.yaml").write_text(
        yaml.safe_dump(["biomechanics", "rehabilitation"])
    )

    return tmp_path


def _entry(repo, slug, data, summary="Stores **gait** data.\n"):
    folder = repo / "content" / "theses" / slug
    folder.mkdir(parents=True)
    (folder / "entry.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    (folder / "summary.md").write_text(summary)
    (folder / "thesis.pdf").write_bytes(b"%PDF-1.4\n")

    if data.get("slides"):
        (folder / data["slides"]).write_bytes(b"%PDF-slides\n")

    return folder


def _build(repo):
    cfg = config.load(repo)
    out = repo / "site"
    Site(cfg, Catalog(cfg)).build(out)

    return out


def test_index_json_matches_the_golden_record(repo):
    _entry(repo, "2027-nieves-serrano-biomechanics-db", FULL)

    out = _build(repo)
    records = json.loads((out / "index.json").read_text())

    assert records == [{
        "slug": "2027-nieves-serrano-biomechanics-db",
        "type": "thesis",
        "title": "A database for biomechanical data",
        "author": "Silvia Nieves Serrano",
        "year": 2027,
        "degree": "bachelor",
        "language": "en",
        "topics": ["biomechanics", "rehabilitation"],
        "supervisors": ["Rodrigo Garcia Carmona"],
        "url": "entries/2027-nieves-serrano-biomechanics-db/",
        "doc": "entries/2027-nieves-serrano-biomechanics-db/thesis.pdf",
        "slides": "entries/2027-nieves-serrano-biomechanics-db/slides.pdf",
        "has_code": True,
        "has_slides": True,
        "summary": "Stores gait data.",
    }]


def test_unfinished_entry_has_false_flags(repo):
    _entry(repo, "2027-x", MINIMAL)

    records = json.loads((_build(repo) / "index.json").read_text())

    assert records[0]["has_code"] is False
    assert records[0]["has_slides"] is False
    assert records[0]["slides"] is None


def test_documents_are_copied_next_to_the_page(repo):
    _entry(repo, "2027-x", FULL)

    out = _build(repo)

    assert (out / "entries" / "2027-x" / "thesis.pdf").read_bytes().startswith(b"%PDF")
    assert (out / "entries" / "2027-x" / "slides.pdf").is_file()


def test_entry_page_renders_summary_markdown(repo):
    _entry(repo, "2027-x", FULL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert "<strong>gait</strong>" in page
    assert "libremotion-chloe" in page


def test_index_page_ships_the_assets(repo):
    _entry(repo, "2027-x", MINIMAL)

    out = _build(repo)

    assert (out / "index.html").is_file()
    assert (out / "assets" / "style.css").is_file()


def test_build_replaces_a_previous_run(repo):
    _entry(repo, "2027-x", MINIMAL)
    out = _build(repo)
    (out / "stale.html").write_text("old")

    _build(repo)

    assert not (out / "stale.html").exists()
