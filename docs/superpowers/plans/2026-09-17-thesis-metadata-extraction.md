# Thesis Metadata Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derive title, author, year, degree, summary and keywords from a thesis's LaTeX source instead of the command line, and add a score, an optional author portrait and ECL visual theming.

**Architecture:** A new driver module `tools/tft/tex.py` sits beside `latex.py` and reports what it can find in a LaTeX source tree, returning `None` for anything absent rather than raising. `ingest.py` applies the human's CLI overrides on top, then decides what is mandatory and aborts naming any field still missing. The layer chain stays `cli -> ingest -> tex`; `tex.py` never sees `Entry`, `Catalog` or YAML.

**Tech Stack:** Python 3.11+, stdlib `re` and `unicodedata` only (no new dependency), PyYAML, Jinja2, markdown, pytest.

**Spec:** `docs/superpowers/specs/2026-09-17-thesis-metadata-extraction-design.md`

## Global Constraints

- No new runtime dependency. `pyproject.toml` stays at `PyYAML>=6`, `Jinja2>=3.1`, `markdown>=3.5`.
- All four new `entry.yaml` fields go in `OPTIONAL`, never `MANDATORY`: the existing entry `content/theses/2026-gomez-martinez-biomechanics-viz/entry.yaml` must keep validating untouched at every commit.
- `keywords` is never checked against `taxonomy/topics.yaml`. `topics` remains the only controlled vocabulary and the only site filter facet.
- Score domain is `0 <= score <= 10`. `honours: true` without a `score` is rejected.
- Colour tokens, exact values: `--ecl-blue: #046ba5`, `--ecl-navy: #093d76`, `--ecl-teal: #218880`, `--ecl-green: #1a6c46`. Teal is decoration only (4.29 contrast on white, below the 4.5 AA floor); it must never colour text.
- Follow the repo's house style: `{}` on every `if`, early returns over nesting, blank lines between logical blocks, short names, comments saying *what and why*.
- Commit messages: imperative subject, <=50 chars, capitalised, no trailing period, blank line, body wrapped at 72.

---

### Task 1: The `tex` driver — macros and the brace scanner

**Files:**
- Create: `tools/tft/tex.py`
- Modify: `tools/tft/errors.py`
- Test: `tests/test_tex.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `tft.tex.Meta` (frozen dataclass, fields `title: str | None`, `author: str | None`, `year: int | None`, `degree: str | None`, `abstract: str | None`, `keywords: tuple[str, ...]`); `tft.errors.ExtractError`. Later tasks in this module add `detex`, `_degree`, `_abstract` and the public `read(src: Path) -> Meta`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tex.py`:

```python
import pytest

from tft import tex
from tft.errors import ExtractError

MAIN = r"""
\newcommand{\authorname}{Belén Gómez Martínez}
\newcommand{\tfgtitle}{Design and development of an environment}
\newcommand{\fecha}{Junio 2026}
\begin{document}
\end{document}
"""


def test_reads_the_template_macros():
    assert tex.macro(MAIN, tex.TITLE_MACRO) == "Design and development of an environment"
    assert tex.macro(MAIN, tex.AUTHOR_MACRO) == "Belén Gómez Martínez"
    assert tex.macro(MAIN, tex.DATE_MACRO) == "Junio 2026"


def test_absent_macro_is_none_not_an_error():
    # tex reports what it finds; ingest decides what is mandatory.
    assert tex.macro(MAIN, "nosuchmacro") is None


def test_macro_value_may_contain_nested_braces():
    source = r"\newcommand{\tfgtitle}{A study of \emph{gait} in adults}"

    assert tex.macro(source, tex.TITLE_MACRO) == r"A study of \emph{gait} in adults"


def test_unbalanced_braces_are_reported():
    with pytest.raises(ExtractError, match="unbalanced"):
        tex.macro(r"\newcommand{\tfgtitle}{never closed", tex.TITLE_MACRO)


def test_meta_is_frozen():
    meta = tex.Meta(
        title="t", author="a", year=2026, degree="bachelor",
        abstract="text", keywords=("gait",),
    )

    with pytest.raises(AttributeError):
        meta.title = "other"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tex.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tft.tex'`

- [ ] **Step 3: Write minimal implementation**

Append to `tools/tft/errors.py`, after `CompileError`:

```python
class ExtractError(TftError):
    """A thesis's metadata could not be read from its LaTeX source."""
```

Create `tools/tft/tex.py`:

```python
"""Reads a thesis's own metadata out of its LaTeX sources.

Reports what it finds and returns None for what it does not; deciding
which fields are mandatory belongs to the caller, which can also accept
the human's overrides. Only malformed input raises.
"""

import re
from dataclasses import dataclass

from .errors import ExtractError

# The ETSIT template declares these three as \newcommand macros.
TITLE_MACRO = "tfgtitle"
AUTHOR_MACRO = "authorname"
DATE_MACRO = "fecha"


@dataclass(frozen=True)
class Meta:
    """What a LaTeX source tree says about itself. None means not found."""
    title: str | None
    author: str | None
    year: int | None
    degree: str | None
    abstract: str | None
    keywords: tuple[str, ...]


def macro(text: str, name: str) -> str | None:
    """The argument of \\newcommand{\\name}{...}, or None if undeclared."""
    match = re.search(r"\\newcommand\s*\{\\" + name + r"\}\s*\{", text)

    if match is None:
        return None

    # match.end() - 1 is the opening brace of the value group.
    return braced(text, match.end() - 1)[0].strip()


def braced(text: str, open_at: int) -> tuple[str, int]:
    """Content of the {...} group at open_at, and the index past its close.

    Counts depth so a value containing \\emph{gait} survives intact.
    """
    depth = 0

    for i in range(open_at, len(text)):
        if text[i] == "{":
            depth += 1
            continue

        if text[i] != "}":
            continue

        depth -= 1

        if depth == 0:
            return text[open_at + 1:i], i + 1

    raise ExtractError("unbalanced braces in the LaTeX source")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tex.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add tools/tft/tex.py tools/tft/errors.py tests/test_tex.py
git commit -m "Add tex driver reading template macros"
```

---

### Task 2: Degree detection

**Files:**
- Modify: `tools/tft/tex.py`
- Test: `tests/test_tex.py`

**Interfaces:**
- Consumes: `tft.errors.ExtractError` from Task 1.
- Produces: `tex.degree(src: Path) -> str | None`, returning `"bachelor"`, `"master"`, `"phd"` or `None`. Raises `ExtractError` when two different degrees are found.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tex.py`:

```python
def _tree(tmp_path, **files):
    """A source tree: _tree(p, **{"main.tex": "...", "ch/a.tex": "..."})."""
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    return tmp_path


def test_bachelor_degree_from_the_cover(tmp_path):
    src = _tree(tmp_path, **{"chapters/0-preamble.tex": "TRABAJO FIN DE GRADO"})

    assert tex.degree(src) == "bachelor"


def test_degree_phrase_with_the_optional_de(tmp_path):
    src = _tree(tmp_path, **{"main.tex": "TRABAJO DE FIN DE GRADO"})

    assert tex.degree(src) == "bachelor"


