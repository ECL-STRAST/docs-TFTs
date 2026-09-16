import pytest
from pathlib import Path

from tft import config
from tft.errors import BadValue


def test_defaults_to_sibling_private_repo(tmp_path):
    cfg = config.load(tmp_path)

    assert cfg.root == tmp_path
    assert cfg.private == (tmp_path / ".." / "docs-TFTs-private").resolve()
    assert cfg.work == tmp_path / ".work"


def test_toml_overrides_private_path(tmp_path):
    (tmp_path / "tft.toml").write_text('[paths]\nprivate = "/srv/private"\n')

    cfg = config.load(tmp_path)

    assert cfg.private == Path("/srv/private")


def test_relative_override_resolves_against_root(tmp_path):
    (tmp_path / "tft.toml").write_text('[paths]\nprivate = "sibling"\n')

    cfg = config.load(tmp_path)

    assert cfg.private == (tmp_path / "sibling").resolve()


def test_non_string_private_path_is_rejected(tmp_path):
    (tmp_path / "tft.toml").write_text("[paths]\nprivate = 7\n")

    with pytest.raises(BadValue):
        config.load(tmp_path)
