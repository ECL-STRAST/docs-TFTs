# Programme, Media and Entry Header Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derive the degree programme and the supervisor list from the thesis cover, let an entry carry a thesis image and a thesis video, and give the entry page the ECL header the index page already has.

**Architecture:** `tex.py` gains two readers. `degree()` is refactored into a private `_cover()` that returns both the degree and the file that names it, so the programme is read only from the cover file and never from body prose. `entry.py` gains three optional fields; `video` is validated by parsing the URL into a `(host, id)` pair, and the `iframe` src is built from the id and a hard-coded host base, so a stored URL never reaches the page. The layer chain stays `cli -> ingest -> tex` and `cli -> site -> catalog -> store -> entry`.

**Tech Stack:** Python 3.11+, stdlib `re` and `unicodedata` only (no new dependency), PyYAML, Jinja2, markdown, pytest.

**Spec:** `docs/superpowers/specs/2026-09-18-programme-media-and-entry-header-design.md`

## Global Constraints

- No new runtime dependency. `pyproject.toml` stays at `PyYAML>=6`, `Jinja2>=3.1`, `markdown>=3.5`.
- All three new `entry.yaml` fields (`programme`, `image`, `video`) go in `OPTIONAL`, never `MANDATORY`. The existing entry `content/theses/2026-gomez-martinez-biomechanics-viz/entry.yaml` must keep validating untouched at every commit.
- `programme` is not in `REQUIRED_BY_TYPE`. A thesis on another template has no programme, and `None` is not an error. There is no `--programme` CLI flag.
- `supervisors` becomes **derived**. The amended sync-preserves list is `topics`, `score`, `honours`, `photo`, `image`, `video`, `repos`, `slides`.
- Allowed video hosts and nothing else: `https://www.youtube.com/watch?v=<id>`, `https://youtu.be/<id>` (id `[A-Za-z0-9_-]+`), `https://vimeo.com/<digits>`. Anything else is a `BadValue` naming the field.
- The stored video URL is never interpolated into the `iframe` src.
- Neither `image` nor `video` enters `index.json`. `programme` does.
- Colour tokens, exact values, already in `style.css`: `--ecl-blue: #046ba5`, `--ecl-navy: #093d76`, `--ecl-teal: #218880`, `--ecl-green: #1a6c46`. Teal is decoration only and must never colour text.
- Entry-page asset paths are two levels up (`../../assets/...`).
- Follow the repo's house style: `{}` on every `if`, early returns over nesting, blank lines between logical blocks, short names, comments saying *what and why*.
- Commit messages: imperative subject, <=50 characters, capitalised, no trailing period; blank line; body wrapped at 72 explaining what and why. End every commit message with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EuibbPeJjCmTkocMTTgQkk
```

- Run the whole suite before each commit: `python -m pytest -q`. If `python` is not on `PATH`, the repo's virtualenv is at `.venv`: use `.venv/bin/python -m pytest -q` and `.venv/bin/tft` throughout.

## Notes on spec deviations

Two, both small, both worth the reviewer's eye:

1. **`Video.embed`.** The spec says "the template builds the embed URL from the id alone". The plan puts a one-line `embed` property on the `Video` dataclass, next to the host allowlist it belongs to, and the template writes `src="{{ video.embed }}"`. Same security property — the URL is built from a hard-coded base plus a charset-restricted id — but the host table has one owner instead of two. If you would rather match the spec literally, branch on `video.host` in the template and delete the property.
2. **`supervisors` has no value validator.** The spec's schema table says its validation is "unchanged: non-empty strings", but no such check exists today: `tuple(data.get("supervisors", ()))` would turn a bare string into a tuple of characters. This plan does not add one — the ownership change does not change validation, and the field is now written by `sync` rather than by hand. Flagged, not fixed.

---

### Task 1: `tex` reads the programme and the supervisors

**Files:**
- Modify: `tools/tft/tex.py`
- Test: `tests/test_tex.py`

**Interfaces:**
- Consumes: `tft.tex.macro`, `tft.tex.detex`, `tft.tex.fold`, `tft.errors.ExtractError` (all already present).
- Produces: `tft.tex.Meta` gains `programme: str | None` and `supervisors: tuple[str, ...]`, both without defaults, so the full field order is `title, author, year, degree, programme, supervisors, abstract, keywords`. `tex.degree(src: Path) -> str | None` keeps its signature, its value and its `ExtractError` on ambiguity.

- [ ] **Step 1: Write the failing tests**

In `tests/test_tex.py`, replace the existing `test_meta_is_frozen` with this version (the two new fields have no defaults, so the old call no longer constructs):

```python
def test_meta_is_frozen():
    meta = tex.Meta(
        title="t", author="a", year=2026, degree="bachelor",
        programme="GRADO EN INGENIERÍA BIOMÉDICA", supervisors=("R. García",),
        abstract="text", keywords=("gait",),
    )

    with pytest.raises(AttributeError):
        meta.title = "other"
```

Replace the existing `FULL_MAIN` constant with one that also declares a supervisor (the cover lines stay where they are):

```python
FULL_MAIN = r"""
\newcommand{\authorname}{Belén Gómez Martínez}
\newcommand{\tfgtitle}{Design and development of an environment}
\newcommand{\supervisor}{Rodrigo García Carmona}
\newcommand{\fecha}{Junio 2026}
TRABAJO FIN DE GRADO
"""
```

Then append the new tests at the end of the file:

```python
COVER = r"""
\begin{center}
    {\Large\rm \textbf{ GRADO EN INGENIERÍA BIOMÉDICA}} \\
    \vspace{2.0cm}
    {\Large\rm \textbf{TRABAJO FIN DE GRADO}} \\
\end{center}
"""


def test_programme_is_read_from_the_cover_with_its_accents(tmp_path):
    src = _tree(tmp_path, **{"main.tex": FULL_MAIN, "chapters/0-preamble.tex": COVER})

    assert tex.read(src).programme == "GRADO EN INGENIERÍA BIOMÉDICA"


def test_master_programme_is_read(tmp_path):
    cover = "MÁSTER EN INGENIERÍA BIOMÉDICA\nTRABAJO FIN DE MÁSTER\n"
    src = _tree(tmp_path, **{"main.tex": cover})

    assert tex.read(src).programme == "MÁSTER EN INGENIERÍA BIOMÉDICA"


def test_no_programme_on_the_cover_is_none(tmp_path):
    src = _tree(tmp_path, **{"main.tex": "TRABAJO FIN DE GRADO"})

    assert tex.read(src).programme is None


