# Thesis catalog implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `tft` Python package and the repository scaffolding that
turn `ECL-STRAST/docs-TFTs` into a browsable catalog of the group's theses,
published as a static GitHub Pages site.

**Architecture:** One Python package in strict layers — a CLI over three
services (catalog, ingest, site) over three drivers (overleaf/git,
latex/latexmk, store/filesystem+yaml). Ingest is a local, human-run step that
clones an Overleaf project and compiles it; CI only validates the catalog and
renders the site from files already committed, so CI holds no secrets.

**Tech Stack:** Python 3.11+, PyYAML, Jinja2, markdown, pytest, vanilla
JavaScript, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-16-thesis-catalog-design.md`

## Global Constraints

- Python `>=3.11` (the config loader relies on stdlib `tomllib`).
- Runtime dependencies are exactly `PyYAML>=6`, `Jinja2>=3.1`,
  `markdown>=3.5`. Test dependency is exactly `pytest>=8`. Adding any other
  dependency is a spec change, not an implementation decision.
- `OVERLEAF_GIT_TOKEN` is read from the environment only. It is never
  written to disk, never passed on a command line, and every error message
  crossing a layer boundary is scrubbed of it.
- No test may touch the network. Git is exercised against local throwaway
  repositories; `latexmk` is stubbed except in one integration test that is
  skipped when the binary is absent.
- Layer rule: `cli.py` calls services, services call drivers, drivers call
  the outside world. No module imports from a layer above itself. Peer calls
  between services are allowed by dependency injection only.
- All prose the catalog renders is English.
- Names of classes, functions and methods are under 30 characters.
- Module-private helpers are prefixed with `_`. A name becomes public only
  when another module needs it.
- Every entry folder is named `<year>-<slug>`; the human supplies `<slug>`
  and the convention is `<surname>-<topic>`. The tool never parses a
  person's name into a surname.
- Mandatory entry fields: `type`, `title`, `author`, `year`, `topics`,
  `language`, plus `degree` when `type` is `thesis`. Everything else is
  optional, because entries may be added before the work is finished.

---

### Task 1: Package scaffold, errors and config

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `tools/tft/__init__.py`
- Create: `tools/tft/errors.py`
- Create: `tools/tft/config.py`
- Create: `tft.toml.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `tft.errors.TftError` and subclasses `ConfigError`, `SchemaError`,
    `MissingField(SchemaError)`, `BadValue(SchemaError)`,
    `UnknownField(SchemaError)`, `UnknownTopic(SchemaError)`,
    `OverleafError`, `CompileError`.
  - `tft.config.Config` — frozen dataclass with `root: Path`,
    `private: Path`, `work: Path`.
  - `tft.config.load(root: Path) -> Config`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tft'`