def test_master_degree_is_accent_insensitive(tmp_path):
    src = _tree(tmp_path, **{"main.tex": "Trabajo de Fin de Máster"})

    assert tex.degree(src) == "master"


def test_phd_degree(tmp_path):
    src = _tree(tmp_path, **{"main.tex": "TESIS DOCTORAL"})

    assert tex.degree(src) == "phd"


def test_no_degree_phrase_is_none(tmp_path):
    src = _tree(tmp_path, **{"main.tex": "nothing relevant here"})

    assert tex.degree(src) is None


def test_two_degrees_is_ambiguous(tmp_path):
    src = _tree(
        tmp_path,
        **{"main.tex": "TRABAJO FIN DE GRADO", "biblio.tex": "Tesis Doctoral"},
    )

    with pytest.raises(ExtractError, match="ambiguous"):
        tex.degree(src)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tex.py -v -k degree`
Expected: FAIL with `AttributeError: module 'tft.tex' has no attribute 'degree'`

- [ ] **Step 3: Write minimal implementation**

Add to the imports at the top of `tools/tft/tex.py`:

```python
import unicodedata
from pathlib import Path
```

Add after the macro constants:

```python
# Cover-page phrases, matched against accent-folded uppercase text so
# "Máster", "MASTER" and "máster" are one case.
DEGREES = (
    (re.compile(r"TRABAJO (?:DE )?FIN DE GRADO"), "bachelor"),
    (re.compile(r"TRABAJO (?:DE )?FIN DE MASTER"), "master"),
    (re.compile(r"TESIS DOCTORAL"), "phd"),
)

TEX_GLOB = "*.tex"
```

Add at the end of the module:

```python
def degree(src: Path) -> str | None:
    """The degree named on the cover, or None when no phrase appears."""
    found = set()

    for path in sorted(src.rglob(TEX_GLOB)):
        text = fold(path.read_text(encoding="utf-8", errors="ignore"))
        found |= {name for pattern, name in DEGREES if pattern.search(text)}

    # Two different phrases means a stray citation, not a second degree.
    if len(found) > 1:
        raise ExtractError(f"degree is ambiguous ({', '.join(sorted(found))}); pass --degree")

    return found.pop() if found else None


def fold(text: str) -> str:
    """Uppercase with accents stripped, for matching Spanish cover phrases."""
    decomposed = unicodedata.normalize("NFKD", text)

    return "".join(c for c in decomposed if not unicodedata.combining(c)).upper()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tex.py -v`
Expected: PASS, 11 passed

- [ ] **Step 5: Commit**

```bash
git add tools/tft/tex.py tests/test_tex.py
git commit -m "Detect the degree from cover-page phrases"
```

---

### Task 3: De-TeXing, abstract, keywords and `read`

**Files:**
- Modify: `tools/tft/tex.py`
- Test: `tests/test_tex.py`

**Interfaces:**
- Consumes: `tex.Meta`, `tex.macro`, `tex.braced`, `tex.degree` from Tasks 1-2.
- Produces: `tex.detex(text: str) -> str` and `tex.read(src: Path) -> Meta`. `read` is the module's only caller-facing entry point; `ingest.py` uses it in Task 5.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tex.py`:

```python
ABSTRACT = r"""
\cleardoublepage
\phantomsection
\chapter*{Abstract}
\addcontentsline{toc}{chapter}{Abstract}
This Bachelor Thesis presents \textbf{CHLOE}, a web-based application.

It reads \textbf{C3D \emph{marker}} data and renders it in a browser.

\vfill
\textbf{Keywords:} Biomedical engineering, biomechanics, Motion Capture, C3D.
"""

FULL_MAIN = r"""
\newcommand{\authorname}{Belén Gómez Martínez}
\newcommand{\tfgtitle}{Design and development of an environment}
\newcommand{\fecha}{Junio 2026}
TRABAJO FIN DE GRADO
"""


def test_detex_unwraps_nested_emphasis():
    assert tex.detex(r"A \textbf{bold \emph{and italic} run} here") == "A bold and italic run here"


def test_detex_removes_a_macro_with_every_brace_group():
    assert tex.detex(r"\addcontentsline{toc}{chapter}{Abstract} text") == "text"


def test_detex_keeps_paragraph_breaks():
    assert tex.detex("One.\n\nTwo.") == "One.\n\nTwo."


def test_reads_the_abstract_and_keywords(tmp_path):
    src = _tree(tmp_path, **{"main.tex": FULL_MAIN, "chapters/B-abstract.tex": ABSTRACT})

    meta = tex.read(src)

    assert meta.abstract.startswith("This Bachelor Thesis presents CHLOE")
    assert "C3D marker" in meta.abstract
    assert "Keywords" not in meta.abstract
    assert meta.keywords == (
        "biomedical engineering", "biomechanics", "motion capture", "c3d",
    )


def test_abstract_is_found_whatever_the_chapter_is_called(tmp_path):
    src = _tree(tmp_path, **{"main.tex": FULL_MAIN, "parts/summary-en.tex": ABSTRACT})

    assert tex.read(src).abstract.startswith("This Bachelor Thesis")


def test_read_returns_every_field(tmp_path):
    src = _tree(tmp_path, **{"main.tex": FULL_MAIN, "chapters/B-abstract.tex": ABSTRACT})

    meta = tex.read(src)

    assert meta.title == "Design and development of an environment"
    assert meta.author == "Belén Gómez Martínez"
    assert meta.year == 2026
    assert meta.degree == "bachelor"


def test_missing_pieces_are_none_not_errors(tmp_path):
    src = _tree(tmp_path, **{"main.tex": "\\begin{document}\\end{document}"})

    meta = tex.read(src)

    assert meta.title is None
    assert meta.author is None
    assert meta.year is None
    assert meta.degree is None
    assert meta.abstract is None
    assert meta.keywords == ()


def test_abstract_without_keywords_yields_no_keywords(tmp_path):
    body = "\\chapter*{Abstract}\nJust prose, no keyword line.\n"
    src = _tree(tmp_path, **{"main.tex": FULL_MAIN, "chapters/B-abstract.tex": body})

    meta = tex.read(src)

    assert meta.abstract == "Just prose, no keyword line."
    assert meta.keywords == ()


def test_year_comes_from_the_spanish_date_macro(tmp_path):
    main = "\\newcommand{\\fecha}{Septiembre 2031}"
    src = _tree(tmp_path, **{"main.tex": main})

    assert tex.read(src).year == 2031
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tex.py -v -k "detex or read or abstract or year_comes"`
Expected: FAIL with `AttributeError: module 'tft.tex' has no attribute 'detex'`

- [ ] **Step 3: Write minimal implementation**

Add to the constants block in `tools/tft/tex.py`:

```python
MAIN_FILE = "main.tex"
ABSTRACT_MARKER = r"\chapter*{Abstract}"
KEYWORDS_MARKER = r"\textbf{Keywords:}"

# Layout-only commands: they carry no words, so they simply go.
DROP = re.compile(r"\\(?:vfill|cleardoublepage|phantomsection|noindent)\b")
# Font switches whose argument IS the prose, so the braces are unwrapped.
UNWRAP = re.compile(r"\\(?:textbf|textit|emph|texttt|textsc)\s*\{")
# Anything else, with every brace group it owns: \addcontentsline takes
# three, and leaving them behind would drop "{chapter}{Abstract}" in the text.
MACRO = re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})*")
SPACES = re.compile(r"[ \t]+")
BLANKS = re.compile(r"\n{3,}")

YEAR = re.compile(r"(?:19|20)\d{2}")
```