def test_no_cover_at_all_is_no_programme(tmp_path):
    src = _tree(tmp_path, **{"main.tex": "nothing relevant here"})

    assert tex.read(src).programme is None


def test_two_programmes_on_the_cover_are_ambiguous(tmp_path):
    cover = (
        "GRADO EN INGENIERÍA BIOMÉDICA\n"
        "GRADO EN INGENIERÍA DE SISTEMAS\n"
        "TRABAJO FIN DE GRADO\n"
    )
    src = _tree(tmp_path, **{"main.tex": cover})

    with pytest.raises(ExtractError, match="ambiguous"):
        tex.read(src)


def test_the_same_programme_twice_is_not_ambiguous(tmp_path):
    cover = "GRADO EN INGENIERÍA BIOMÉDICA\nTRABAJO FIN DE GRADO\nGrado en Ingeniería Biomédica\n"
    src = _tree(tmp_path, **{"main.tex": cover})

    assert tex.read(src).programme == "GRADO EN INGENIERÍA BIOMÉDICA"


def test_body_prose_outside_the_cover_is_not_a_programme(tmp_path):
    # The pattern is case-insensitive, so "el grado en ..." in a chapter
    # would match; only the file carrying the degree phrase is searched.
    src = _tree(
        tmp_path,
        **{
            "main.tex": "TRABAJO FIN DE GRADO",
            "chapters/1-intro.tex": "Durante el grado en ingeniería de sistemas se estudia...",
        },
    )

    assert tex.read(src).programme is None


def test_supervisors_split_on_commas(tmp_path):
    main = r"\newcommand{\supervisor}{Rodrigo García Carmona, Ana Pérez Ruiz}"
    src = _tree(tmp_path, **{"main.tex": main})

    assert tex.read(src).supervisors == ("Rodrigo García Carmona", "Ana Pérez Ruiz")


def test_supervisors_split_on_newlines_and_latex_line_breaks(tmp_path):
    main = "\\newcommand{\\supervisor}{Rodrigo García Carmona \\\\\nAna Pérez Ruiz}"
    src = _tree(tmp_path, **{"main.tex": main})

    assert tex.read(src).supervisors == ("Rodrigo García Carmona", "Ana Pérez Ruiz")


def test_one_supervisor_is_a_one_element_tuple(tmp_path):
    src = _tree(tmp_path, **{"main.tex": r"\newcommand{\supervisor}{Rodrigo García Carmona}"})

    assert tex.read(src).supervisors == ("Rodrigo García Carmona",)


def test_supervisor_names_are_de_texed(tmp_path):
    main = r"\newcommand{\supervisor}{\textbf{Rodrigo} García Carmona}"
    src = _tree(tmp_path, **{"main.tex": main})

    assert tex.read(src).supervisors == ("Rodrigo García Carmona",)


def test_no_supervisor_macro_yields_an_empty_tuple(tmp_path):
    src = _tree(tmp_path, **{"main.tex": "TRABAJO FIN DE GRADO"})

    assert tex.read(src).supervisors == ()


def test_degree_value_and_error_survive_the_cover_refactor(tmp_path):
    src = _tree(tmp_path, **{"chapters/0-preamble.tex": "TRABAJO FIN DE GRADO"})

    assert tex.degree(src) == "bachelor"
```

Also extend the existing `test_missing_pieces_are_none_not_errors` with two assertions:

```python
    assert meta.programme is None
    assert meta.supervisors == ()
```

and the existing `test_read_without_a_main_tex_returns_all_none` with the same two.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_tex.py -q`
Expected: FAIL — `TypeError: Meta.__init__() got an unexpected keyword argument 'programme'` and `AttributeError: 'Meta' object has no attribute 'programme'`.

- [ ] **Step 3: Add the two patterns and the supervisor macro name**

In `tools/tft/tex.py`, below the existing `DEGREES` tuple, add:

```python
# The programme sits immediately above the degree phrase on the ETSIT
# cover. Matched against the ORIGINAL text, not the accent-folded text
# used for the degree, so "INGENIERÍA BIOMÉDICA" keeps its accents.
PROGRAMME = re.compile(r"(?:GRADO|M[ÁA]STER)\s+EN\s+([^\\}\n]+)", re.IGNORECASE)
```

Beside `DATE_MACRO`, add:

```python
SUPERVISOR_MACRO = "supervisor"
```

and beside `PROGRAMME`, add:

```python
# \supervisor holds the whole list, however the student separated it.
SUPERVISOR_SPLIT = re.compile(r",|\\\\|\n")
```

- [ ] **Step 4: Widen `Meta`**

Replace the `Meta` dataclass body with:

```python
@dataclass(frozen=True)
class Meta:
    """What a LaTeX source tree says about itself. None means not found."""
    title: str | None
    author: str | None
    year: int | None
    degree: str | None
    programme: str | None
    supervisors: tuple[str, ...]
    abstract: str | None
    keywords: tuple[str, ...]
```

- [ ] **Step 5: Refactor `degree` so the cover file is available**

Replace the whole existing `degree` function with:

```python
def degree(src: Path) -> str | None:
    """The degree named on the cover, or None when no phrase appears."""
    return _cover(src)[0]


def _cover(src: Path) -> tuple[str | None, Path | None]:
    """The degree named on the cover, and the file that names it.

    The file is what scopes the programme search: the programme belongs
    on the cover, and the cover is whatever file carries the phrase.
    """
    found: dict[str, Path] = {}

    for path in sorted(src.rglob(TEX_GLOB)):
        text = fold(path.read_text(encoding="utf-8", errors="ignore"))

        for pattern, name in DEGREES:
            if pattern.search(text):
                found.setdefault(name, path)

    # Two different phrases means a stray citation, not a second degree.
    if len(found) > 1:
        raise ExtractError(f"degree is ambiguous ({', '.join(sorted(found))}); pass --degree")

    if not found:
        return None, None

    name = next(iter(found))

    return name, found[name]
```

- [ ] **Step 6: Add the two readers**

Append to `tools/tft/tex.py`, after `_cover`:

```python
def _programme(path: Path | None) -> str | None:
    """The degree programme named on the cover file, accents intact."""
    if path is None:
        return None

    text = path.read_text(encoding="utf-8", errors="ignore")
    found: dict[str, str] = {}

    # Keyed on the folded phrase so "GRADO EN X" and "Grado en X" are one.
    for match in PROGRAMME.finditer(text):
        phrase = " ".join(match.group().split())
        found.setdefault(fold(phrase), phrase)

    if len(found) > 1:
        raise ExtractError(f"programme is ambiguous ({', '.join(sorted(found.values()))})")

    return next(iter(found.values()), None)


def _supervisors(main: str) -> tuple[str, ...]:
    """Every name in \\supervisor, comma-, newline- or \\\\-separated."""
    raw = macro(main, SUPERVISOR_MACRO)

    if raw is None:
        return ()

    names = [detex(part).strip() for part in SUPERVISOR_SPLIT.split(raw)]

    return tuple(name for name in names if name)
```

