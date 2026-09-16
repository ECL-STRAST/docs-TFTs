import json
import re
from pathlib import Path

import yaml

from tft import config
from tft.catalog import Catalog
from tft.site import Site

APP_JS = Path(__file__).parent.parent / "tools" / "tft" / "assets" / "app.js"

MINIMAL = {
    "type": "thesis",
    "title": "A database for biomechanical data",
    "author": "Silvia Nieves Serrano",
    "year": 2027,
    "degree": "bachelor",
    "topics": ["biomechanics"],
    "language": "en",
}


def _fields_read_by(source: str) -> set[str]:
    return set(re.findall(r"\be\.([a-z_]+)", source))


def test_app_reads_only_fields_the_record_provides(tmp_path):
    (tmp_path / "taxonomy").mkdir()
    (tmp_path / "taxonomy" / "topics.yaml").write_text(yaml.safe_dump(["biomechanics"]))
    folder = tmp_path / "content" / "theses" / "2027-x"
    folder.mkdir(parents=True)
    (folder / "entry.yaml").write_text(yaml.safe_dump(MINIMAL, sort_keys=False))
    (folder / "summary.md").write_text("Text.\n")
    (folder / "thesis.pdf").write_bytes(b"%PDF-1.4\n")

    cfg = config.load(tmp_path)
    Site(cfg, Catalog(cfg)).build(tmp_path / "site")
    record = json.loads((tmp_path / "site" / "index.json").read_text())[0]

    assert _fields_read_by(APP_JS.read_text()) <= set(record)


def test_app_binds_every_filter_control():
    source = APP_JS.read_text()

    for control in ["q", "year", "degree", "topic", "code", "slides"]:
        assert f'"{control}"' in source or f"'{control}'" in source


def test_app_escapes_interpolated_text():
    # Titles and summaries are authored content; they must never be raw HTML.
    assert "escape" in APP_JS.read_text()