Add at the end of the module:

```python
def detex(text: str) -> str:
    """LaTeX prose as plain text, paragraph breaks preserved."""
    text = DROP.sub("", text)
    text = _unwrap(text)
    text = MACRO.sub("", text)
    text = text.replace("{", "").replace("}", "")
    text = SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())

    return BLANKS.sub("\n\n", text).strip()


def read(src: Path) -> Meta:
    """Everything the source tree declares about itself."""
    main = (src / MAIN_FILE).read_text(encoding="utf-8", errors="ignore")
    abstract, keywords = _abstract(src)
    year = YEAR.search(macro(main, DATE_MACRO) or "")

    return Meta(
        title=macro(main, TITLE_MACRO),
        author=macro(main, AUTHOR_MACRO),
        year=int(year.group()) if year else None,
        degree=degree(src),
        abstract=abstract,
        keywords=keywords,
    )


def _unwrap(text: str) -> str:
    """Replace \\textbf{x} and friends with x, outermost first.

    Each pass exposes any nested switch to the next, so
    \\textbf{a \\emph{b}} resolves in two passes without recursion.
    """
    while True:
        match = UNWRAP.search(text)

        if match is None:
            return text

        inner, end = braced(text, match.end() - 1)
        text = text[:match.start()] + inner + text[end:]


def _abstract(src: Path) -> tuple[str | None, tuple[str, ...]]:
    """The English abstract and the author's keywords, both de-TeXed."""
    path = _abstract_file(src)

    if path is None:
        return None, ()

    _, _, after = path.read_text(encoding="utf-8").partition(ABSTRACT_MARKER)
    body, marker, tail = after.partition(KEYWORDS_MARKER)

    if not marker:
        return detex(body), ()

    words = [w.strip().lower() for w in detex(tail).rstrip(".").split(",")]

    return detex(body), tuple(w for w in words if w)


def _abstract_file(src: Path) -> Path | None:
    """Found by scanning, so a renamed chapter file still works."""
    for path in sorted(src.rglob(TEX_GLOB)):
        if ABSTRACT_MARKER in path.read_text(encoding="utf-8", errors="ignore"):
            return path

    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tex.py -v`
Expected: PASS, 20 passed

- [ ] **Step 5: Verify against the real thesis**

Run:

```bash
python -c "
from pathlib import Path
from tft import tex
m = tex.read(Path('.work/2026-gomez-martinez-biomechanics-viz'))
print(m.title); print(m.author, m.year, m.degree); print(m.keywords)
print(len(m.abstract.split(chr(10)*2)), 'paragraphs,', len(m.abstract), 'chars')
"
```

Expected, exactly:

```
Design and development of an environment for the visualization of biomechanical information of physiotherapy patients
Belén Gómez Martínez 2026 bachelor
('biomedical engineering', 'biomechanics', 'motion capture', 'c3d', 'plug-in gait', 'data visualization', 'analog data', 'physiotherapy')
5 paragraphs, 2637 chars
```

If `.work/2026-gomez-martinez-biomechanics-viz` is absent, skip this step and note it; the unit tests are the gate.

- [ ] **Step 6: Commit**

```bash
git add tools/tft/tex.py tests/test_tex.py
git commit -m "Extract the abstract and keywords from LaTeX"
```

---

### Task 4: Schema — keywords, score, honours, photo

**Files:**
- Modify: `tools/tft/entry.py`
- Modify: `tools/tft/catalog.py:96-103` (`_required_files`)
- Test: `tests/test_entry.py`, `tests/test_catalog.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Entry.keywords: tuple[str, ...]` (default `()`), `Entry.score: float | None`, `Entry.honours: bool` (default `False`), `Entry.photo: str | None`. Task 5 constructs entries with `keywords`; Task 7 reads all four.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_entry.py`:

```python
def test_new_optional_fields_round_trip():
    data = MINIMAL | {
        "keywords": ["motion capture", "c3d"],
        "score": 10,
        "honours": True,
        "photo": "photo.jpg",
    }

    parsed = entry.from_dict("2027-x", data)

    assert parsed.keywords == ("motion capture", "c3d")
    assert parsed.score == 10
    assert parsed.honours is True
    assert parsed.photo == "photo.jpg"
    assert entry.to_dict(parsed) == data


def test_entry_without_the_new_fields_is_unchanged():
    # The catalog's existing entry predates them and must keep validating.
    parsed = entry.from_dict("2027-x", MINIMAL)

    assert parsed.keywords == ()
    assert parsed.score is None
    assert parsed.honours is False
    assert parsed.photo is None
    assert entry.to_dict(parsed) == MINIMAL


@pytest.mark.parametrize("score", [-1, 11, 10.5])
def test_score_outside_the_scale_is_rejected(score):
    with pytest.raises(BadValue, match="score"):
        entry.from_dict("2027-x", MINIMAL | {"score": score})


def test_score_must_be_a_number():
    with pytest.raises(BadValue, match="score"):
        entry.from_dict("2027-x", MINIMAL | {"score": "10"})


def test_score_must_not_be_a_boolean():
    # bool is a subclass of int in Python; True would otherwise pass as 1.
    with pytest.raises(BadValue, match="score"):
        entry.from_dict("2027-x", MINIMAL | {"score": True})


def test_score_accepts_the_bounds():
    assert entry.from_dict("2027-x", MINIMAL | {"score": 0}).score == 0
    assert entry.from_dict("2027-x", MINIMAL | {"score": 10}).score == 10
    assert entry.from_dict("2027-x", MINIMAL | {"score": 9.5}).score == 9.5


def test_honours_needs_a_score():
    with pytest.raises(BadValue, match="honours"):
        entry.from_dict("2027-x", MINIMAL | {"honours": True})


def test_keywords_must_not_be_empty():
    with pytest.raises(BadValue, match="keywords"):
        entry.from_dict("2027-x", MINIMAL | {"keywords": []})


def test_keywords_must_be_non_empty_strings():
    with pytest.raises(BadValue, match="keywords"):
        entry.from_dict("2027-x", MINIMAL | {"keywords": ["ok", " "]})


def test_keywords_are_not_checked_against_the_taxonomy():
    # Deliberate: keywords are the thesis's own words, topics are curated.
    parsed = entry.from_dict("2027-x", MINIMAL | {"keywords": ["plug-in gait"]})

    assert parsed.keywords == ("plug-in gait",)
```

Append to `tests/test_catalog.py`:

```python
def test_declared_photo_must_exist(repo):
    _add(repo, "2027-x", data=MINIMAL | {"photo": "photo.jpg"})

    assert any("photo.jpg" in p for p in _catalog(repo).problems())