- [ ] **Step 7: Wire them into `read`**

Replace the body of `read` with:

```python
def read(src: Path) -> Meta:
    """Everything the source tree declares about itself."""
    path = src / MAIN_FILE
    main = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
    abstract, keywords = _abstract(src)
    year = YEAR.search(macro(main, DATE_MACRO) or "")
    named, cover = _cover(src)

    return Meta(
        title=macro(main, TITLE_MACRO),
        author=macro(main, AUTHOR_MACRO),
        year=int(year.group()) if year else None,
        degree=named,
        programme=_programme(cover),
        supervisors=_supervisors(main),
        abstract=abstract,
        keywords=keywords,
    )
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python -m pytest tests/test_tex.py -q`
Expected: PASS, all of them.

- [ ] **Step 9: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS. `tex.Meta` is constructed only by `tex.read`, so nothing else should break; if `test_ingest.py` fails, a construction site was missed.

- [ ] **Step 10: Commit**

```bash
git add tools/tft/tex.py tests/test_tex.py
git commit -m "Read the programme and supervisors from the cover"
```

Body: the programme is searched only in the file carrying the degree
phrase, because the pattern is case-insensitive and body prose would
otherwise match; `degree()` keeps its value and its error.

---

### Task 2: Schema — `programme`, `image` and `video`

**Files:**
- Modify: `tools/tft/entry.py`
- Test: `tests/test_entry.py`

**Interfaces:**
- Consumes: `tft.errors.BadValue`.
- Produces: `Entry` gains `programme: str | None = None`, `image: str | None = None`, `video: str | None = None`. New public names in `tft.entry`: `Video` (frozen dataclass, `host: str`, `id: str`, property `embed: str`), `parse_video(url: str | None) -> Video | None`, constants `YOUTUBE = "youtube"` and `VIMEO = "vimeo"`. `OPTIONAL` gains the three field names.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_entry.py`:

```python
YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
SHORT_URL = "https://youtu.be/dQw4w9WgXcQ"
VIMEO_URL = "https://vimeo.com/76979871"


def test_programme_round_trips():
    data = MINIMAL | {"programme": "GRADO EN INGENIERÍA BIOMÉDICA"}

    parsed = entry.from_dict("2027-x", data)

    assert parsed.programme == "GRADO EN INGENIERÍA BIOMÉDICA"
    assert entry.to_dict(parsed) == data


def test_absent_programme_is_none():
    assert entry.from_dict("2027-x", MINIMAL).programme is None


def test_programme_must_be_a_non_empty_string():
    with pytest.raises(BadValue, match="programme"):
        entry.from_dict("2027-x", MINIMAL | {"programme": "  "})


def test_programme_must_be_a_string():
    with pytest.raises(BadValue, match="programme"):
        entry.from_dict("2027-x", MINIMAL | {"programme": 7})


def test_image_and_video_round_trip():
    data = MINIMAL | {"image": "cover.png", "video": YOUTUBE_URL}

    parsed = entry.from_dict("2027-x", data)

    assert parsed.image == "cover.png"
    assert parsed.video == YOUTUBE_URL
    assert entry.to_dict(parsed) == data


def test_absent_image_and_video_are_none():
    parsed = entry.from_dict("2027-x", MINIMAL)

    assert parsed.image is None
    assert parsed.video is None


def test_image_must_be_a_string():
    with pytest.raises(BadValue, match="image"):
        entry.from_dict("2027-x", MINIMAL | {"image": 123})


def test_image_must_not_be_blank():
    with pytest.raises(BadValue, match="image"):
        entry.from_dict("2027-x", MINIMAL | {"image": "  "})


def test_image_must_not_traverse_out_of_the_entry():
    with pytest.raises(BadValue, match="image"):
        entry.from_dict("2027-x", MINIMAL | {"image": "../../secret.png"})


@pytest.mark.parametrize("url,host,id", [
    (YOUTUBE_URL, entry.YOUTUBE, "dQw4w9WgXcQ"),
    ("https://youtube.com/watch?v=dQw4w9WgXcQ", entry.YOUTUBE, "dQw4w9WgXcQ"),
    (SHORT_URL, entry.YOUTUBE, "dQw4w9WgXcQ"),
    (VIMEO_URL, entry.VIMEO, "76979871"),
])
def test_video_accepts_each_allowed_form(url, host, id):
    parsed = entry.from_dict("2027-x", MINIMAL | {"video": url})

    assert parsed.video == url
    assert entry.parse_video(url) == entry.Video(host=host, id=id)


@pytest.mark.parametrize("url", [
    "https://evil.example.com/watch?v=dQw4w9WgXcQ",
    "javascript:alert(1)",
    "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30",
    "https://vimeo.com/not-a-number",
    "https://www.youtube.com/watch?v=",
    "dQw4w9WgXcQ",
])
def test_video_rejects_anything_else(url):
    with pytest.raises(BadValue, match="video"):
        entry.from_dict("2027-x", MINIMAL | {"video": url})


def test_video_must_be_a_string():
    with pytest.raises(BadValue, match="video"):
        entry.from_dict("2027-x", MINIMAL | {"video": 42})


def test_embed_url_is_built_from_the_id_alone():
    assert entry.parse_video(YOUTUBE_URL).embed == "https://www.youtube.com/embed/dQw4w9WgXcQ"
    assert entry.parse_video(VIMEO_URL).embed == "https://player.vimeo.com/video/76979871"


def test_parse_video_of_nothing_is_none():
    assert entry.parse_video(None) is None
    assert entry.parse_video("javascript:alert(1)") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_entry.py -q`
Expected: FAIL — `UnknownField: unknown field: programme`, and `AttributeError: module 'tft.entry' has no attribute 'parse_video'`.

- [ ] **Step 3: Add the video allowlist**

In `tools/tft/entry.py`, add `import re` at the top of the import block, and add after the `DEGREES` tuple:

```python
YOUTUBE = "youtube"
VIMEO = "vimeo"