- [ ] **Step 3: Write the package scaffold and the implementation**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "tft"
version = "0.1.0"
description = "Catalog tooling for the group's theses and publications"
requires-python = ">=3.11"
dependencies = ["PyYAML>=6", "Jinja2>=3.1", "markdown>=3.5"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
tft = "tft.cli:main"

[tool.setuptools.packages.find]
where = ["tools"]

[tool.setuptools.package-data]
tft = ["templates/*", "assets/*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

```gitignore
# .gitignore
site/
.work/
.env
tft.toml
__pycache__/
*.egg-info/
.pytest_cache/
```

```python
# tools/tft/__init__.py
"""Catalog tooling for the group's theses and publications."""
```

```python
# tools/tft/errors.py
"""Every failure the tool reports, one class per cause."""


class TftError(Exception):
    """Base for anything this tool raises."""


class ConfigError(TftError):
    """tft.toml is unreadable or malformed."""


class SchemaError(TftError):
    """An entry.yaml violates the schema."""


class MissingField(SchemaError):
    """A mandatory field is absent."""


class UnknownField(SchemaError):
    """A field not in the schema is present, usually a typo."""


class BadValue(SchemaError):
    """A field is present but its value is of the wrong type or domain."""


class UnknownTopic(SchemaError):
    """A topic is not listed in taxonomy/topics.yaml."""


class OverleafError(TftError):
    """Cloning or pulling the Overleaf project failed."""


class CompileError(TftError):
    """The document could not be compiled."""
```

```python
# tools/tft/config.py
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
```

```toml
# tft.toml.example
# Copy to tft.toml (gitignored) when the private repo is not the sibling
# directory ../docs-TFTs-private.
[paths]
private = "../docs-TFTs-private"
```

- [ ] **Step 4: Install the package and run the test to verify it passes**

Run: `python -m pip install -e ".[dev]" && python -m pytest tests/test_config.py -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore tft.toml.example tools/tft tests/test_config.py
git commit -m "Add tft package scaffold with errors and config"
```

---

### Task 2: Entry model and schema validation

**Files:**
- Create: `tools/tft/entry.py`
- Test: `tests/test_entry.py`

**Interfaces:**
- Consumes: `tft.errors.MissingField`, `UnknownField`, `BadValue`.
- Produces:
  - Constants `THESIS = "thesis"`, `PUBLICATION = "publication"`,
    `TYPES`, `DEGREES = ("bachelor", "master", "phd")`, `DOC_NAME`
    (a dict mapping type to the document filename).
  - `tft.entry.Overleaf` — frozen dataclass `project_id: str`,
    `commit: str | None`, `main: str | None`, `mirror: str | None`.
  - `tft.entry.Repos` — frozen dataclass `code: tuple[str, ...]`,
    `docs: str | None`.
  - `tft.entry.Entry` — frozen dataclass `slug, type, title, author, year,
    topics, language, degree, venue, supervisors, overleaf, repos, slides,
    summary`.
  - `tft.entry.from_dict(slug: str, data: dict) -> Entry`.
  - `tft.entry.to_dict(entry: Entry) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_entry.py
import pytest

from tft import entry
from tft.errors import BadValue, MissingField, UnknownField

MINIMAL = {
    "type": "thesis",
    "title": "A database for biomechanical data",
    "author": "Silvia Nieves Serrano",
    "year": 2027,
    "degree": "bachelor",
    "topics": ["biomechanics"],
    "language": "en",
}


def test_minimal_entry_round_trips():
    parsed = entry.from_dict("2027-nieves-serrano-biomechanics-db", MINIMAL)

    assert parsed.slug == "2027-nieves-serrano-biomechanics-db"
    assert parsed.title == MINIMAL["title"]
    assert parsed.topics == ("biomechanics",)
    assert entry.to_dict(parsed) == MINIMAL


def test_optional_blocks_survive_the_round_trip():
    data = MINIMAL | {
        "supervisors": ["Rodrigo Garcia Carmona"],
        "overleaf": {"project_id": "698b41fa174f9aec00db94cb", "commit": "a3f19c2"},
        "repos": {"code": ["https://github.com/ECL-STRAST/libremotion-chloe"]},
        "slides": "slides.pdf",
    }

    parsed = entry.from_dict("2027-x", data)

    assert parsed.overleaf.project_id == "698b41fa174f9aec00db94cb"
    assert parsed.repos.code == ("https://github.com/ECL-STRAST/libremotion-chloe",)
    assert parsed.slides == "slides.pdf"
    assert entry.to_dict(parsed) == data


def test_unfinished_entry_is_valid():
    # No repos, no slides, no overleaf commit: the work is still in progress.
    parsed = entry.from_dict("2027-x", MINIMAL)

    assert parsed.repos.code == ()
    assert parsed.slides is None
    assert parsed.overleaf is None


@pytest.mark.parametrize("field", ["type", "title", "author", "year", "topics", "language"])
def test_missing_mandatory_field(field):
    data = {k: v for k, v in MINIMAL.items() if k != field}

    with pytest.raises(MissingField, match=field):
        entry.from_dict("2027-x", data)


def test_thesis_requires_a_degree():
    data = {k: v for k, v in MINIMAL.items() if k != "degree"}

    with pytest.raises(MissingField, match="degree"):
        entry.from_dict("2027-x", data)


def test_publication_does_not_require_a_degree():
    data = {k: v for k, v in MINIMAL.items() if k != "degree"} | {"type": "publication"}

    assert entry.from_dict("2027-x", data).degree is None


def test_unknown_field_is_rejected():
    with pytest.raises(UnknownField, match="titel"):
        entry.from_dict("2027-x", MINIMAL | {"titel": "typo"})


def test_unknown_type_is_rejected():
    with pytest.raises(BadValue, match="type"):
        entry.from_dict("2027-x", MINIMAL | {"type": "poster"})


def test_unknown_degree_is_rejected():
    with pytest.raises(BadValue, match="degree"):
        entry.from_dict("2027-x", MINIMAL | {"degree": "postdoc"})


def test_year_must_be_an_integer():
    with pytest.raises(BadValue, match="year"):
        entry.from_dict("2027-x", MINIMAL | {"year": "2027"})


def test_topics_must_not_be_empty():
    with pytest.raises(BadValue, match="topics"):
        entry.from_dict("2027-x", MINIMAL | {"topics": []})


def test_doc_name_per_type():
    assert entry.DOC_NAME["thesis"] == "thesis.pdf"
    assert entry.DOC_NAME["publication"] == "paper.pdf"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_entry.py -v`
Expected: FAIL with `ImportError: cannot import name 'entry' from 'tft'`

- [ ] **Step 3: Write the implementation**

```python
# tools/tft/entry.py
"""The catalog's domain type and the rules an entry.yaml must satisfy."""

from dataclasses import dataclass, field
from typing import Any

from .errors import BadValue, MissingField, UnknownField

THESIS = "thesis"
PUBLICATION = "publication"
TYPES = (THESIS, PUBLICATION)

DEGREES = ("bachelor", "master", "phd")

DOC_NAME = {THESIS: "thesis.pdf", PUBLICATION: "paper.pdf"}

MANDATORY = ("type", "title", "author", "year", "topics", "language")
OPTIONAL = ("degree", "venue", "supervisors", "overleaf", "repos", "slides")

TEXT_FIELDS = ("title", "author", "language")


@dataclass(frozen=True)
class Overleaf:
    project_id: str
    commit: str | None = None
    main: str | None = None     # only when root-file detection is ambiguous
    mirror: str | None = None   # URL of the source mirror in the private repo


@dataclass(frozen=True)
class Repos:
    code: tuple[str, ...] = ()
    docs: str | None = None


@dataclass(frozen=True)
class Entry:
    slug: str
    type: str
    title: str
    author: str
    year: int
    topics: tuple[str, ...]
    language: str
    degree: str | None = None
    venue: str | None = None
    supervisors: tuple[str, ...] = ()
    overleaf: Overleaf | None = None
    repos: Repos = field(default_factory=Repos)
    slides: str | None = None
    summary: str = ""   # summary.md's body, attached by the store


def from_dict(slug: str, data: dict) -> Entry:
    """Parse and validate one entry.yaml. Raises a SchemaError subclass."""
    _reject_unknown(data)
    _require(data, MANDATORY)

    kind = _one_of(data, "type", TYPES)

    # A thesis has a degree; a publication will have a venue instead.
    if kind == THESIS:
        _require(data, ("degree",))
        _one_of(data, "degree", DEGREES)

    _check_types(data)

    return Entry(
        slug=slug,
        type=kind,
        title=data["title"],
        author=data["author"],
        year=data["year"],
        topics=tuple(data["topics"]),
        language=data["language"],
        degree=data.get("degree"),
        venue=data.get("venue"),
        supervisors=tuple(data.get("supervisors", ())),
        overleaf=_overleaf(data.get("overleaf")),
        repos=_repos(data.get("repos")),
        slides=data.get("slides"),
    )


def to_dict(entry: Entry) -> dict:
    """Serialise back to the entry.yaml shape, omitting what is unset."""
    out: dict[str, Any] = {
        "type": entry.type,
        "title": entry.title,
        "author": entry.author,
        "year": entry.year,
    }

    _put(out, "degree", entry.degree)
    _put(out, "venue", entry.venue)
    _put(out, "supervisors", list(entry.supervisors))

    out["topics"] = list(entry.topics)
    out["language"] = entry.language

    if entry.overleaf is not None:
        out["overleaf"] = _put_all(
            project_id=entry.overleaf.project_id,
            commit=entry.overleaf.commit,
            main=entry.overleaf.main,
            mirror=entry.overleaf.mirror,
        )

    repos = _put_all(code=list(entry.repos.code), docs=entry.repos.docs)
    _put(out, "repos", repos)
    _put(out, "slides", entry.slides)

    return out


def _reject_unknown(data: dict) -> None:
    for key in data:
        if key not in MANDATORY and key not in OPTIONAL:
            raise UnknownField(f"unknown field: {key}")


def _require(data: dict, names: tuple[str, ...]) -> None:
    for name in names:
        if name not in data:
            raise MissingField(f"missing field: {name}")


def _one_of(data: dict, name: str, allowed: tuple[str, ...]) -> str:
    value = data[name]

    if value not in allowed:
        raise BadValue(f"{name} must be one of {', '.join(allowed)}, got {value!r}")

    return value


def _check_types(data: dict) -> None:
    if not isinstance(data["year"], int):
        raise BadValue("year must be an integer")

    for name in TEXT_FIELDS:
        if not isinstance(data[name], str) or not data[name].strip():
            raise BadValue(f"{name} must be a non-empty string")

    topics = data["topics"]

    if not isinstance(topics, list) or not topics:
        raise BadValue("topics must be a non-empty list")


def _overleaf(raw: dict | None) -> Overleaf | None:
    if raw is None:
        return None

    if "project_id" not in raw:
        raise MissingField("missing field: overleaf.project_id")

    return Overleaf(
        project_id=raw["project_id"],
        commit=raw.get("commit"),
        main=raw.get("main"),
        mirror=raw.get("mirror"),
    )


def _repos(raw: dict | None) -> Repos:
    if raw is None:
        return Repos()

    return Repos(code=tuple(raw.get("code", ())), docs=raw.get("docs"))


def _put(out: dict, name: str, value: Any) -> None:
    if value:
        out[name] = value


def _put_all(**values: Any) -> dict:
    return {name: value for name, value in values.items() if value}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_entry.py -v`
Expected: PASS, 16 tests

- [ ] **Step 5: Commit**

```bash
git add tools/tft/entry.py tests/test_entry.py
git commit -m "Add entry model and schema validation"
```

---

### Task 3: Store driver

**Files:**
- Create: `tools/tft/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `tft.entry.Entry`, `from_dict`, `to_dict`; `tft.errors.ConfigError`.
- Produces:
  - Constants `ENTRY_FILE = "entry.yaml"`, `SUMMARY_FILE = "summary.md"`.
  - `tft.store.read(dir: Path) -> Entry` — slug is the directory name, and
    `summary.md` is loaded into `Entry.summary` (empty string when absent).
  - `tft.store.write(dir: Path, entry: Entry) -> None` — writes `entry.yaml`
    only; never touches `summary.md`.
  - `tft.store.write_summary(dir: Path, text: str) -> None`.
  - `tft.store.dirs(parent: Path) -> list[Path]` — entry directories under
    `parent`, sorted, skipping anything without an `entry.yaml`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store.py
import pytest
import yaml

from tft import entry, store
from tft.errors import SchemaError

MINIMAL = {
    "type": "thesis",
    "title": "A database for biomechanical data",
    "author": "Silvia Nieves Serrano",
    "year": 2027,
    "degree": "bachelor",
    "topics": ["biomechanics"],
    "language": "en",
}


def _make(tmp_path, slug, data=None, summary=None):
    folder = tmp_path / slug
    folder.mkdir(parents=True)
    (folder / store.ENTRY_FILE).write_text(yaml.safe_dump(data or MINIMAL, sort_keys=False))

    if summary is not None:
        (folder / store.SUMMARY_FILE).write_text(summary)

    return folder


def test_reads_slug_from_the_directory_name(tmp_path):
    folder = _make(tmp_path, "2027-nieves-serrano-biomechanics-db")

    assert store.read(folder).slug == "2027-nieves-serrano-biomechanics-db"


def test_reads_summary_into_the_entry(tmp_path):
    folder = _make(tmp_path, "2027-x", summary="Stores gait data.\n")

    assert store.read(folder).summary == "Stores gait data.\n"


def test_missing_summary_is_empty_not_an_error(tmp_path):
    folder = _make(tmp_path, "2027-x")

    assert store.read(folder).summary == ""


def test_write_then_read_round_trips(tmp_path):
    folder = tmp_path / "2027-x"
    folder.mkdir()
    original = entry.from_dict("2027-x", MINIMAL | {"slides": "slides.pdf"})

    store.write(folder, original)

    assert store.read(folder) == original


def test_write_does_not_touch_the_summary(tmp_path):
    folder = _make(tmp_path, "2027-x", summary="Hand written.\n")
    parsed = store.read(folder)

    store.write(folder, parsed)

    assert (folder / store.SUMMARY_FILE).read_text() == "Hand written.\n"


def test_invalid_entry_reports_the_file(tmp_path):
    folder = _make(tmp_path, "2027-x", data={"type": "thesis"})

    with pytest.raises(SchemaError, match="2027-x"):
        store.read(folder)


def test_dirs_lists_only_entry_folders(tmp_path):
    _make(tmp_path, "2027-b")
    _make(tmp_path, "2025-a")
    (tmp_path / "not-an-entry").mkdir()

    assert [d.name for d in store.dirs(tmp_path)] == ["2025-a", "2027-b"]


def test_dirs_on_a_missing_parent_is_empty(tmp_path):
    assert store.dirs(tmp_path / "nope") == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL with `ImportError: cannot import name 'store' from 'tft'`

- [ ] **Step 3: Write the implementation**

```python
# tools/tft/store.py
"""Reads and writes entry folders. The only module that knows about YAML."""

import dataclasses
from pathlib import Path

import yaml

from . import entry as model
from .entry import Entry
from .errors import ConfigError, SchemaError

ENTRY_FILE = "entry.yaml"
SUMMARY_FILE = "summary.md"


def read(dir: Path) -> Entry:
    """Load one entry folder. The directory name is the slug."""
    path = dir / ENTRY_FILE

    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: {exc}") from exc

    try:
        parsed = model.from_dict(dir.name, data)
    except SchemaError as exc:
        # Re-raise the same class so callers can still discriminate the cause.
        raise type(exc)(f"{path}: {exc}") from exc

    return dataclasses.replace(parsed, summary=_summary(dir))


def write(dir: Path, entry: Entry) -> None:
    """Write entry.yaml. summary.md is hand written and never overwritten."""
    dir.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(model.to_dict(entry), sort_keys=False, allow_unicode=True)
    (dir / ENTRY_FILE).write_text(text)


def write_summary(dir: Path, text: str) -> None:
    dir.mkdir(parents=True, exist_ok=True)
    (dir / SUMMARY_FILE).write_text(text)


def dirs(parent: Path) -> list[Path]:
    """Entry folders under parent, sorted by slug."""
    if not parent.is_dir():
        return []

    return sorted(d for d in parent.iterdir() if (d / ENTRY_FILE).is_file())


def _summary(dir: Path) -> str:
    path = dir / SUMMARY_FILE

    return path.read_text() if path.is_file() else ""
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_store.py -v`
Expected: PASS, 8 tests

- [ ] **Step 5: Commit**

```bash
git add tools/tft/store.py tests/test_store.py
git commit -m "Add store driver for entry folders"
```

---

### Task 4: Catalog service and topic vocabulary

**Files:**
- Create: `tools/tft/catalog.py`
- Create: `taxonomy/topics.yaml`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `tft.config.Config`, `tft.store`, `tft.entry`.
- Produces:
  - Constants `CONTENT = "content"`, `TAXONOMY = "taxonomy/topics.yaml"`,
    `COLLECTIONS = {"thesis": "theses", "publication": "publications"}`.
  - `tft.catalog.Catalog(cfg: Config)` with:
    - `entries() -> list[Entry]` — every entry, sorted by year descending
      then slug.
    - `find(slug: str) -> Entry` — raises `MissingField` when absent.
    - `dir_for(entry: Entry) -> Path`.
    - `create(slug, type, year, title, author, degree) -> Path` — scaffolds
      the folder with a stub `entry.yaml` and `summary.md`, returns the path.
    - `save(entry: Entry) -> None`.
    - `topics() -> set[str]`.
    - `problems() -> list[str]` — every validation failure as a line of
      English, empty when the catalog is sound.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_catalog.py
import pytest
import yaml

from tft import config
from tft.catalog import Catalog
from tft.errors import MissingField

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
def repo(tmp_path):
    (tmp_path / "taxonomy").mkdir()
    (tmp_path / "taxonomy" / "topics.yaml").write_text(
        yaml.safe_dump(["biomechanics", "rehabilitation", "vr"])
    )
    (tmp_path / "content" / "theses").mkdir(parents=True)

    return tmp_path


def _add(repo, slug, data=None, summary="Text.\n", doc="thesis.pdf"):
    folder = repo / "content" / "theses" / slug
    folder.mkdir(parents=True)
    (folder / "entry.yaml").write_text(yaml.safe_dump(data or MINIMAL, sort_keys=False))
    (folder / "summary.md").write_text(summary)

    if doc:
        (folder / doc).write_bytes(b"%PDF-1.4\n")

    return folder


def _catalog(repo):
    return Catalog(config.load(repo))


def test_entries_sort_newest_first(repo):
    _add(repo, "2025-old")
    _add(repo, "2027-new", data=MINIMAL | {"year": 2027})
    _add(repo, "2025-older", data=MINIMAL | {"year": 2025})

    slugs = [e.slug for e in _catalog(repo).entries()]

    assert slugs == ["2027-new", "2025-old", "2025-older"]


def test_find_returns_the_entry(repo):
    _add(repo, "2027-x")

    assert _catalog(repo).find("2027-x").title == MINIMAL["title"]


def test_find_missing_slug_raises(repo):
    with pytest.raises(MissingField, match="2027-nope"):
        _catalog(repo).find("2027-nope")


def test_create_scaffolds_a_usable_folder(repo):
    cat = _catalog(repo)

    folder = cat.create(
        slug="2027-x", type="thesis", year=2027,
        title="Untitled", author="Unknown", degree="bachelor",
    )

    assert folder == repo / "content" / "theses" / "2027-x"
    assert (folder / "summary.md").is_file()
    assert cat.find("2027-x").year == 2027


def test_create_refuses_an_existing_slug(repo):
    _add(repo, "2027-x")

    with pytest.raises(FileExistsError):
        _catalog(repo).create(
            slug="2027-x", type="thesis", year=2027,
            title="t", author="a", degree="bachelor",
        )


def test_sound_catalog_has_no_problems(repo):
    _add(repo, "2027-x")

    assert _catalog(repo).problems() == []


def test_unknown_topic_is_a_problem(repo):
    _add(repo, "2027-x", data=MINIMAL | {"topics": ["byomechanics"]})

    problems = _catalog(repo).problems()

    assert len(problems) == 1
    assert "byomechanics" in problems[0]


def test_missing_document_is_a_problem(repo):
    _add(repo, "2027-x", doc=None)

    assert any("thesis.pdf" in p for p in _catalog(repo).problems())


def test_missing_summary_is_a_problem(repo):
    folder = _add(repo, "2027-x")
    (folder / "summary.md").unlink()

    assert any("summary.md" in p for p in _catalog(repo).problems())


def test_declared_slides_must_exist(repo):
    _add(repo, "2027-x", data=MINIMAL | {"slides": "slides.pdf"})

    assert any("slides.pdf" in p for p in _catalog(repo).problems())


def test_schema_error_is_reported_not_raised(repo):
    _add(repo, "2027-x", data={"type": "thesis"})

    assert any("missing field" in p for p in _catalog(repo).problems())
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tft.catalog'`

- [ ] **Step 3: Write the vocabulary and the implementation**

```yaml
# taxonomy/topics.yaml
# The controlled vocabulary for entry topics. Adding a topic is a deliberate
# act: it is what stops near-duplicate tags such as "byomechanics".
- biomechanics
- computer-vision
- forensics
- machine-learning
- medical-training
- rehabilitation
- signal-processing
- software-engineering
- vr
```

```python
# tools/tft/catalog.py
"""The catalog as a whole: locating, listing, creating and checking entries."""

from pathlib import Path

import yaml

from . import store
from .config import Config
from .entry import DOC_NAME, Entry, from_dict
from .errors import MissingField, SchemaError

CONTENT = "content"
TAXONOMY = "taxonomy/topics.yaml"
COLLECTIONS = {"thesis": "theses", "publication": "publications"}

STUB_SUMMARY = "Replace this line with one or two paragraphs in English.\n"


class Catalog:
    def __init__(self, cfg: Config):
        self._cfg = cfg

    def entries(self) -> list[Entry]:
        """Every entry in the catalog, newest first."""
        found = []

        for collection in COLLECTIONS.values():
            found += [store.read(d) for d in store.dirs(self._content(collection))]

        return sorted(found, key=lambda e: (-e.year, e.slug))

    def find(self, slug: str) -> Entry:
        for entry in self.entries():
            if entry.slug == slug:
                return entry

        raise MissingField(f"no entry with slug {slug}")

    def dir_for(self, entry: Entry) -> Path:
        return self._content(COLLECTIONS[entry.type]) / entry.slug

    def create(self, slug, type, year, title, author, degree=None) -> Path:
        """Scaffold a new entry folder with stubs for the human to fill in."""
        folder = self._content(COLLECTIONS[type]) / slug

        if folder.exists():
            raise FileExistsError(f"{folder} already exists")

        data = {
            "type": type, "title": title, "author": author, "year": year,
            "topics": ["CHANGE-ME"], "language": "en",
        }

        if degree is not None:
            data["degree"] = degree

        store.write(folder, from_dict(slug, data))
        store.write_summary(folder, STUB_SUMMARY)

        return folder

    def save(self, entry: Entry) -> None:
        store.write(self.dir_for(entry), entry)

    def topics(self) -> set[str]:
        path = self._cfg.root / TAXONOMY

        return set(yaml.safe_load(path.read_text()) or [])

    def problems(self) -> list[str]:
        """Every reason the catalog would not publish cleanly."""
        vocabulary = self.topics()
        found = []

        for collection in COLLECTIONS.values():
            for folder in store.dirs(self._content(collection)):
                found += self._check(folder, vocabulary)

        return found

    def _check(self, folder: Path, vocabulary: set[str]) -> list[str]:
        try:
            entry = store.read(folder)
        except SchemaError as exc:
            return [str(exc)]

        found = [
            f"{folder.name}: topic not in the vocabulary: {topic}"
            for topic in entry.topics
            if topic not in vocabulary
        ]

        for name in self._required_files(entry):
            if not (folder / name).is_file():
                found.append(f"{folder.name}: missing {name}")

        return found

    def _required_files(self, entry: Entry) -> list[str]:
        names = [store.SUMMARY_FILE, DOC_NAME[entry.type]]

        # Slides are optional, but a declared file must be there.
        if entry.slides:
            names.append(entry.slides)

        return names

    def _content(self, collection: str) -> Path:
        return self._cfg.root / CONTENT / collection
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: PASS, 11 tests

- [ ] **Step 5: Commit**

```bash
git add tools/tft/catalog.py taxonomy/topics.yaml tests/test_catalog.py
git commit -m "Add catalog service and topic vocabulary"
```

---

### Task 5: Overleaf driver

**Files:**
- Create: `tools/tft/overleaf.py`
- Test: `tests/test_overleaf.py`

**Interfaces:**
- Consumes: `tft.errors.OverleafError`.
- Produces:
  - Constants `TOKEN_ENV = "OVERLEAF_GIT_TOKEN"`, `GIT_HOST = "git.overleaf.com"`.
  - `tft.overleaf.url(project_id: str, token: str) -> str`.
  - `tft.overleaf.scrub(text: str, token: str) -> str`.
  - `tft.overleaf.token() -> str` — from the environment, raises
    `OverleafError` when unset.
  - `tft.overleaf.fetch(project_id: str, dest: Path) -> str` — clones when
    `dest` is absent, pulls when it exists, returns the HEAD SHA.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_overleaf.py
import subprocess

import pytest

from tft import overleaf
from tft.errors import OverleafError

TOKEN = "olp_secret123"


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def remote(tmp_path):
    """A local git repo standing in for an Overleaf project."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git("init", "-q", "-b", "main", cwd=origin)
    (origin / "main.tex").write_text("\\documentclass{article}\n\\begin{document}x\\end{document}\n")
    _git("add", "-A", cwd=origin)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init", cwd=origin)

    return origin


def test_url_embeds_the_token():
    assert overleaf.url("abc123", TOKEN) == f"https://git:{TOKEN}@git.overleaf.com/abc123"


def test_scrub_removes_every_occurrence():
    text = f"fatal: https://git:{TOKEN}@git.overleaf.com/abc failed, token {TOKEN}"

    scrubbed = overleaf.scrub(text, TOKEN)

    assert TOKEN not in scrubbed
    assert scrubbed.count("***") == 2


def test_token_missing_from_environment(monkeypatch):
    monkeypatch.delenv(overleaf.TOKEN_ENV, raising=False)

    with pytest.raises(OverleafError, match=overleaf.TOKEN_ENV):
        overleaf.token()


def test_fetch_clones_then_pulls(tmp_path, remote, monkeypatch):
    monkeypatch.setattr(overleaf, "url", lambda project_id, token: str(remote))
    monkeypatch.setenv(overleaf.TOKEN_ENV, TOKEN)
    dest = tmp_path / "work" / "2027-x"

    first = overleaf.fetch("abc123", dest)

    assert (dest / "main.tex").is_file()
    assert len(first) == 40

    # A second call must update in place, not fail on the existing directory.
    assert overleaf.fetch("abc123", dest) == first


def test_fetch_scrubs_the_token_from_failures(tmp_path, monkeypatch):
    monkeypatch.setenv(overleaf.TOKEN_ENV, TOKEN)
    # A local path that does not exist makes git fail without any network,
    # and carries the token into the error message git prints back.
    monkeypatch.setattr(
        overleaf, "url",
        lambda project_id, token: f"{tmp_path}/missing-{token}",
    )

    with pytest.raises(OverleafError) as caught:
        overleaf.fetch("does-not-exist", tmp_path / "dest")

    assert TOKEN not in str(caught.value)
    assert "***" in str(caught.value)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_overleaf.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tft.overleaf'`

- [ ] **Step 3: Write the implementation**

```python
# tools/tft/overleaf.py
"""Talks to the Overleaf git connector. The only module that runs git."""

import os
import subprocess
from pathlib import Path

from .errors import OverleafError

TOKEN_ENV = "OVERLEAF_GIT_TOKEN"
GIT_HOST = "git.overleaf.com"
REDACTED = "***"


def token() -> str:
    """The Overleaf git token, from the environment and nowhere else."""
    value = os.environ.get(TOKEN_ENV)

    if not value:
        raise OverleafError(f"{TOKEN_ENV} is not set")

    return value


def url(project_id: str, token: str) -> str:
    return f"https://git:{token}@{GIT_HOST}/{project_id}"


def scrub(text: str, token: str) -> str:
    return text.replace(token, REDACTED)


def fetch(project_id: str, dest: Path) -> str:
    """Clone or update the project into dest. Returns the HEAD SHA."""
    secret = token()
    remote = url(project_id, secret)

    if (dest / ".git").is_dir():
        _run(["git", "pull", "--ff-only", remote], secret, cwd=dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", remote, str(dest)], secret, cwd=dest.parent)

    return _run(["git", "rev-parse", "HEAD"], secret, cwd=dest).strip()


def _run(args: list[str], secret: str, cwd: Path) -> str:
    try:
        done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise OverleafError(scrub(exc.stderr or str(exc), secret)) from None

    return done.stdout
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_overleaf.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add tools/tft/overleaf.py tests/test_overleaf.py
git commit -m "Add Overleaf git driver with token scrubbing"
```

---

### Task 6: LaTeX driver

**Files:**
- Create: `tools/tft/latex.py`
- Test: `tests/test_latex.py`

**Interfaces:**
- Consumes: `tft.errors.CompileError`.
- Produces:
  - Constants `LATEXMK = "latexmk"`, `LOG_NAME = "latexmk.log"`.
  - `tft.latex.find_main(src: Path) -> Path` — the single root `.tex`
    containing `\documentclass`; raises `CompileError` on zero or several.
  - `tft.latex.build(src: Path, main: Path, out: Path) -> Path` — returns the
    produced PDF; on failure writes the log to `out / LOG_NAME` and raises
    `CompileError`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_latex.py
import shutil

import pytest

from tft import latex
from tft.errors import CompileError

DOC = "\\documentclass{article}\n\\begin{document}\nHello.\n\\end{document}\n"


def test_find_main_picks_the_root_document(tmp_path):
    (tmp_path / "main.tex").write_text(DOC)
    (tmp_path / "chapter.tex").write_text("Just a fragment.\n")

    assert latex.find_main(tmp_path) == tmp_path / "main.tex"


def test_find_main_without_any_document(tmp_path):
    (tmp_path / "chapter.tex").write_text("Just a fragment.\n")

    with pytest.raises(CompileError, match="no root"):
        latex.find_main(tmp_path)


def test_find_main_with_several_documents(tmp_path):
    (tmp_path / "main.tex").write_text(DOC)
    (tmp_path / "poster.tex").write_text(DOC)

    with pytest.raises(CompileError, match="overleaf.main"):
        latex.find_main(tmp_path)


def test_build_failure_writes_the_log(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    out = tmp_path / "out"

    def fail(args, **kwargs):
        raise _fake_failure("! Undefined control sequence.\n")

    monkeypatch.setattr(latex.subprocess, "run", fail)

    with pytest.raises(CompileError):
        latex.build(src, src / "main.tex", out)

    assert "Undefined control sequence" in (out / latex.LOG_NAME).read_text()


def _fake_failure(output):
    import subprocess

    return subprocess.CalledProcessError(1, "latexmk", output=output, stderr="")


@pytest.mark.skipif(shutil.which("latexmk") is None, reason="latexmk not installed")
def test_build_produces_a_pdf(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.tex").write_text(DOC)
    out = tmp_path / "out"

    pdf = latex.build(src, src / "main.tex", out)

    assert pdf.is_file()
    assert pdf.read_bytes().startswith(b"%PDF")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_latex.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tft.latex'`

- [ ] **Step 3: Write the implementation**

```python
# tools/tft/latex.py
"""Compiles a LaTeX source tree. The only module that runs latexmk."""

import subprocess
from pathlib import Path

from .errors import CompileError

LATEXMK = "latexmk"
LOG_NAME = "latexmk.log"
ROOT_MARKER = "\\documentclass"


def find_main(src: Path) -> Path:
    """The root .tex at the top of the source tree."""
    roots = [p for p in sorted(src.glob("*.tex")) if ROOT_MARKER in p.read_text(errors="ignore")]

    if not roots:
        raise CompileError(f"no root .tex found in {src}")

    if len(roots) > 1:
        names = ", ".join(p.name for p in roots)
        raise CompileError(f"several root files ({names}); set overleaf.main")

    return roots[0]


def build(src: Path, main: Path, out: Path) -> Path:
    """Compile main into out. On failure the log is kept for the human."""
    out.mkdir(parents=True, exist_ok=True)
    args = [
        LATEXMK, "-pdf", "-interaction=nonstopmode", "-halt-on-error",
        f"-outdir={out}", main.name,
    ]

    try:
        subprocess.run(args, cwd=src, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise CompileError(f"{LATEXMK} is not installed") from None
    except subprocess.CalledProcessError as exc:
        (out / LOG_NAME).write_text((exc.output or "") + (exc.stderr or ""))
        raise CompileError(f"{main.name} failed to compile; see {out / LOG_NAME}") from None

    return out / f"{main.stem}.pdf"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_latex.py -v`
Expected: PASS, 4 passed and 1 skipped when `latexmk` is absent; 5 passed when installed

- [ ] **Step 5: Commit**

```bash
git add tools/tft/latex.py tests/test_latex.py
git commit -m "Add latexmk driver"
```

---

### Task 7: Ingest service

**Files:**
- Create: `tools/tft/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `tft.config.Config`, `tft.catalog.Catalog`, `tft.overleaf`,
  `tft.latex`, `tft.entry`.
- Produces:
  - Constant `SOURCES = "sources"` — the private repo's top folder.
  - `tft.ingest.Ingest(cfg, catalog, fetch=overleaf.fetch, build=latex.build)`
    — the two drivers are injected so tests can stub them.
  - `Ingest.add(project_id, slug, year, title, author, type="thesis",
    degree=None) -> Path` — fetch, compile, scaffold, install the PDF,
    mirror the sources, record the SHA. Returns the entry folder.
  - `Ingest.sync(slug) -> bool` — False when the Overleaf SHA is unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest.py
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tft.ingest'`

- [ ] **Step 3: Write the implementation**

```python
# tools/tft/ingest.py
"""Brings an Overleaf project into the catalog: fetch, compile, mirror."""

import dataclasses
import shutil
from pathlib import Path

from . import latex, overleaf
from .catalog import COLLECTIONS, Catalog
from .config import Config
from .entry import DOC_NAME, THESIS, Entry, Overleaf

SOURCES = "sources"


class Ingest:
    def __init__(self, cfg: Config, catalog: Catalog, fetch=overleaf.fetch, build=latex.build):
        self._cfg = cfg
        self._catalog = catalog
        self._fetch = fetch
        self._build = build

    def add(self, project_id, slug, year, title, author, type=THESIS, degree=None) -> Path:
        """Create a new entry from an Overleaf project."""
        work = self._cfg.work / slug
        sha = self._fetch(project_id, work)

        # Compile before scaffolding, so a broken project leaves no half entry.
        pdf = self._compile(work, main=None)

        folder = self._catalog.create(
            slug=slug, type=type, year=year, title=title, author=author, degree=degree,
        )
        entry = self._catalog.find(slug)

        self._install(entry, folder, pdf, work, sha, project_id)

        return folder

    def sync(self, slug: str) -> bool:
        """Re-pull and recompile. False when Overleaf has not moved."""
        entry = self._catalog.find(slug)

        if entry.overleaf is None:
            raise FileNotFoundError(f"{slug} has no overleaf.project_id to sync")

        work = self._cfg.work / slug
        sha = self._fetch(entry.overleaf.project_id, work)

        if sha == entry.overleaf.commit:
            return False

        pdf = self._compile(work, entry.overleaf.main)
        folder = self._catalog.dir_for(entry)

        self._install(entry, folder, pdf, work, sha, entry.overleaf.project_id)

        return True

    def _compile(self, work: Path, main: str | None) -> Path:
        root = work / main if main else latex.find_main(work)

        return self._build(work, root, self._cfg.work / "out")

    def _install(self, entry: Entry, folder: Path, pdf: Path, work: Path, sha, project_id) -> None:
        """Everything that must only happen once the compile has succeeded."""
        shutil.copyfile(pdf, folder / DOC_NAME[entry.type])

        mirror = self._mirror(entry, work)
        updated = dataclasses.replace(
            entry,
            overleaf=Overleaf(
                project_id=project_id,
                commit=sha,
                main=entry.overleaf.main if entry.overleaf else None,
                mirror=mirror,
            ),
        )

        self._catalog.save(updated)

    def _mirror(self, entry: Entry, work: Path) -> str:
        """Copy the sources into the private repo, minus git's bookkeeping."""
        dest = self._cfg.private / SOURCES / COLLECTIONS[entry.type] / entry.slug

        if dest.exists():
            shutil.rmtree(dest)

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(work, dest, ignore=shutil.ignore_patterns(".git"))

        return str(dest)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Commit**

```bash
git add tools/tft/ingest.py tests/test_ingest.py
git commit -m "Add ingest service for Overleaf projects"
```

---

### Task 8: CLI for add, sync and validate

**Files:**
- Create: `tools/tft/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `tft.config.load`, `tft.catalog.Catalog`, `tft.ingest.Ingest`.
- Produces:
  - `tft.cli.main(argv: list[str] | None = None) -> int` — exit code 0 on
    success, 1 on a `TftError` or a non-empty problem list.
  - `tft.cli.find_root(start: Path) -> Path` — the nearest ancestor holding
    `pyproject.toml`.
  - The `build` subcommand is added in Task 11.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tft.cli'`

- [ ] **Step 3: Write the implementation**

```python
# tools/tft/cli.py
"""The command line. Knows about services, never about git or latexmk."""

import argparse
import sys
from pathlib import Path

from . import config
from .catalog import Catalog
from .entry import THESIS, TYPES
from .errors import TftError
from .ingest import Ingest

ROOT_MARKER = "pyproject.toml"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    try:
        return args.run(args)
    except (TftError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def find_root(start: Path) -> Path:
    """The repository root, found by walking up from start."""
    for folder in [start, *start.parents]:
        if (folder / ROOT_MARKER).is_file():
            return folder

    raise TftError(f"no {ROOT_MARKER} above {start}")


def _catalog() -> Catalog:
    return Catalog(config.load(find_root(Path.cwd())))


def _ingest() -> Ingest:
    cfg = config.load(find_root(Path.cwd()))

    return Ingest(cfg, Catalog(cfg))


def _add(args) -> int:
    slug = f"{args.year}-{args.name}"
    folder = _ingest().add(
        project_id=args.overleaf, slug=slug, year=args.year,
        title=args.title, author=args.author, type=args.type, degree=args.degree,
    )
    print(f"created {folder}; now fill in summary.md and topics")

    return 0


def _sync(args) -> int:
    changed = _ingest().sync(args.slug)
    print(f"{args.slug}: {'updated' if changed else 'unchanged'}")

    return 0


def _validate(args) -> int:
    problems = _catalog().problems()

    for problem in problems:
        print(problem)

    if problems:
        return 1

    print("ok")

    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tft", description="Catalog tooling")
    subs = parser.add_subparsers(dest="command", required=True)

    add = subs.add_parser("add", help="add an entry from an Overleaf project")
    add.add_argument("--overleaf", required=True, metavar="ID", help="Overleaf project id")
    add.add_argument("--name", required=True, help="slug without the year, e.g. surname-topic")
    add.add_argument("--year", required=True, type=int, help="expected defence year")
    add.add_argument("--title", required=True)
    add.add_argument("--author", required=True)
    add.add_argument("--type", default=THESIS, choices=TYPES)
    add.add_argument("--degree", default="bachelor")
    add.set_defaults(run=_add)

    sync = subs.add_parser("sync", help="re-pull and recompile an entry")
    sync.add_argument("slug")
    sync.set_defaults(run=_sync)

    validate = subs.add_parser("validate", help="check every entry")
    validate.set_defaults(run=_validate)

    return parser
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add tools/tft/cli.py tests/test_cli.py
git commit -m "Add CLI for add, sync and validate"
```

---

### Task 9: Site renderer

**Files:**
- Create: `tools/tft/site.py`
- Create: `tools/tft/templates/index.html`
- Create: `tools/tft/templates/entry.html`
- Create: `tools/tft/assets/style.css`
- Test: `tests/test_site.py`
- Test fixture: `tests/fixtures/catalog/` (built by the test)

**Interfaces:**
- Consumes: `tft.config.Config`, `tft.catalog.Catalog`, `tft.entry`.
- Produces:
  - Constants `SITE = "site"`, `INDEX_JSON = "index.json"`,
    `ENTRIES = "entries"`, `ASSETS = "assets"`.
  - `tft.site.record(entry: Entry) -> dict` — the JSON shape the client
    filters over: `slug, type, title, author, year, degree, topics,
    language, supervisors, url, doc, slides, has_code, has_slides, summary`.
  - `tft.site.Site(cfg, catalog).build(out: Path) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_site.py
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_site.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tft.site'`

- [ ] **Step 3: Write the templates and the implementation**

```html
<!-- tools/tft/templates/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Theses &amp; publications</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header>
  <h1>Theses &amp; publications</h1>
  <p>{{ entries|length }} entries from the research group.</p>
</header>

<form id="filters" aria-label="Filters">
  <input type="search" id="q" placeholder="Search title, author, summary">
  <select id="year"><option value="">Any year</option>
    {% for year in years %}<option>{{ year }}</option>{% endfor %}
  </select>
  <select id="degree"><option value="">Any degree</option>
    {% for degree in degrees %}<option>{{ degree }}</option>{% endfor %}
  </select>
  <select id="topic"><option value="">Any topic</option>
    {% for topic in topics %}<option>{{ topic }}</option>{% endfor %}
  </select>
  <label><input type="checkbox" id="code"> Has code</label>
  <label><input type="checkbox" id="slides"> Has slides</label>
</form>

<p id="count" role="status"></p>
<ul id="results"></ul>

<script src="assets/app.js"></script>
</body>
</html>
```

```html
<!-- tools/tft/templates/entry.html -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ entry.title }}</title>
<link rel="stylesheet" href="../../assets/style.css">
</head>
<body>
<p><a href="../../">&larr; All entries</a></p>

<article>
  <h1>{{ entry.title }}</h1>
  <p class="meta">
    {{ entry.author }} &middot; {{ entry.year }} &middot; {{ entry.type }}
    {%- if entry.degree %} ({{ entry.degree }}){% endif %}
  </p>

  {% if entry.supervisors %}
  <p class="meta">Supervised by {{ entry.supervisors|join(", ") }}</p>
  {% endif %}

  <p class="topics">{% for topic in entry.topics %}<span>{{ topic }}</span>{% endfor %}</p>

  <div class="summary">{{ summary }}</div>

  <h2>Files</h2>
  <ul>
    <li><a href="{{ doc }}">Document (PDF)</a></li>
    {% if entry.slides %}<li><a href="{{ entry.slides }}">Presentation</a></li>{% endif %}
  </ul>

  {% if entry.repos.code or entry.repos.docs %}
  <h2>Repositories</h2>
  <ul>
    {% for url in entry.repos.code %}<li><a href="{{ url }}">Code: {{ url }}</a></li>{% endfor %}
    {% if entry.repos.docs %}<li><a href="{{ entry.repos.docs }}">Docs: {{ entry.repos.docs }}</a></li>{% endif %}
  </ul>
  {% endif %}
</article>
</body>
</html>
```

```css
/* tools/tft/assets/style.css */
:root { --ink: #1a1a1a; --dim: #5a5a5a; --line: #d8d8d8; --bg: #fff; }

body {
  max-width: 54rem;
  margin: 0 auto;
  padding: 2rem 1rem;
  font: 16px/1.55 system-ui, sans-serif;
  color: var(--ink);
  background: var(--bg);
}

h1 { font-size: 1.6rem; margin-bottom: .2rem; }
.meta, #count { color: var(--dim); font-size: .9rem; }

#filters { display: flex; flex-wrap: wrap; gap: .5rem; margin: 1.5rem 0 1rem; }
#filters input[type=search] { flex: 1 1 16rem; }
#filters input, #filters select { padding: .4rem; border: 1px solid var(--line); }

#results { list-style: none; padding: 0; }
#results li { border-top: 1px solid var(--line); padding: .9rem 0; }
#results a { font-weight: 600; text-decoration: none; color: var(--ink); }
#results a:hover { text-decoration: underline; }

.topics span {
  display: inline-block;
  margin: 0 .3rem .3rem 0;
  padding: .1rem .5rem;
  border: 1px solid var(--line);
  border-radius: 1rem;
  font-size: .8rem;
  color: var(--dim);
}
```

```python
# tools/tft/site.py
"""Renders the catalog into a static site."""

import json
import shutil
from importlib import resources
from pathlib import Path

import markdown
from jinja2 import Environment, PackageLoader, select_autoescape

from .catalog import Catalog
from .config import Config
from .entry import DOC_NAME, Entry

SITE = "site"
INDEX_JSON = "index.json"
ENTRIES = "entries"
ASSETS = "assets"

SUMMARY_LIMIT = 300


def record(entry: Entry) -> dict:
    """The flat shape the client-side filter works with."""
    base = f"{ENTRIES}/{entry.slug}"

    return {
        "slug": entry.slug,
        "type": entry.type,
        "title": entry.title,
        "author": entry.author,
        "year": entry.year,
        "degree": entry.degree,
        "language": entry.language,
        "topics": list(entry.topics),
        "supervisors": list(entry.supervisors),
        "url": f"{base}/",
        "doc": f"{base}/{DOC_NAME[entry.type]}",
        "slides": f"{base}/{entry.slides}" if entry.slides else None,
        "has_code": bool(entry.repos.code),
        "has_slides": bool(entry.slides),
        "summary": _teaser(entry.summary),
    }


class Site:
    def __init__(self, cfg: Config, catalog: Catalog):
        self._cfg = cfg
        self._catalog = catalog
        self._jinja = Environment(
            loader=PackageLoader("tft", "templates"),
            autoescape=select_autoescape(["html"]),
        )

    def build(self, out: Path) -> None:
        """Render everything. The output directory is rebuilt from scratch."""
        entries = self._catalog.entries()

        if out.exists():
            shutil.rmtree(out)

        out.mkdir(parents=True)

        self._write_index(out, entries)
        self._write_assets(out)

        for entry in entries:
            self._write_entry(out, entry)

    def _write_index(self, out: Path, entries: list[Entry]) -> None:
        records = [record(entry) for entry in entries]
        (out / INDEX_JSON).write_text(json.dumps(records, indent=1, ensure_ascii=False))

        page = self._jinja.get_template("index.html").render(
            entries=entries,
            years=sorted({e.year for e in entries}, reverse=True),
            degrees=sorted({e.degree for e in entries if e.degree}),
            topics=sorted({t for e in entries for t in e.topics}),
        )
        (out / "index.html").write_text(page)

    def _write_entry(self, out: Path, entry: Entry) -> None:
        folder = out / ENTRIES / entry.slug
        folder.mkdir(parents=True)

        source = self._catalog.dir_for(entry)
        doc = DOC_NAME[entry.type]
        shutil.copyfile(source / doc, folder / doc)

        if entry.slides:
            shutil.copyfile(source / entry.slides, folder / entry.slides)

        page = self._jinja.get_template("entry.html").render(
            entry=entry, doc=doc, summary=markdown.markdown(entry.summary),
        )
        (folder / "index.html").write_text(page)

    def _write_assets(self, out: Path) -> None:
        """Copied verbatim: assets are not templates and must not be rendered."""
        source = resources.files("tft") / ASSETS
        dest = out / ASSETS
        dest.mkdir()

        for asset in source.iterdir():
            shutil.copyfile(asset, dest / asset.name)


def _teaser(summary: str) -> str:
    """The summary's first paragraph as plain text, for the index."""
    first = summary.strip().split("\n\n")[0]
    plain = first.replace("*", "").replace("`", "").replace("\n", " ").strip()

    return plain if len(plain) <= SUMMARY_LIMIT else plain[:SUMMARY_LIMIT].rstrip() + "..."
```

`_write_assets` copies every file in `tools/tft/assets/`, so Task 10 adds
`app.js` there without touching this module. Until then `index.html` links a
script that is not yet present; the page still renders and the tests below
still pass.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_site.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add tools/tft/site.py tools/tft/templates tools/tft/assets tests/test_site.py
git commit -m "Add static site renderer"
```

---

### Task 10: Client-side filtering

**Files:**
- Create: `tools/tft/assets/app.js`
- Test: `tests/test_app_js.py`

**Interfaces:**
- Consumes: the `index.json` records produced by `tft.site.record`.
- Produces: no Python interface. `app.js` reads `index.json`, renders into
  `#results`, and filters on `#q`, `#year`, `#degree`, `#topic`, `#code`,
  `#slides`.

- [ ] **Step 1: Write the failing test**

The browser code has no Python API, so the test pins the contract that would
silently break: every field `app.js` reads must exist in every record.

```python
# tests/test_app_js.py
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_app_js.py -v`
Expected: FAIL with `FileNotFoundError` — `tools/tft/assets/app.js` does not exist yet

- [ ] **Step 3: Write the implementation**

```javascript
// tools/tft/assets/app.js
// Filters the catalog in the browser. No framework, no network beyond
// index.json, so a copy of this directory works offline.

const CONTROLS = ["q", "year", "degree", "topic", "code", "slides"];

let entries = [];

function escape(text) {
  const box = document.createElement("div");
  box.textContent = text == null ? "" : String(text);
  return box.innerHTML;
}

function value(id) {
  const node = document.getElementById(id);
  return node.type === "checkbox" ? node.checked : node.value.trim().toLowerCase();
}

function matches(e, f) {
  if (f.year && String(e.year) !== f.year) return false;
  if (f.degree && e.degree !== f.degree) return false;
  if (f.topic && !e.topics.includes(f.topic)) return false;
  if (f.code && !e.has_code) return false;
  if (f.slides && !e.has_slides) return false;
  if (!f.q) return true;

  const haystack = [e.title, e.author, e.summary, e.topics.join(" ")].join(" ").toLowerCase();
  return haystack.includes(f.q);
}

function card(e) {
  const degree = e.degree ? ` &middot; ${escape(e.degree)}` : "";
  const topics = e.topics.map((t) => `<span>${escape(t)}</span>`).join("");

  return `<li>
    <a href="${escape(e.url)}">${escape(e.title)}</a>
    <p class="meta">${escape(e.author)} &middot; ${escape(e.year)}${degree}</p>
    <p>${escape(e.summary)}</p>
    <p class="topics">${topics}</p>
  </li>`;
}

function render() {
  const f = {};
  CONTROLS.forEach((id) => { f[id] = value(id); });

  const shown = entries.filter((e) => matches(e, f));
  document.getElementById("results").innerHTML = shown.map(card).join("");
  document.getElementById("count").textContent =
    `${shown.length} of ${entries.length} entries`;
}

fetch("index.json")
  .then((response) => response.json())
  .then((data) => {
    entries = data;
    CONTROLS.forEach((id) => {
      document.getElementById(id).addEventListener("input", render);
    });
    render();
  });
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_app_js.py tests/test_site.py -v`
Expected: PASS, 9 tests

- [ ] **Step 5: Commit**

```bash
git add tools/tft/assets/app.js tests/test_app_js.py
git commit -m "Add client-side catalog filtering"
```

---

### Task 11: Build command, CI workflows and README

**Files:**
- Modify: `tools/tft/cli.py` (add the `build` subcommand)
- Create: `.github/workflows/validate.yml`
- Create: `.github/workflows/pages.yml`
- Create: `README.md`
- Test: `tests/test_cli_build.py`

**Interfaces:**
- Consumes: `tft.site.Site`, `tft.site.SITE`.
- Produces: `tft build [--out PATH]`, defaulting to `<root>/site`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_build.py
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

    folder = tmp_path / "content" / "theses" / "2027-x"
    folder.mkdir(parents=True)
    (folder / "entry.yaml").write_text(yaml.safe_dump(MINIMAL, sort_keys=False))
    (folder / "summary.md").write_text("Text.\n")
    (folder / "thesis.pdf").write_bytes(b"%PDF-1.4\n")

    monkeypatch.chdir(tmp_path)

    return tmp_path


def test_build_writes_the_default_site_dir(repo):
    assert cli.main(["build"]) == 0
    assert (repo / "site" / "index.html").is_file()
    assert (repo / "site" / "index.json").is_file()


def test_build_honours_an_explicit_out(repo, tmp_path):
    out = tmp_path / "elsewhere"

    assert cli.main(["build", "--out", str(out)]) == 0
    assert (out / "index.html").is_file()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_cli_build.py -v`
Expected: FAIL with `argument command: invalid choice: 'build'`

- [ ] **Step 3: Wire the build command into the CLI**

Add the import and the two blocks below to `tools/tft/cli.py`. Nothing else
in that file changes.

```python
# add to the imports
from .site import SITE, Site
```

```python
# add next to the other command functions
def _build(args) -> int:
    root = find_root(Path.cwd())
    cfg = config.load(root)
    out = Path(args.out) if args.out else root / SITE

    Site(cfg, Catalog(cfg)).build(out)
    print(f"built {out}")

    return 0
```

```python
# add inside _parser(), before the final return
    build = subs.add_parser("build", help="render the static site")
    build.add_argument("--out", default=None, help="output directory (default: site/)")
    build.set_defaults(run=_build)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_cli_build.py -v`
Expected: PASS, 2 tests

- [ ] **Step 5: Write the workflows**

```yaml
# .github/workflows/validate.yml
name: validate

on:
  push:
  pull_request:

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: python -m pip install -e ".[dev]"
      - run: python -m pytest -q
      - run: tft validate
```

```yaml
# .github/workflows/pages.yml
name: pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: python -m pip install -e .
      - run: tft build
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deploy.outputs.page_url }}
    steps:
      - id: deploy
        uses: actions/deploy-pages@v4
```

- [ ] **Step 6: Write the README**

```markdown
# docs-TFTs

A catalog of the Bachelor's, Master's and PhD theses of the research group.
Each entry holds its metadata, an English summary, the compiled PDF, links to
the attached code and docs repositories, and an optional presentation. The
site is published from `main` to GitHub Pages.

LaTeX sources and anything not cleared for publication live in the private
repository `ECL-STRAST/docs-TFTs-private`. Presence in *this* repository is
what makes an entry public; there is no flag to get wrong.

## Layout

    content/theses/<year>-<slug>/   entry.yaml, summary.md, thesis.pdf, slides.pdf
    taxonomy/topics.yaml            the controlled topic vocabulary
    tools/tft/                      the tooling
    site/                           build output, gitignored

## Setup

    python -m pip install -e ".[dev]"
    export OVERLEAF_GIT_TOKEN=...          # never committed
    git clone git@github.com:ECL-STRAST/docs-TFTs-private.git ../docs-TFTs-private

`latexmk` and a TeX distribution are needed to add or sync entries, but not
to build the site.

## Adding an entry

    tft add --overleaf <project-id> --name nieves-serrano-biomechanics-db \
            --year 2027 --title "..." --author "..." --degree bachelor

Then edit the entry's `summary.md` and replace the `CHANGE-ME` topic with
tags from `taxonomy/topics.yaml`, adding any missing tag to that file first.
Finally:

    tft validate

Entries may be added before the work is defended: a draft PDF, no attached
repositories and no slides are all valid.

## Other commands

    tft sync <slug>     re-pull from Overleaf and recompile
    tft build           render site/ locally
```

- [ ] **Step 7: Run the whole suite**

Run: `python -m pytest -q && tft validate && tft build`
Expected: every test passes; `validate` prints `ok`; `build` writes `site/`

- [ ] **Step 8: Commit**

```bash
git add tools/tft/cli.py tests/test_cli_build.py .github/workflows README.md
git commit -m "Add build command, CI workflows and README"
```

---

### Task 12: Ingest the first real thesis

**Files:**
- Create: `content/theses/2027-nieves-serrano-biomechanics-db/`

This task is manual and needs the `OVERLEAF_GIT_TOKEN`, a TeX distribution,
and a checkout of the private repository. It is the plan's acceptance test:
the worked example the README points at.

- [ ] **Step 1: Add the entry**

```bash
tft add --overleaf 698b41fa174f9aec00db94cb \
        --name nieves-serrano-biomechanics-db \
        --year 2027 \
        --title "Design and development of a database for the storage and processing of biomechanical data from physiotherapy patients" \
        --author "Silvia Nieves Serrano" \
        --degree bachelor
```

- [ ] **Step 2: Fill in the entry**

Edit `content/theses/2027-nieves-serrano-biomechanics-db/summary.md` with one
or two English paragraphs, then in `entry.yaml` set:

```yaml
supervisors: [Rodrigo García Carmona]
topics: [biomechanics, rehabilitation, vr]
repos:
  code: [https://github.com/ECL-STRAST/libremotion-chloe]
  docs: https://github.com/ECL-STRAST/libremotion-chloe-docs
```

- [ ] **Step 3: Validate and preview**

Run: `tft validate && tft build && python -m http.server -d site 8000`
Expected: `ok`, then the entry visible and filterable at http://localhost:8000

- [ ] **Step 4: Commit both repositories**

```bash
git -C ../docs-TFTs-private add -A
git -C ../docs-TFTs-private commit -m "Mirror sources for 2027-nieves-serrano-biomechanics-db"

git add content/theses/2027-nieves-serrano-biomechanics-db
git commit -m "Add Nieves Serrano biomechanics database thesis"
```

- [ ] **Step 5: Enable Pages**

In the repository settings, set Pages to build from GitHub Actions, then push
`main` and confirm the deployment succeeds.