def test_present_photo_is_no_problem(repo):
    folder = _add(repo, "2027-x", data=MINIMAL | {"photo": "photo.jpg"})
    (folder / "photo.jpg").write_bytes(b"\xff\xd8\xff")

    assert _catalog(repo).problems() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_entry.py tests/test_catalog.py -v`
Expected: FAIL — `UnknownField: unknown field: keywords` on the new entry tests, and `test_declared_photo_must_exist` failing because `problems()` returns `[]`.

- [ ] **Step 3: Write minimal implementation**

In `tools/tft/entry.py`, extend the field lists and add a constant:

```python
OPTIONAL = (
    "degree", "venue", "supervisors", "overleaf", "repos", "slides",
    "keywords", "score", "honours", "photo",
)

MAX_SCORE = 10
```

Add to the `Entry` dataclass, after `slides`:

```python
    keywords: tuple[str, ...] = ()
    score: float | None = None
    honours: bool = False
    photo: str | None = None
```

In `from_dict`, add `_check_score(data)` and `_check_keywords(data)` immediately after the existing `_check_types(data)` call, and add these arguments to the `Entry(...)` construction, after `slides=data.get("slides")`:

```python
        keywords=tuple(data.get("keywords", ())),
        score=data.get("score"),
        honours=bool(data.get("honours", False)),
        photo=data.get("photo"),
```

In `to_dict`, after the `_put(out, "supervisors", ...)` line:

```python
    _put(out, "score", entry.score)
    _put(out, "honours", entry.honours)
```

and after `_put(out, "slides", entry.slides)`:

```python
    _put(out, "keywords", list(entry.keywords))
    _put(out, "photo", entry.photo)
```

Add the two validators beside `_check_types`:

```python
def _check_score(data: dict) -> None:
    score = data.get("score")

    if score is not None:
        # bool is an int subclass; honours must not sneak in as a score.
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise BadValue("score must be a number")

        if not 0 <= score <= MAX_SCORE:
            raise BadValue(f"score must be between 0 and {MAX_SCORE}, got {score}")

    # An honours mark qualifies a score; alone it says nothing.
    if data.get("honours") and score is None:
        raise BadValue("honours needs a score")


def _check_keywords(data: dict) -> None:
    if "keywords" not in data:
        return

    keywords = data["keywords"]

    if not isinstance(keywords, list) or not keywords:
        raise BadValue("keywords must be a non-empty list")

    for word in keywords:
        if not isinstance(word, str) or not word.strip():
            raise BadValue("keywords must be non-empty strings")
```

Note: `test_score_outside_the_scale_is_rejected` includes `10.5`, which the `0 <= score <= 10` bound already rejects.

In `tools/tft/catalog.py`, extend `_required_files`:

```python
    def _required_files(self, entry: Entry) -> list[str]:
        names = [store.SUMMARY_FILE, DOC_NAME[entry.type]]

        # Slides are optional, but a declared file must be there.
        if entry.slides:
            names.append(entry.slides)

        if entry.photo:
            names.append(entry.photo)

        return names
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -v`
Expected: PASS, all tests green (the existing suites are untouched by optional fields).

- [ ] **Step 5: Confirm the live entry still validates**

Run: `python -m tft.cli validate` (or `tft validate`)
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add tools/tft/entry.py tools/tft/catalog.py tests/test_entry.py tests/test_catalog.py
git commit -m "Add keywords, score, honours and photo fields"
```

---

### Task 5: Wire extraction into `tft add`

**Files:**
- Modify: `tools/tft/ingest.py`
- Modify: `tools/tft/catalog.py:47-70` (`create`)
- Modify: `tools/tft/cli.py`
- Test: `tests/test_ingest.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `tex.read` (Task 3), `Entry.keywords` (Task 4).
- Produces: `ingest.Overrides` (frozen dataclass: `title`, `author`, `year`, `degree`, all defaulting to `None`); `Ingest.add(project_id: str, name: str, overrides: Overrides = Overrides(), type: str = THESIS) -> Path`; `Catalog.create(..., keywords=(), summary=STUB_SUMMARY)`. Task 6 reuses `Ingest._meta`.

Note two deliberate changes of shape:
1. The slug is now built inside `Ingest.add` from the extracted year, not in `cli.py`.
2. The scratch clone moves from `.work/<slug>` to `.work/<project_id>`, which is stable before the year is known and lets `sync` pull instead of re-cloning. The existing `.work/2026-gomez-martinez-biomechanics-viz` becomes orphaned scratch; `.work/` is gitignored, so leave it or delete it by hand.

- [ ] **Step 1: Write the failing test**

Replace the `fetch` stub and `_add` helper in `tests/test_ingest.py` with these, and append the new tests:

```python
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
```

Add to the imports at the top of `tests/test_ingest.py`:

```python
from tft.errors import CompileError, ExtractError
from tft.ingest import Ingest, Overrides
```

(replacing the existing `CompileError` and `Ingest` import lines).

Three tests in `tests/test_cli.py` monkeypatch `Ingest.add` with its old
signature and must be updated. Replace each `fake_add` and the argument
lists that feed it:

```python
def test_add_builds_the_slug_from_the_name(repo, monkeypatch):
    seen = {}

    def fake_add(self, project_id, name, overrides=None, type="thesis"):
        seen["name"] = name
        return repo

    monkeypatch.setattr("tft.ingest.Ingest.add", fake_add)

    code = cli.main(["add", "--overleaf", "abc", "--name", "nieves-serrano-biomechanics-db"])

    assert code == 0
    assert seen["name"] == "nieves-serrano-biomechanics-db"


def test_add_passes_the_overrides_through(repo, monkeypatch):
    seen = {}

    def fake_add(self, project_id, name, overrides=None, type="thesis"):
        seen["overrides"] = overrides
        return repo

    monkeypatch.setattr("tft.ingest.Ingest.add", fake_add)

    code = cli.main([
        "add", "--overleaf", "abc", "--name", "x",
        "--title", "T", "--year", "2027",
    ])

    assert code == 0
    assert seen["overrides"].title == "T"
    assert seen["overrides"].year == 2027
    assert seen["overrides"].author is None


def test_add_publication_passes_the_type(repo, monkeypatch):
    seen = {}

    def fake_add(self, project_id, name, overrides=None, type="thesis"):
        seen["type"] = type
        return repo

    monkeypatch.setattr("tft.ingest.Ingest.add", fake_add)

    code = cli.main([
        "add", "--overleaf", "abc", "--name", "x", "--type", "publication",
    ])

    assert code == 0
    assert seen["type"] == "publication"


def test_add_reports_an_unreadable_field(repo, monkeypatch, capsys):
    from tft.errors import ExtractError

    def fake_add(self, project_id, name, overrides=None, type="thesis"):
        raise ExtractError("could not read title; pass --title")

    monkeypatch.setattr("tft.ingest.Ingest.add", fake_add)

    code = cli.main(["add", "--overleaf", "abc", "--name", "x"])

    assert code == 1
    assert "--title" in capsys.readouterr().err
```

These replace `test_add_builds_the_slug_from_year_and_name`,
`test_add_publication_omits_degree_by_default` and
`test_add_thesis_without_degree_fails_cleanly`. The degree-is-mandatory
case moves into the extractor's territory and is covered by
`test_missing_metadata_names_the_field` above.

Also trim the now-unnecessary flags from `test_add_reports_a_missing_token`:

```python
    code = cli.main([
        "add", "--overleaf", "abc", "--name", "nieves-serrano-biomechanics-db",
    ])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: FAIL with `ImportError: cannot import name 'Overrides' from 'tft.ingest'`