# The only URL shapes an entry.yaml may name, and the id each yields.
# entry.yaml is repo content arriving through pull requests, so the
# stored URL is parsed, never interpolated into the iframe src.
VIDEO_URLS = (
    (re.compile(r"^https://(?:www\.)?youtube\.com/watch\?v=([A-Za-z0-9_-]+)$"), YOUTUBE),
    (re.compile(r"^https://youtu\.be/([A-Za-z0-9_-]+)$"), YOUTUBE),
    (re.compile(r"^https://(?:www\.)?vimeo\.com/(\d+)$"), VIMEO),
)

EMBED = {
    YOUTUBE: "https://www.youtube.com/embed/",
    VIMEO: "https://player.vimeo.com/video/",
}
```

- [ ] **Step 4: Add `Video` and `parse_video`**

Add the dataclass above `Overleaf`:

```python
@dataclass(frozen=True)
class Video:
    host: str
    id: str

    @property
    def embed(self) -> str:
        """Built from a fixed base and the id: the stored URL never reaches the page."""
        return EMBED[self.host] + self.id
```

and the parser beside the other module-level helpers, just above `_overleaf`:

```python
def parse_video(url: str | None) -> Video | None:
    """The host and id behind an allowed video URL, else None."""
    if not isinstance(url, str):
        return None

    for pattern, host in VIDEO_URLS:
        match = pattern.match(url)

        if match:
            return Video(host=host, id=match.group(1))

    return None
```

- [ ] **Step 5: Widen the schema and the validators**

Add the three names to `OPTIONAL`:

```python
OPTIONAL = (
    "degree", "programme", "venue", "supervisors", "overleaf", "repos",
    "slides", "keywords", "score", "honours", "photo", "image", "video",
)
```

Add the three fields to `Entry`, `programme` after `degree`, `image` and `video` after `photo`:

```python
    degree: str | None = None
    programme: str | None = None
```

```python
    photo: str | None = None
    image: str | None = None
    video: str | None = None
```

Split the blank-string check out of `_check_filename` so `programme` can reuse it, and add the video check:

```python
def _check_text(data: dict, name: str) -> None:
    """A present optional string must actually carry something."""
    value = data.get(name)

    if value is None:
        return

    if not isinstance(value, str) or not value.strip():
        raise BadValue(f"{name} must be a non-empty string")


def _check_filename(data: dict, name: str) -> None:
    """A declared file (photo, slides, image) must be a bare name in the folder."""
    _check_text(data, name)
    value = data.get(name)

    if value is None:
        return

    if "/" in value or "\\" in value or ".." in value:
        raise BadValue(f"{name} must not contain a path separator")


def _check_video(data: dict) -> None:
    """A video is a URL on an allowed host, parseable to an id."""
    if "video" not in data:
        return

    if parse_video(data["video"]) is None:
        raise BadValue(f"video must be a YouTube or Vimeo URL, got {data['video']!r}")
```

In `from_dict`, extend the check block and the constructor:

```python
    _check_types(data)
    _check_score(data)
    _check_keywords(data)
    _check_text(data, "programme")
    _check_filename(data, "photo")
    _check_filename(data, "slides")
    _check_filename(data, "image")
    _check_video(data)
```

```python
        degree=data.get("degree"),
        programme=data.get("programme"),
```

```python
        photo=data.get("photo"),
        image=data.get("image"),
        video=data.get("video"),
```

In `to_dict`, add `programme` beside `degree` and the media beside `photo`:

```python
    _put(out, "degree", entry.degree)
    _put(out, "programme", entry.programme)
    _put(out, "venue", entry.venue)
```

```python
    _put(out, "photo", entry.photo)
    _put(out, "image", entry.image)
    _put(out, "video", entry.video)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_entry.py -q`
Expected: PASS.

- [ ] **Step 7: Confirm the live entry still validates**

Run: `python -m pytest -q && python -m tft.cli validate`

If `python -m tft.cli` is not runnable, use the installed console script: `tft validate`.
Expected: the suite passes and `validate` reports no problems.

- [ ] **Step 8: Commit**

```bash
git add tools/tft/entry.py tests/test_entry.py
git commit -m "Add programme, image and video to the schema"
```

Body: a video URL is parsed into a host and an id and rejected if it is
neither YouTube nor Vimeo, because entry.yaml is repo content and an
interpolated src would accept any origin and any scheme.

---

### Task 3: `ingest` and `catalog` carry the derived fields

**Files:**
- Modify: `tools/tft/catalog.py`
- Modify: `tools/tft/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `tex.Meta.programme`, `tex.Meta.supervisors` (Task 1); `Entry.programme` (Task 2).
- Produces: `Catalog.create(slug, type, year, title, author, degree=None, programme=None, supervisors=(), keywords=(), summary=STUB_SUMMARY) -> Path`. `Ingest.sync` now overwrites `programme` and `supervisors` from the source on every sync.

- [ ] **Step 1: Write the failing tests**

In `tests/test_ingest.py`, replace the `MAIN` constant with one carrying a cover programme and a two-name supervisor macro:

```python
MAIN = r"""
\newcommand{\authorname}{Silvia Nieves Serrano}
\newcommand{\tfgtitle}{A database for biomechanical data}
\newcommand{\supervisor}{Rodrigo García Carmona, Ana Pérez Ruiz}
\newcommand{\fecha}{Junio 2027}
GRADO EN INGENIERÍA BIOMÉDICA
TRABAJO FIN DE GRADO
\documentclass{article}
\begin{document}x\end{document}
"""
```

Extend `test_sync_preserves_human_owned_fields` to cover the two new human-owned fields:

```python
def test_sync_preserves_human_owned_fields(repo):
    folder = _add(repo, _ingest(repo))
    data = yaml.safe_load((folder / "entry.yaml").read_text())
    data["topics"] = ["biomechanics"]
    data["score"] = 10
    data["honours"] = True
    data["slides"] = "slides.pdf"
    data["image"] = "cover.png"
    data["video"] = "https://vimeo.com/76979871"
    (folder / "entry.yaml").write_text(yaml.safe_dump(data, sort_keys=False))

    _synced(repo, folder)
    after = yaml.safe_load((folder / "entry.yaml").read_text())

    assert after["topics"] == ["biomechanics"]
    assert after["score"] == 10
    assert after["honours"] is True
    assert after["slides"] == "slides.pdf"
    assert after["image"] == "cover.png"
    assert after["video"] == "https://vimeo.com/76979871"
```

Append the new tests:

