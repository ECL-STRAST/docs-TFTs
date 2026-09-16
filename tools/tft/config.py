"""Where the tool reads and writes, resolved once per run."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import BadValue, ConfigError

CONFIG_FILE = "tft.toml"
DEFAULT_PRIVATE = "../docs-TFTs-private"
WORK_DIR = ".work"


@dataclass(frozen=True)
class Config:
    root: Path      # the public repo
    private: Path   # the private repo checkout holding LaTeX sources
    work: Path      # scratch clones, gitignored


def load(root: Path) -> Config:
    """Read tft.toml if present, otherwise fall back to the sibling repo."""
    private = _private_path(root)

    return Config(root=root, private=private, work=root / WORK_DIR)


def _private_path(root: Path) -> Path:
    raw = _read_toml(root).get("paths", {}).get("private", DEFAULT_PRIVATE)

    if not isinstance(raw, str):
        raise BadValue(f"paths.private must be a string, got {type(raw).__name__}")

    # An absolute override is taken as given; anything else hangs off the repo.
    path = Path(raw)

    return path if path.is_absolute() else (root / path).resolve()


def _read_toml(root: Path) -> dict:
    path = root / CONFIG_FILE

    if not path.exists():
        return {}

    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