- [ ] **Step 3: Write minimal implementation**

In `tools/tft/catalog.py`, widen `create`:

```python
    def create(self, slug, type, year, title, author,
               degree=None, keywords=(), summary=STUB_SUMMARY) -> Path:
        """Scaffold a new entry folder with stubs for the human to fill in."""
        folder = self._content(COLLECTIONS[type]) / slug

        if store.dir_exists(folder):
            raise FileExistsError(f"{folder} already exists")

        data = {
            "type": type, "title": title, "author": author, "year": year,
            "topics": ["CHANGE-ME"], "language": "en",
        }

        if degree is not None:
            data["degree"] = degree

        if keywords:
            data["keywords"] = list(keywords)

        store.write(folder, from_dict(slug, data))
        store.write_summary(folder, summary)

        return folder
```

In `tools/tft/ingest.py`, add imports and constants at the top:

```python
from . import latex, overleaf, store, tex
from .errors import ExtractError
```

(extend the existing `from . import latex, overleaf` line and add the two others; `store` is needed in Task 6.)

```python
# Everything an entry cannot be created without. Each may instead be
# supplied by hand when a thesis does not follow the group's template.
REQUIRED = ("title", "author", "year", "degree", "abstract", "keywords")
```

Add the `Overrides` dataclass after the `SOURCES` constant:

```python
@dataclass(frozen=True)
class Overrides:
    """What the human supplies when the source does not declare it."""
    title: str | None = None
    author: str | None = None
    year: int | None = None
    degree: str | None = None
```

and add `from dataclasses import dataclass` to the imports (the module already imports `dataclasses`; add the name import beside it).

Replace `Ingest.add`:

```python
    def add(self, project_id, name, overrides=Overrides(), type=THESIS) -> Path:
        """Create a new entry from an Overleaf project."""
        work = self._cfg.work / project_id
        sha = self._fetch(project_id, work)

        # Read metadata before compiling: a missing field costs seconds,
        # a LaTeX run costs a minute.
        meta = self._meta(work, overrides)
        pdf = self._compile(work, main=None)

        slug = f"{meta.year}-{name}"
        folder = self._catalog.create(
            slug=slug, type=type, year=meta.year, title=meta.title,
            author=meta.author, degree=meta.degree, keywords=meta.keywords,
            summary=meta.abstract,
        )
        entry = self._catalog.find(slug)

        self._install(entry, folder, pdf, work, sha, project_id)

        return folder
```

Add the `_meta` helper beside `_compile`:

```python
    def _meta(self, work: Path, overrides: Overrides) -> tex.Meta:
        """Source metadata with the human's overrides laid on top."""
        found = tex.read(work)
        supplied = {
            name: value
            for name, value in dataclasses.asdict(overrides).items()
            if value is not None
        }
        meta = dataclasses.replace(found, **supplied)
        missing = [name for name in REQUIRED if not getattr(meta, name)]

        if missing:
            raise ExtractError(f"could not read {', '.join(missing)}; {_remedy(missing)}")

        return meta
```

and at module level:

```python
# Fields the CLI can supply; the rest must be fixed in the LaTeX itself.
OVERRIDABLE = ("title", "author", "year", "degree")


def _remedy(missing: list[str]) -> str:
    """What the human can do about each field that could not be read."""
    flags = [f"--{name}" for name in missing if name in OVERRIDABLE]

    if not flags:
        return "fix the thesis source"

    return f"pass {' '.join(flags)}"
```

In `tools/tft/cli.py`, import `Overrides` and make the four flags optional:

```python
from .ingest import Ingest, Overrides
```

```python
def _add(args) -> int:
    overrides = Overrides(
        title=args.title, author=args.author, year=args.year, degree=args.degree,
    )
    folder = _ingest().add(
        project_id=args.overleaf, name=args.name,
        overrides=overrides, type=args.type,
    )
    print(f"created {folder}; now replace the CHANGE-ME topic")

    return 0
```

```python
    add = subs.add_parser("add", help="add an entry from an Overleaf project")
    add.add_argument("--overleaf", required=True, metavar="ID", help="Overleaf project id")
    add.add_argument("--name", required=True, help="slug without the year, e.g. surname-topic")
    add.add_argument("--title", default=None, help="override the extracted title")
    add.add_argument("--author", default=None, help="override the extracted author")
    add.add_argument("--year", default=None, type=int, help="override the extracted year")
    add.add_argument("--degree", default=None, choices=DEGREES,
                     help="override the extracted degree")
    add.add_argument("--type", default=THESIS, choices=TYPES)
    add.set_defaults(run=_add)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ingest.py tests/test_cli.py -v`
Expected: PASS. `sync` is untouched by this task, so `test_sync_reports_no_change` keeps passing; Task 6 changes it.

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tools/tft/ingest.py tools/tft/catalog.py tools/tft/cli.py tests/test_ingest.py tests/test_cli.py
git commit -m "Derive entry metadata from the thesis source"
```

---

### Task 6: `tft sync` re-extracts

**Files:**
- Modify: `tools/tft/ingest.py`
- Modify: `tools/tft/store.py:41-51` (docstrings)
- Modify: `tools/tft/cli.py` (`_sync`)
- Test: `tests/test_ingest.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `Ingest._meta`, `Overrides` (Task 5).
- Produces: `ingest.SyncResult` (frozen dataclass: `changed: bool`, `warnings: tuple[str, ...]`); `Ingest.sync(slug: str) -> SyncResult`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ingest.py`:

```python
NEXT_SHA = "b7c379a000000000000000000000000000000000"


def _synced(repo, folder, **stub):
    """Re-sync the entry in folder with a moved Overleaf commit."""
    return _ingest(repo, sha=NEXT_SHA, **stub).sync(folder.name)


def test_sync_is_a_noop_when_overleaf_has_not_moved(repo):
    folder = _add(repo, _ingest(repo))

    assert _ingest(repo).sync(folder.name).changed is False


def test_sync_refreshes_the_summary_from_the_abstract(repo):
    folder = _add(repo, _ingest(repo))
    (folder / "summary.md").write_text("Hand-written text.\n")
    moved = ABSTRACT.replace("a \\textbf{database}", "an \\textbf{archive}")

    result = _synced(repo, folder, abstract=moved)

    assert result.changed is True
    assert "archive" in (folder / "summary.md").read_text()


def test_sync_refreshes_keywords(repo):
    folder = _add(repo, _ingest(repo))
    moved = ABSTRACT.replace("biomechanics, Databases.", "gait, Kinematics.")

    _synced(repo, folder, abstract=moved)
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert data["keywords"] == ["gait", "kinematics"]


def test_sync_preserves_human_owned_fields(repo):
    folder = _add(repo, _ingest(repo))
    data = yaml.safe_load((folder / "entry.yaml").read_text())
    data["topics"] = ["biomechanics"]
    data["score"] = 10
    data["honours"] = True
    data["slides"] = "slides.pdf"
    (folder / "entry.yaml").write_text(yaml.safe_dump(data, sort_keys=False))

    _synced(repo, folder)
    after = yaml.safe_load((folder / "entry.yaml").read_text())

    assert after["topics"] == ["biomechanics"]
    assert after["score"] == 10
    assert after["honours"] is True
    assert after["slides"] == "slides.pdf"