```python
def test_add_records_the_programme_and_supervisors(repo):
    folder = _add(repo, _ingest(repo))
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert data["programme"] == "GRADO EN INGENIERÍA BIOMÉDICA"
    assert data["supervisors"] == ["Rodrigo García Carmona", "Ana Pérez Ruiz"]


def test_add_without_a_programme_omits_the_field(repo):
    main = MAIN.replace("GRADO EN INGENIERÍA BIOMÉDICA\n", "")
    folder = _add(repo, _ingest(repo, main=main))
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert "programme" not in data


def test_sync_backfills_the_programme_and_supervisors(repo):
    folder = _add(repo, _ingest(repo))
    data = yaml.safe_load((folder / "entry.yaml").read_text())
    del data["programme"]
    del data["supervisors"]
    (folder / "entry.yaml").write_text(yaml.safe_dump(data, sort_keys=False))

    _synced(repo, folder)
    after = yaml.safe_load((folder / "entry.yaml").read_text())

    assert after["programme"] == "GRADO EN INGENIERÍA BIOMÉDICA"
    assert after["supervisors"] == ["Rodrigo García Carmona", "Ana Pérez Ruiz"]


def test_sync_overwrites_hand_entered_supervisors(repo):
    # supervisors is derived now: the \supervisor macro is the whole list,
    # so a re-sync replacing it cannot lose a co-supervisor.
    folder = _add(repo, _ingest(repo))
    moved = MAIN.replace(
        "Rodrigo García Carmona, Ana Pérez Ruiz", "Rodrigo García Carmona",
    )

    _synced(repo, folder, main=moved)
    after = yaml.safe_load((folder / "entry.yaml").read_text())

    assert after["supervisors"] == ["Rodrigo García Carmona"]


def test_a_publication_gets_no_programme(repo):
    bare = "\\documentclass{article}\\begin{document}x\\end{document}"
    ingest = _ingest(repo, main=bare, abstract=None)

    folder = ingest.add(
        project_id=PROJECT, name="garcia-paper",
        overrides=Overrides(title="A Paper", author="X. Garcia", year=2027),
        type=PUBLICATION,
    )
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert "programme" not in data
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_ingest.py -q`
Expected: FAIL — `KeyError: 'programme'` in `test_add_records_the_programme_and_supervisors`, and `supervisors` absent from the written YAML.

- [ ] **Step 3: Widen `Catalog.create`**

In `tools/tft/catalog.py`, replace the signature and the stub-building block:

```python
    def create(self, slug, type, year, title, author, degree=None,
               programme=None, supervisors=(), keywords=(), summary=STUB_SUMMARY) -> Path:
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

        if programme is not None:
            data["programme"] = programme

        if supervisors:
            data["supervisors"] = list(supervisors)

        if keywords:
            data["keywords"] = list(keywords)

        store.write(folder, from_dict(slug, data))
        store.write_summary(folder, summary)

        return folder
```

- [ ] **Step 4: Pass the derived fields through `ingest`**

In `tools/tft/ingest.py`, extend the `create` call inside `add`:

```python
        folder = self._catalog.create(
            slug=slug, type=type, year=meta.year, title=meta.title,
            author=meta.author, degree=_degree_for(type, meta),
            programme=meta.programme, supervisors=meta.supervisors,
            keywords=meta.keywords, summary=meta.abstract or STUB_SUMMARY,
        )
```

and the `replace` call inside `sync`:

```python
        refreshed = dataclasses.replace(
            entry, title=meta.title, author=meta.author, year=meta.year,
            degree=_degree_for(entry.type, meta), programme=meta.programme,
            supervisors=meta.supervisors, keywords=meta.keywords,
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_ingest.py -q`
Expected: PASS.

- [ ] **Step 6: Run the whole suite and commit**

Run: `python -m pytest -q`
Expected: PASS.

```bash
git add tools/tft/catalog.py tools/tft/ingest.py tests/test_ingest.py
git commit -m "Derive the programme and supervisors on ingest"
```

Body: supervisors moves from human-owned to derived, amending the
sync-preserves list in the 2026-09-17 spec. Safe because \supervisor
holds the whole list, so a re-sync cannot drop a co-supervisor.

---

### Task 4: `image` joins the file checks and the copy

**Files:**
- Modify: `tools/tft/catalog.py:110-121` (`_required_files`)
- Modify: `tools/tft/site.py` (`_verify_files`, `_write_entry`)
- Test: `tests/test_catalog.py`, `tests/test_site.py`

**Interfaces:**
- Consumes: `Entry.image` (Task 2).
- Produces: nothing new. `tft validate` reports a declared-but-missing `image`; `Site.build` raises `BadValue` before the output directory is wiped, and copies the file next to the page when it is there.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_catalog.py`:

```python
def test_declared_image_must_exist(repo):
    _add(repo, "2027-x", data=MINIMAL | {"image": "cover.png"})

    assert any("cover.png" in p for p in _catalog(repo).problems())


def test_present_image_is_no_problem(repo):
    folder = _add(repo, "2027-x", data=MINIMAL | {"image": "cover.png"})
    (folder / "cover.png").write_bytes(b"\x89PNG\r\n")

    assert _catalog(repo).problems() == []
```

Append to `tests/test_site.py`:

```python
def test_image_is_copied_next_to_the_page(repo):
    folder = _entry(repo, "2027-x", FULL | {"image": "cover.png"})
    (folder / "cover.png").write_bytes(b"\x89PNG\r\n")

    out = _build(repo)

    assert (out / "entries" / "2027-x" / "cover.png").is_file()


def test_a_declared_image_missing_from_disk_fails_the_build(repo):
    folder = _entry(repo, "2027-x", FULL | {"image": "cover.png"})
    (folder / "cover.png").write_bytes(b"\x89PNG\r\n")
    out = _build(repo)
    (out / "sentinel.html").write_text("kept")

    # The metadata still declares the image, but the file behind it is gone.
    (folder / "cover.png").unlink()

    with pytest.raises(BadValue, match="2027-x.*cover.png"):
        _build(repo)

    assert (out / "sentinel.html").read_text() == "kept"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_catalog.py tests/test_site.py -q`
Expected: FAIL — `problems()` returns `[]` where a missing `cover.png` was expected, and `DID NOT RAISE BadValue`.

- [ ] **Step 3: Add `image` to the required files**

In `tools/tft/catalog.py`, inside `_required_files`, after the `photo` block:

```python
        if entry.image:
            names.append(entry.image)
```

- [ ] **Step 4: Verify and copy it in `site`**

In `tools/tft/site.py`, inside `_verify_files`, after the `photo` block:

```python
            if entry.image:
                self._require(source, entry.image, entry.slug)
```

and inside `_write_entry`, after the `photo` copy:

```python
        if entry.image:
            shutil.copyfile(source / entry.image, folder / entry.image)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_catalog.py tests/test_site.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/tft/catalog.py tools/tft/site.py tests/test_catalog.py tests/test_site.py