def test_sync_warns_but_does_not_rename_on_a_year_change(repo):
    folder = _add(repo, _ingest(repo))
    moved = MAIN.replace("Junio 2027", "Junio 2028")

    result = _synced(repo, folder, main=moved)
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert data["year"] == 2028
    assert folder.name == "2027-nieves-serrano-biomechanics-db"
    assert folder.is_dir()
    assert any("2028" in w for w in result.warnings)
```

`tests/test_cli.py` stubs `Ingest.sync` with a bare `False`, which the new
CLI cannot read. Replace `test_sync_reports_no_change` with:

```python
def test_sync_reports_no_change(repo, monkeypatch, capsys):
    from tft.ingest import SyncResult

    _entry(repo, "2027-x")
    monkeypatch.setattr(
        "tft.ingest.Ingest.sync", lambda self, slug: SyncResult(changed=False),
    )

    assert cli.main(["sync", "2027-x"]) == 0
    assert "unchanged" in capsys.readouterr().out


def test_sync_prints_warnings(repo, monkeypatch, capsys):
    from tft.ingest import SyncResult

    _entry(repo, "2027-x")
    monkeypatch.setattr(
        "tft.ingest.Ingest.sync",
        lambda self, slug: SyncResult(changed=True, warnings=("year is now 2028",)),
    )

    assert cli.main(["sync", "2027-x"]) == 0
    assert "year is now 2028" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ingest.py tests/test_cli.py -v -k sync`
Expected: FAIL with `ImportError: cannot import name 'SyncResult' from 'tft.ingest'`

- [ ] **Step 3: Write minimal implementation**

In `tools/tft/ingest.py`, add beside `Overrides`:

```python
@dataclass(frozen=True)
class SyncResult:
    """What a sync did, and anything the human should look at."""
    changed: bool
    warnings: tuple[str, ...] = ()
```

Replace `Ingest.sync`:

```python
    def sync(self, slug: str) -> SyncResult:
        """Re-pull, re-extract and recompile. Unchanged when Overleaf has not moved."""
        entry = self._catalog.find(slug)

        if entry.overleaf is None:
            raise FileNotFoundError(f"{slug} has no overleaf.project_id to sync")

        project_id = entry.overleaf.project_id
        work = self._cfg.work / project_id
        sha = self._fetch(project_id, work)

        if sha == entry.overleaf.commit:
            return SyncResult(changed=False)

        meta = self._meta(work, Overrides())
        pdf = self._compile(work, entry.overleaf.main)
        folder = self._catalog.dir_for(entry)

        # summary.md is derived from the abstract, so it is rewritten here.
        store.write_summary(folder, meta.abstract)

        refreshed = dataclasses.replace(
            entry, title=meta.title, author=meta.author, year=meta.year,
            degree=meta.degree, keywords=meta.keywords,
        )
        self._install(refreshed, folder, pdf, work, sha, project_id)

        return SyncResult(changed=True, warnings=_year_drift(entry.year, meta.year, slug))
```

Add at module level:

```python
def _year_drift(was: int, now: int, slug: str) -> tuple[str, ...]:
    """The slug embeds the year, but renaming would break shared URLs."""
    if was == now:
        return ()

    return (f"{slug}: year is now {now}; the folder name still says {was}",)
```

In `tools/tft/cli.py`:

```python
def _sync(args) -> int:
    result = _ingest().sync(args.slug)

    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    print(f"{args.slug}: {'updated' if result.changed else 'unchanged'}")

    return 0
```

In `tools/tft/store.py`, correct two now-false docstrings:

```python
def write(dir: Path, entry: Entry) -> None:
    """Write entry.yaml. summary.md is written separately, by write_summary."""