git commit -m "Check and copy a declared thesis image"
```

Body: image follows photo and slides — validate names it, and the build
refuses before the output directory is wiped, so a typo never costs the
previous site.

---

### Task 5: The entry page gets the ECL header

**Files:**
- Modify: `tools/tft/templates/entry.html:11`
- Modify: `tools/tft/assets/style.css`
- Test: `tests/test_site.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. Presentation only.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_site.py`:

```python
def test_entry_page_carries_the_site_header(repo):
    _entry(repo, "2027-x", FULL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert 'src="../../assets/ecl-logo.png"' in page
    assert 'class="rule"' in page
    assert 'href="../../"' in page
    # The header's home link replaces the old back link; it is not duplicated.
    assert "All entries" not in page
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_site.py::test_entry_page_carries_the_site_header -q`
Expected: FAIL — `assert 'src="../../assets/ecl-logo.png"' in page`.

- [ ] **Step 3: Replace the back link with the header**

In `tools/tft/templates/entry.html`, replace this line:

```html
<p><a href="../../">&larr; All entries</a></p>
```

with:

```html
<header>
  <img src="../../assets/ecl-logo.png" alt="Embodied Computing Lab">
  {# Not an h1: the thesis title below owns that. #}
  <p class="brand"><a href="../../">Theses &amp; publications</a></p>
</header>
<div class="rule"></div>
```

- [ ] **Step 4: Style the brand line like the index title**

In `tools/tft/assets/style.css`, in the header block, extend it to:

```css
/* Header: the mark, the title, and one gradient hairline echoing it. */
header { display: flex; align-items: center; gap: .75rem; }
header img { width: 36px; height: 36px; }
header h1 { margin: 0; }

.brand { margin: 0; font-size: 1.6rem; font-weight: 700; }
.brand a { color: var(--ink); text-decoration: none; }
.brand a:hover { text-decoration: underline; }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_site.py -q`
Expected: PASS. Other entry-page tests keep passing; none of them asserted on the back link.

- [ ] **Step 6: Commit**

```bash
git add tools/tft/templates/entry.html tools/tft/assets/style.css tests/test_site.py
git commit -m "Give the entry page the ECL header"
```

Body: the header's home link replaces the back link rather than joining
it. The brand line is a paragraph, not a second h1: the thesis title
owns that on this page.

---

### Task 6: Render, publish and search the programme

**Files:**
- Modify: `tools/tft/site.py` (`record`, `Site.__init__`, new `titlecase`)
- Modify: `tools/tft/templates/entry.html` (the meta line)
- Modify: `tools/tft/assets/app.js` (the haystack)
- Test: `tests/test_site.py`, `tests/test_app_js.py`

**Interfaces:**
- Consumes: `Entry.programme` (Task 2).
- Produces: `tft.site.titlecase(text: str) -> str`, registered as the Jinja filter `titlecase`. `index.json` records gain a `programme` key, `None` when absent.

- [ ] **Step 1: Write the failing tests**

In `tests/test_site.py`, change the import line `from tft.site import Site` to `from tft.site import Site, titlecase`, add `"programme": "GRADO EN INGENIERÍA BIOMÉDICA"` to the `FULL` fixture, and add `"programme": "GRADO EN INGENIERÍA BIOMÉDICA",` to the golden record in `test_index_json_matches_the_golden_record`, immediately after `"degree": "bachelor",`.

Add `"programme": None` to the assertions of `test_unfinished_entry_has_false_flags`:

```python
    assert records[0]["programme"] is None
```

Append the new tests:

```python
def test_entry_page_shows_the_programme_title_cased(repo):
    _entry(repo, "2027-x", FULL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert "Grado en Ingeniería Biomédica" in page
    assert "GRADO EN INGENIERÍA BIOMÉDICA" not in page


def test_entry_page_omits_the_programme_when_absent(repo):
    _entry(repo, "2027-x", MINIMAL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert "Grado en" not in page


def test_the_card_meta_line_keeps_showing_the_degree_not_the_programme(repo):
    # The card's meta line is author · year · degree; a full programme
    # name would wrap it on a phone. The programme stays searchable only.
    _entry(repo, "2027-x", FULL)

    record = json.loads((_build(repo) / "index.json").read_text())[0]

    assert record["degree"] == "bachelor"
    assert record["programme"] == "GRADO EN INGENIERÍA BIOMÉDICA"


@pytest.mark.parametrize("raw,shown", [
    ("GRADO EN INGENIERÍA BIOMÉDICA", "Grado en Ingeniería Biomédica"),
    ("MÁSTER EN INGENIERÍA DE TELECOMUNICACIÓN", "Máster en Ingeniería de Telecomunicación"),
    ("EN", "En"),
    ("", ""),
])
def test_titlecase_lowercases_spanish_connectives(raw, shown):
    assert titlecase(raw) == shown
```

Append to `tests/test_app_js.py`:

```python
def test_app_searches_the_programme():
    # "biomédica" must find the thesis even though the card never shows it.
    assert "e.programme" in APP_JS.read_text()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_site.py tests/test_app_js.py -q`
Expected: FAIL — the golden record comparison mismatches on the missing `programme` key, and `ImportError: cannot import name 'titlecase' from 'tft.site'`.

- [ ] **Step 3: Add the filter**

In `tools/tft/site.py`, add after `SUMMARY_LIMIT`:

```python
# Spanish connectives stay lowercase inside a programme name, except
# when the name starts with one.
MINOR_WORDS = ("en", "de", "del", "la", "el", "los", "las", "y", "e")
```

and add the function above `record`:

```python
def titlecase(text: str) -> str:
    """'GRADO EN INGENIERÍA BIOMÉDICA' -> 'Grado en Ingeniería Biomédica'."""
    words = [word.lower() for word in text.split()]

    if not words:
        return ""

    rest = [word if word in MINOR_WORDS else word.capitalize() for word in words[1:]]

    return " ".join([words[0].capitalize(), *rest])
```

- [ ] **Step 4: Register the filter and publish the field**

In `Site.__init__`, after the `Environment(...)` assignment:

```python
        self._jinja.filters["titlecase"] = titlecase
```

In `record`, after the `"degree"` entry:

```python
        "programme": entry.programme,
```

- [ ] **Step 5: Show it on the entry page**

In `tools/tft/templates/entry.html`, replace the meta paragraph with:

```html
  <p class="meta">
    {{ entry.author }} &middot; {{ entry.year }} &middot; {{ entry.type }}
    {%- if entry.degree %} ({{ entry.degree }}){% endif %}
    {%- if entry.programme %} &middot; {{ entry.programme|titlecase }}{% endif %}
  </p>
```

- [ ] **Step 6: Add it to the search haystack**

In `tools/tft/assets/app.js`, replace the haystack line in `matches`:

```js
  const haystack = [e.title, e.author, e.summary, e.programme,
                    e.topics.join(" "), e.keywords.join(" ")]
    .join(" ").toLowerCase();
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_site.py tests/test_app_js.py -q`
Expected: PASS. `test_app_reads_only_fields_the_record_provides` also passes, because `programme` is now a record key.

- [ ] **Step 8: Run the whole suite and commit**

Run: `python -m pytest -q`
Expected: PASS.

```bash
git add tools/tft/site.py tools/tft/templates/entry.html tools/tft/assets/app.js \
        tests/test_site.py tests/test_app_js.py
git commit -m "Show and search the degree programme"
```

Body: the stored value keeps the cover's uppercase; casing is a
presentation filter. The card still shows the degree, not the
programme, which would wrap the meta line on a phone.

---

### Task 7: Render the thesis image and video

**Files:**
- Modify: `tools/tft/site.py` (`_write_entry`)
- Modify: `tools/tft/templates/entry.html`
- Modify: `tools/tft/assets/style.css`
- Test: `tests/test_site.py`

**Interfaces:**
- Consumes: `Entry.image`, `Entry.video`, `entry.parse_video`, `Video.embed` (Task 2); the image copy (Task 4).
- Produces: the entry template receives a `video` context variable, a `tft.entry.Video` or `None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_site.py`:

```python
VIMEO_URL = "https://vimeo.com/76979871"
YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def _with_media(repo, slug="2027-x", video=YOUTUBE_URL):
    folder = _entry(repo, slug, FULL | {"image": "cover.png", "video": video})
    (folder / "cover.png").write_bytes(b"\x89PNG\r\n")

    return folder


def test_image_and_video_render_before_the_abstract(repo):
    _with_media(repo)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert page.index("thesis-image") < page.index('class="summary"')
    assert page.index("<iframe") < page.index('class="summary"')


def test_video_src_is_built_from_the_id_not_the_stored_url(repo):
    _with_media(repo)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ"' in page
    assert YOUTUBE_URL not in page


def test_a_vimeo_video_uses_the_vimeo_player(repo):
    _with_media(repo, video=VIMEO_URL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert 'src="https://player.vimeo.com/video/76979871"' in page


def test_media_never_enters_the_index(repo):
    _with_media(repo)

    record = json.loads((_build(repo) / "index.json").read_text())[0]

    assert "image" not in record
    assert "video" not in record


def test_entry_page_omits_the_media_blocks_when_absent(repo):
    _entry(repo, "2027-x", FULL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert "thesis-image" not in page
    assert "<iframe" not in page
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_site.py -q`
Expected: FAIL — `ValueError: substring not found` on `page.index("thesis-image")`.

- [ ] **Step 3: Pass the parsed video to the template**

In `tools/tft/site.py`, extend the import:

```python
from .entry import DOC_NAME, Entry, parse_video
```

and the render call in `_write_entry`:

```python
        page = self._jinja.get_template("entry.html").render(
            entry=entry, doc=doc, video=parse_video(entry.video),
            summary=markdown.markdown(entry.summary),
        )
```

- [ ] **Step 4: Render them after the score row**

In `tools/tft/templates/entry.html`, insert immediately after the score block and before the supervisors block:

```html
  {% if entry.image %}
  <img class="thesis-image" src="{{ entry.image }}" alt="{{ entry.title }}">
  {% endif %}

  {# src is built from the parsed provider id, never from the stored URL:
     entry.yaml arrives through pull requests. #}
  {% if video %}
  <div class="video">
    <iframe src="{{ video.embed }}" title="{{ entry.title }}"
            allowfullscreen loading="lazy"></iframe>
  </div>
  {% endif %}
```

- [ ] **Step 5: Style them**

Append to `tools/tft/assets/style.css`:

```css
/* The thesis's own figure, full column width: unlike the portrait it is
   the content, not a decoration beside it. */
.thesis-image { display: block; width: 100%; height: auto; margin: 1rem 0; }

.video { margin: 1rem 0; }
.video iframe { display: block; width: 100%; aspect-ratio: 16 / 9; border: 0; }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_site.py -q`
Expected: PASS.

- [ ] **Step 7: Run the whole suite and commit**

Run: `python -m pytest -q`
Expected: PASS.

```bash
git add tools/tft/site.py tools/tft/templates/entry.html tools/tft/assets/style.css \
        tests/test_site.py
git commit -m "Render the thesis image and video"
```

Body: both sit before the abstract and neither enters index.json — a
list page pulling a video frame per entry is slow on exactly the
phone-shaped viewport this site has to work on.

---

### Task 8: Document the new fields and the edit workflow

**Files:**
- Modify: `README.md`
- Test: none — prose.

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Correct the extraction paragraph**

In `README.md`, under "Adding an entry", replace:

```
Title, author, year, degree, summary and keywords are read from the LaTeX
source.
```

with:

```
Title, author, year, degree, programme, supervisors, summary and keywords
are read from the LaTeX source.
```

and extend the paragraph that lists the landmarks, replacing:

```
Extraction reads the group's template: `\tfgtitle`, `\authorname` and
`\fecha` in `main.tex`, the cover phrase (`TRABAJO FIN DE GRADO`,
`... DE MÁSTER`, `TESIS DOCTORAL`), and the chapter holding
`\chapter*{Abstract}` with its `\textbf{Keywords:}` line.
```

with:

```
Extraction reads the group's template: `\tfgtitle`, `\authorname`,
`\supervisor` and `\fecha` in `main.tex`, the cover phrase
(`TRABAJO FIN DE GRADO`, `... DE MÁSTER`, `TESIS DOCTORAL`), the
programme named just above it on the same page (`GRADO EN ...`,
`MÁSTER EN ...`), and the chapter holding `\chapter*{Abstract}` with its
`\textbf{Keywords:}` line. A thesis on another template simply has no
programme; that is not an error and there is no flag for it.
```

- [ ] **Step 2: Rewrite the hand-filled fields table**

Replace the table under "Fields you fill in by hand" with:

```markdown
| Field | Notes |
|---|---|
| `topics` | from `taxonomy/topics.yaml`; the only filter facet |
| `score` | 0 to 10 |
| `honours` | `true` for Matrícula de Honor; needs a `score` |
| `photo` | the author's portrait, a file in the entry folder, e.g. `photo.jpg` |
| `image` | a figure from the thesis, a file in the entry folder, e.g. `cover.png` |
| `video` | a YouTube or Vimeo URL, e.g. `https://vimeo.com/76979871` |
| `repos`, `slides` | as before |

`supervisors` is no longer hand-entered: it is read from the
`\supervisor` macro and rewritten on every sync.

Only three video URL shapes are accepted —
`https://www.youtube.com/watch?v=<id>`, `https://youtu.be/<id>` and
`https://vimeo.com/<digits>`. Anything else is rejected by `validate`.
The stored URL is parsed into a provider id and never reaches the page's
`iframe`, because `entry.yaml` arrives through pull requests.
```

- [ ] **Step 3: Extend the consent note**

Replace:

```
A student's portrait is personal data. Get their written consent before
committing one, and note that removing it later means rewriting this
repository's history.
```

with:

```
A student's portrait is personal data, and so is a recognisable student
in an `image` or a `video`. Get their written consent before committing
one, and note that removing it later means rewriting this repository's
history.
```

- [ ] **Step 4: Fix the sync-preserves list and document editing one field**

Under "Keeping an entry current", replace:

```
Your own fields (`topics`,
`score`, `honours`, `photo`, `repos`, `slides`) are preserved.
```

with:

```
Your own fields (`topics`,
`score`, `honours`, `photo`, `image`, `video`, `repos`, `slides`) are
preserved; `supervisors` is not — it is re-read from the source.
```

Then add a new section immediately after that one:

```markdown
### Changing one field

To change a field you own — a score, a photo, an image, a video — edit
`content/theses/<slug>/entry.yaml` and run:

    tft validate && tft build

Do **not** use `tft sync` for this. Sync re-pulls from Overleaf and
recompiles the LaTeX; it is for picking up changes to the thesis itself,
not for applying your own edits.
```

- [ ] **Step 5: Check the README against the code**

Run: `python -m pytest -q`
Then reread the two edited sections and confirm every field name in the
table exists in `OPTIONAL` in `tools/tft/entry.py`.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "Document image, video and the edit-one-field workflow"
```

Body: supervisors leaves the hand-entered table; sync's preserve list
gains image and video. Editing one field was undocumented, and the
obvious guess — tft sync — is the wrong command.

---

### Task 9: Migrate the live entry

**Files:**
- Modify: `content/theses/2026-gomez-martinez-biomechanics-viz/entry.yaml` (by running `tft sync`, not by hand)
- Test: none — a manual verification against the real thesis.

**Interfaces:**
- Consumes: everything above.
- Produces: the live entry carrying `programme` and the re-derived `supervisors`.

**Prerequisites:** `OVERLEAF_GIT_TOKEN` exported, `latexmk` and the TeX packages listed in the README installed, and the private mirror cloned at `../docs-TFTs-private`. If any is missing, stop and say so rather than hand-editing `entry.yaml` — the point of this task is to prove the pipeline produces the field.

- [ ] **Step 1: Record the current state**

```bash
cp content/theses/2026-gomez-martinez-biomechanics-viz/entry.yaml /tmp/entry-before.yaml
cat /tmp/entry-before.yaml
```

- [ ] **Step 2: Sync**

```bash
tft sync 2026-gomez-martinez-biomechanics-viz
```

Expected: it reports the entry changed. If it reports no change, the Overleaf commit has not moved; force the re-read by clearing the recorded commit:

```bash
python - <<'PY'
from pathlib import Path
p = Path("content/theses/2026-gomez-martinez-biomechanics-viz/entry.yaml")
p.write_text("\n".join(l for l in p.read_text().splitlines() if "commit:" not in l) + "\n")
PY
tft sync 2026-gomez-martinez-biomechanics-viz
```

- [ ] **Step 3: Diff and check what moved**

```bash
diff /tmp/entry-before.yaml content/theses/2026-gomez-martinez-biomechanics-viz/entry.yaml
git diff --stat
```

Expected: `entry.yaml` gains `programme: GRADO EN INGENIERÍA BIOMÉDICA`, keeps `supervisors: [Rodrigo García Carmona]`, and `topics`, `score` and `summary.md` are unchanged. The cover file is
`chapters/0-preamble.tex` and the macro is `\newcommand{\supervisor}{Rodrigo García Carmona}` in `main.tex`; both were verified against this thesis when the spec was written.

- [ ] **Step 4: Validate and build**

```bash
tft validate && tft build
```

Expected: no problems, and `site/entries/2026-gomez-martinez-biomechanics-viz/index.html` shows "Grado en Ingeniería Biomédica" in the meta line and carries the ECL header.

```bash
grep -c "Grado en Ingeniería Biomédica" site/entries/2026-gomez-martinez-biomechanics-viz/index.html
grep -c "biomédica" site/index.json
```

- [ ] **Step 5: Commit**

```bash
git add content/theses/2026-gomez-martinez-biomechanics-viz/entry.yaml
git commit -m "Backfill the programme on the live entry"
```

Body: produced by tft sync, not by hand, so the extractor is what is
being verified. supervisors is unchanged; it now comes from the
\supervisor macro rather than from the human.

---

## Self-Review

Checked against `docs/superpowers/specs/2026-09-18-programme-media-and-entry-header-design.md`:

| Spec section | Task |
|---|---|
| Schema: three new fields in `OPTIONAL` | 2 |
| Schema: `supervisors` ownership change | 3 (code), 8 (docs) |
| Extraction: programme pattern, original text, cover-file scope | 1 |
| Extraction: two programmes raise | 1 |
| Extraction: programme not mandatory, no `--programme` flag | 1, 3 (no CLI change) |
| Extraction: supervisors split on `,`, newline, `\\` | 1 |
| Rendering: entry page header, `../../` assets, back link replaced | 5 |
| Rendering: programme title-cased, in the meta line | 6 |
| Rendering: programme in `index.json` and the search haystack; card keeps the degree | 6 |
| Rendering: image and video before the abstract, image copied | 4 (copy), 7 (render) |
| Rendering: neither in `index.json` | 7 |
| Video safety: parsed `(host, id)`, allowlist, `BadValue` otherwise | 2 |
| File validation: `image` in `_check_filename`, `_required_files`, `_verify_files` | 2, 4 |
| Documentation: table, edit-one-field section, consent note | 8 |
| Testing: extractor, schema, site, migration | 1, 2, 4-7, 9 |

Out-of-scope items in the spec (`tft set`, self-hosted video, `\tfgtitlees`, `language`) have no task, as intended.