```

```python
def write_summary(dir: Path, text: str) -> None:
    """Write summary.md. Derived from the thesis abstract and rewritten on
    every sync, so hand edits do not survive; the diff is the review."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/tft/ingest.py tools/tft/cli.py tools/tft/store.py tests/test_ingest.py tests/test_cli.py
git commit -m "Re-extract metadata on sync"
```

---

### Task 7: Site — score, keywords and portrait

**Files:**
- Modify: `tools/tft/site.py:28-46` (`record`)
- Modify: `tools/tft/assets/app.js`
- Modify: `tools/tft/templates/entry.html`
- Test: `tests/test_site.py`, `tests/test_app_js.py`

**Interfaces:**
- Consumes: `Entry.keywords`, `Entry.score`, `Entry.honours`, `Entry.photo` (Task 4).
- Produces: three new keys in every `index.json` record — `keywords` (list of str), `score` (number or null), `honours` (bool). `photo` is deliberately **not** in the record: the portrait appears on the entry page only, rendered from the Jinja template.

- [ ] **Step 1: Write the failing test**

In `tests/test_site.py`, extend `FULL` and the golden record, and append the new tests:

```python
FULL = MINIMAL | {
    "supervisors": ["Rodrigo Garcia Carmona"],
    "topics": ["biomechanics", "rehabilitation"],
    "keywords": ["motion capture", "c3d"],
    "score": 10,
    "honours": True,
    "repos": {
        "code": ["https://github.com/ECL-STRAST/libremotion-chloe"],
        "docs": "https://github.com/ECL-STRAST/libremotion-chloe-docs",
    },
    "slides": "slides.pdf",
}
```

In `test_index_json_matches_the_golden_record`, add these three keys to the expected dict, after `"supervisors"`:

```python
        "keywords": ["motion capture", "c3d"],
        "score": 10,
        "honours": True,
```

Append:

```python
def test_entry_without_a_score_has_nulls(repo):
    _entry(repo, "2027-x", MINIMAL)

    record = json.loads((_build(repo) / "index.json").read_text())[0]

    assert record["score"] is None
    assert record["honours"] is False
    assert record["keywords"] == []


def test_entry_page_shows_the_score(repo):
    _entry(repo, "2027-x", FULL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert "10 / 10" in page
    assert "Matrícula de Honor" in page


def test_entry_page_lists_keywords(repo):
    _entry(repo, "2027-x", FULL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert "motion capture" in page


def test_entry_page_shows_the_portrait_when_present(repo):
    folder = _entry(repo, "2027-x", FULL | {"photo": "photo.jpg"})
    (folder / "photo.jpg").write_bytes(b"\xff\xd8\xff")

    out = _build(repo)
    page = (out / "entries" / "2027-x" / "index.html").read_text()

    assert 'src="photo.jpg"' in page
    assert (out / "entries" / "2027-x" / "photo.jpg").is_file()


def test_entry_page_omits_the_portrait_block_when_absent(repo):
    _entry(repo, "2027-x", FULL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert "portrait" not in page
```

Append to `tests/test_app_js.py`:

```python
def test_app_reads_the_score_and_keywords():
    source = APP_JS.read_text()

    assert "e.score" in source
    assert "e.keywords" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_site.py tests/test_app_js.py -v`
Expected: FAIL — the golden-record test reports the three missing keys, and `test_entry_page_shows_the_score` fails on `"10 / 10" not in page`.

- [ ] **Step 3: Write minimal implementation**

In `tools/tft/site.py`, add to the dict returned by `record`, after `"supervisors"`:

```python
        "keywords": list(entry.keywords),
        "score": entry.score,
        "honours": entry.honours,
```

In `_write_entry`, copy the portrait alongside the slides, right after the slides copy:

```python
        if entry.photo:
            shutil.copyfile(source / entry.photo, folder / entry.photo)
```

In `tools/tft/templates/entry.html`, replace the block from `<h1>` through the `topics` paragraph with:

```html
  {% if entry.photo %}
  <img class="portrait" src="{{ entry.photo }}" alt="{{ entry.author }}">
  {% endif %}

  <h1>{{ entry.title }}</h1>
  <p class="meta">
    {{ entry.author }} &middot; {{ entry.year }} &middot; {{ entry.type }}
    {%- if entry.degree %} ({{ entry.degree }}){% endif %}
  </p>

  {% if entry.score is not none %}
  <p><span class="score">{{ entry.score }} / 10{% if entry.honours %}
    &middot; Matrícula de Honor{% endif %}</span></p>
  {% endif %}

  {% if entry.supervisors %}
  <p class="meta">Supervised by {{ entry.supervisors|join(", ") }}</p>
  {% endif %}

  <p class="topics">{% for topic in entry.topics %}<span>{{ topic }}</span>{% endfor %}</p>

  {% if entry.keywords %}
  <p class="keywords">{% for word in entry.keywords %}<span>{{ word }}</span>{% endfor %}</p>
  {% endif %}
```

(Drop the now-duplicated original `<h1>`, `meta`, `supervisors` and `topics` lines.)

In `tools/tft/assets/app.js`, add the badge helper above `card`:

```js
function badge(e) {
  if (e.score == null) return "";
  const honours = e.honours ? " &middot; Matrícula de Honor" : "";
  return `<span class="score">${escape(e.score)} / 10${honours}</span>`;
}
```

and use it in `card`, after the meta paragraph:

```js
function card(e) {
  const degree = e.degree ? ` &middot; ${escape(e.degree)}` : "";
  const topics = e.topics.map((t) => `<span>${escape(t)}</span>`).join("");

  return `<li>
    <a href="${escape(e.url)}">${escape(e.title)}</a>
    <p class="meta">${escape(e.author)} &middot; ${escape(e.year)}${degree}</p>
    ${badge(e)}
    <p>${escape(e.summary)}</p>
    <p class="topics">${topics}</p>
  </li>`;
}
```

and widen the search haystack in `matches`, so a thesis's own vocabulary is searchable:

```js
  const haystack = [e.title, e.author, e.summary, e.topics.join(" "), e.keywords.join(" ")]
    .join(" ").toLowerCase();
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/tft/site.py tools/tft/assets/app.js tools/tft/templates/entry.html tests/test_site.py tests/test_app_js.py
git commit -m "Show score, keywords and portrait on the site"
```

---

### Task 8: ECL theming

**Files:**
- Create: `tools/tft/assets/ecl-logo.png`
- Modify: `tools/tft/assets/style.css`
- Modify: `tools/tft/templates/index.html`
- Modify: `tools/tft/templates/entry.html`
- Test: `tests/test_site.py`

**Interfaces:**
- Consumes: the `.score`, `.keywords` and `.portrait` classes emitted in Task 7.
- Produces: no Python API. The published site gains `assets/ecl-logo.png`, used as both the header mark and the favicon.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_site.py`:

```python
def test_logo_and_favicon_ship_with_the_site(repo):
    _entry(repo, "2027-x", MINIMAL)

    out = _build(repo)

    assert (out / "assets" / "ecl-logo.png").is_file()
    assert 'rel="icon"' in (out / "index.html").read_text()
    assert 'rel="icon"' in (out / "entries" / "2027-x" / "index.html").read_text()


def test_stylesheet_defines_the_ecl_palette(repo):
    _entry(repo, "2027-x", MINIMAL)

    css = (_build(repo) / "assets" / "style.css").read_text()

    for token in ["--ecl-blue: #046ba5", "--ecl-navy: #093d76",
                  "--ecl-teal: #218880", "--ecl-green: #1a6c46"]:
        assert token in css
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_site.py -v -k "logo or palette"`
Expected: FAIL with `assert False` on the missing `ecl-logo.png`.

- [ ] **Step 3: Write minimal implementation**

Fetch the organization avatar and vendor it:

```bash
curl -sL -o tools/tft/assets/ecl-logo.png \
  "https://avatars.githubusercontent.com/u/287655333?s=400&v=4"
```

Verify it is a 400x400 PNG of about 44 KB:

```bash
python -c "
import struct
d = open('tools/tft/assets/ecl-logo.png','rb').read()
print(len(d), 'bytes', struct.unpack('>II', d[16:24]))
"
```

Expected: `44438 bytes (400, 400)`

`site._write_assets` copies every file in `assets/` verbatim, so no Python change is needed.

In `tools/tft/assets/style.css`, replace the `:root` line and append the new rules:

```css
:root {
  --ink: #1a1a1a; --dim: #5a5a5a; --line: #d8d8d8; --bg: #fff;
  /* Sampled from the ECL mark. Teal is 4.29:1 on white, below the 4.5
     AA floor, so it is used in the gradient rule and never for text. */
  --ecl-blue: #046ba5;
  --ecl-navy: #093d76;
  --ecl-teal: #218880;
  --ecl-green: #1a6c46;
}
```

```css
/* Header: the mark, the title, and one gradient hairline echoing it. */
header { display: flex; align-items: center; gap: .75rem; }
header img { width: 36px; height: 36px; }
header h1 { margin: 0; }

.rule {
  height: 3px;
  margin: .75rem 0 0;
  background: linear-gradient(90deg, var(--ecl-blue), var(--ecl-teal), var(--ecl-green));
}

a { color: var(--ecl-blue); }
#results a { color: var(--ecl-blue); }

.score {
  display: inline-block;
  padding: .1rem .5rem;
  border-radius: .2rem;
  background: var(--ecl-green);
  color: #fff;
  font-size: .8rem;
}

/* Honours is the thing that separates two theses that both scored 10. */
.score.honours { background: var(--ecl-navy); }

.portrait {
  float: right;
  width: 72px;
  height: 72px;
  margin: 0 0 .75rem .75rem;
  border-radius: 50%;
  object-fit: cover;
}

/* Keywords are the thesis's own words and are not filterable, so they
   read flatter than the topic pills, which are. */
.keywords span {
  display: inline-block;
  margin: 0 .4rem .3rem 0;
  font-size: .8rem;
  color: var(--dim);
}
```

In `tools/tft/templates/index.html`, add the favicon link in `<head>`:

```html
<link rel="icon" href="assets/ecl-logo.png">
```

and replace the `<header>` block:

```html
<header>
  <img src="assets/ecl-logo.png" alt="Embodied Computing Lab">
  <h1>Theses &amp; publications</h1>
</header>
<div class="rule"></div>
<p>{{ entries|length }} entries from the research group.</p>
```

In `tools/tft/templates/entry.html`, add in `<head>`:

```html
<link rel="icon" href="../../assets/ecl-logo.png">
```

and apply the honours class to the badge added in Task 7:

```html
  {% if entry.score is not none %}
  <p><span class="score{% if entry.honours %} honours{% endif %}">{{ entry.score }} / 10{% if entry.honours %}
    &middot; Matrícula de Honor{% endif %}</span></p>
  {% endif %}
```

In `tools/tft/assets/app.js`, apply the same class in `badge`:

```js
function badge(e) {
  if (e.score == null) return "";
  const honours = e.honours ? " &middot; Matrícula de Honor" : "";
  const cls = e.honours ? "score honours" : "score";
  return `<span class="${cls}">${escape(e.score)} / 10${honours}</span>`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -v`
Expected: PASS

- [ ] **Step 5: Look at it**

Run:

```bash
tft build && python -m http.server -d site 8000
```

Open `http://localhost:8000/`. Confirm: the mark sits left of the title, the gradient hairline runs beneath the header, links are ECL blue, and the page has no horizontal scroll at phone width. Stop the server with Ctrl-C.

- [ ] **Step 6: Commit**

```bash
git add tools/tft/assets/ecl-logo.png tools/tft/assets/style.css tools/tft/assets/app.js tools/tft/templates/index.html tools/tft/templates/entry.html tests/test_site.py
git commit -m "Theme the site with the ECL mark and palette"
```

---

### Task 9: Documentation and migration

**Files:**
- Modify: `README.md`
- Modify: `content/theses/2026-gomez-martinez-biomechanics-viz/entry.yaml` (by running `tft sync`)
- Modify: `content/theses/2026-gomez-martinez-biomechanics-viz/summary.md` (same)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing further depends on this task.

- [ ] **Step 1: Update the README**

Replace the "Adding an entry" section with:

```markdown
## Adding an entry

    tft add --overleaf <project-id> --name nieves-serrano-biomechanics-db

Title, author, year, degree, summary and keywords are read from the LaTeX
source. The year becomes the slug's prefix, so the entry lands in
`content/theses/<year>-<name>/`.

Extraction reads the group's template: `\tfgtitle`, `\authorname` and
`\fecha` in `main.tex`, the cover phrase (`TRABAJO FIN DE GRADO`,
`... DE MÁSTER`, `TESIS DOCTORAL`), and the chapter holding
`\chapter*{Abstract}` with its `\textbf{Keywords:}` line. A field it
cannot find aborts the command by name; `--title`, `--author`, `--year`
and `--degree` supply one by hand for a thesis built on another template.

Then replace the `CHANGE-ME` topic with tags from `taxonomy/topics.yaml`,
adding any missing tag to that file first. Topics are curated and drive
the site's filter; the extracted `keywords` are the thesis's own words,
are displayed but never filtered, and are not checked against the
vocabulary. Finally:

    tft validate

`validate` checks schema, topics, referenced files, and repo URL syntax.
It never checks that a URL is reachable: CI holds no secrets and reaches
nothing, and group repos may be private.

Entries may be added before the work is defended: a draft PDF, no attached
repositories and no slides are all valid.

### Fields you fill in by hand

| Field | Notes |
|---|---|
| `topics` | from `taxonomy/topics.yaml`; the only filter facet |
| `score` | 0 to 10 |
| `honours` | `true` for Matrícula de Honor; needs a `score` |
| `photo` | a file in the entry folder, e.g. `photo.jpg` |
| `repos`, `slides`, `supervisors` | as before |

A student's portrait is personal data. Get their written consent before
committing one, and note that removing it later means rewriting this
repository's history.

### Keeping an entry current

    tft sync <slug>

Re-pulls from Overleaf, recompiles, and re-reads the metadata.
`summary.md` is **derived from the abstract and is rewritten on every
sync** — do not hand-edit it; edit the thesis. Your own fields (`topics`,
`score`, `honours`, `photo`, `repos`, `slides`) are preserved. If the
thesis's year changes, `sync` updates the field and warns, but does not
rename the folder: the slug is an identifier and shared URLs must keep
working.
```

- [ ] **Step 2: Commit the documentation**

```bash
git add README.md
git commit -m "Document metadata extraction and manual fields"
```

- [ ] **Step 3: Run the migration**

This needs `OVERLEAF_GIT_TOKEN` and a working TeX install.

```bash
set -a && . ./.env && set +a
tft sync 2026-gomez-martinez-biomechanics-viz
```

Expected: `2026-gomez-martinez-biomechanics-viz: updated`, or `unchanged` if the Overleaf commit has not moved since `919a437`. **If it reports `unchanged`, the backfill did not happen** — sync returns early before extracting. In that case temporarily clear the recorded commit to force a pass:

```bash
python - <<'EOF'
import yaml, pathlib
p = pathlib.Path("content/theses/2026-gomez-martinez-biomechanics-viz/entry.yaml")
d = yaml.safe_load(p.read_text())
d["overleaf"].pop("commit", None)
p.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True))
EOF
tft sync 2026-gomez-martinez-biomechanics-viz
```

- [ ] **Step 4: Review the migration diff**

```bash
git diff --stat
git diff content/theses/2026-gomez-martinez-biomechanics-viz/
```

Confirm: `keywords` now lists the eight terms from the thesis; `summary.md` holds the five-paragraph abstract; `topics` still reads `biomechanics, rehabilitation, signal-processing`; `overleaf.commit` is restored to a real SHA.

- [ ] **Step 5: Validate and build**

```bash
tft validate && tft build
```

Expected: `ok`, then `built .../site`

- [ ] **Step 6: Commit the migration**

```bash
git add content/theses/2026-gomez-martinez-biomechanics-viz/
git commit -m "Backfill keywords and summary from the thesis"
```

---

## Self-Review

**Spec coverage.** Every spec section maps to a task: the extractor (Tasks 1-3), landmarks and de-TeXing (Tasks 2-3), failure behaviour and call order and the interface change (Task 5), sync (Task 6), schema and its four fields (Task 4), migration (Task 9), site record and `app.js` and the entry page (Task 7), theme and contrast (Task 8), README note on consent (Task 9). The spec's "out of scope" item (`language`) is implemented nowhere, as intended.

**Type consistency.** `tex.Meta` fields are named `title, author, year, degree, abstract, keywords` in Tasks 1, 3, 5 and 6. `Overrides` shares the first four names, which is what makes `dataclasses.replace(found, **supplied)` work in Task 5. `SyncResult.changed`/`.warnings` are used identically in Tasks 6 and the CLI. The `.score`, `.keywords` and `.portrait` CSS classes emitted in Task 7 are exactly the ones styled in Task 8.

**Placeholder scan.** No TBDs, no "similar to Task N", no "add error handling". Every code step carries the code. Two ambiguities found and fixed during review: a duplicated `_meta` draft in Task 5 (only the `_remedy` version remains), and a vague "update `test_cli.py` if needed" (Tasks 5 and 6 now spell out every replacement, since four existing CLI tests stub `Ingest.add`/`Ingest.sync` with signatures this work changes).

**Commit health.** Every task's suite run is green at its commit. `sync` is untouched until Task 6, so `test_sync_reports_no_change` keeps passing through Task 5 and is rewritten in Task 6 alongside the code that breaks it.
