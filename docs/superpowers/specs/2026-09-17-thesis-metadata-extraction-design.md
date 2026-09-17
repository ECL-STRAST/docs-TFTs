# Thesis metadata extraction, score, portrait and ECL theming

Date: 2026-09-17
Status: approved, pending implementation plan

## Purpose

Today `tft add` takes title, author, year and degree as command-line
arguments, and `summary.md` is written by hand. All of that already
exists inside the thesis: the ETSIT template declares title, author and
date as macros, the cover states the degree, and `chapters/B-abstract.tex`
holds both the English abstract and the author's own keywords.

This design derives those fields from the LaTeX source instead, and adds
three things the catalog cannot derive: the defence score, an optional
author portrait, and a visual identity matching the ECL organization.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Keywords vs topics | Two separate fields | `topics` stays curated and drives the site filter; `keywords` records the thesis's own terms verbatim |
| `summary.md` | Derived, overwritten on every sync | The abstract is the authoritative text; the overwrite is a reviewable git diff, not a silent loss |
| Missing landmark | Abort, naming the field | CLI flags become optional overrides, so an odd template is still ingestable |
| Parser | Hand-rolled regex, no new dependency | Proven on the real document; a parser library would replace only the smaller half of the work |
| Photo | Author portrait, optional, dropped in by hand | Nothing to extract; absent means the block is simply not rendered |
| Score | Number 0-10 plus an honours flag | Sortable and checkable; Matrícula de Honor is what separates two theses that both scored 10 |
| Logo | Vendored 400x400 PNG from the GitHub org avatar | No vector original exists; crisp enough at header and favicon size |

### Why not extract from the compiled PDF

`hyperref` already stamps `pdfauthor` and `pdftitle`, but the abstract
and keywords would need page-text extraction with positional heuristics
plus a PDF library. It also reads the build output rather than the source
of truth, and is most fragile exactly on the fields that matter.

### Why keywords never touch the taxonomy

`taxonomy/topics.yaml` says adding a topic is a deliberate act, and that
is what stops near-duplicates such as "byomechanics". Belén's eight
keywords contain exactly one vocabulary term; two of her three curated
topics appear in no keyword. The two vocabularies answer different
questions and merging them would both pollute the filter facets and
discard curation.

## The extractor

New module `tools/tft/tex.py`, a driver in the same layer as `latex.py`.
It knows LaTeX and nothing else: no `Entry`, no `Catalog`, no YAML.
`ingest.py` is its only caller and performs the `Meta` to `Entry`
mapping, keeping the chain `cli -> ingest -> tex`.

```python
@dataclass(frozen=True)
class Meta:
    title: str
    author: str
    year: int
    degree: str | None
    abstract: str               # de-TeXed paragraphs, markdown-ready
    keywords: tuple[str, ...]
```

### Landmarks

| Field | Source | Rule |
|---|---|---|
| title | `main.tex` | `\newcommand{\tfgtitle}{...}` |
| author | `main.tex` | `\newcommand{\authorname}{...}` |
| year | `main.tex` | first `(19\|20)\d{2}` inside `\newcommand{\fecha}{...}` |
| degree | any `.tex` | `TRABAJO FIN DE GRADO` -> bachelor, `... MÁSTER` -> master, `TESIS DOCTORAL` -> phd; accent- and case-insensitive |
| abstract | the `.tex` holding `\chapter*{Abstract}` | text after `\addcontentsline`, cut at `\textbf{Keywords:}` |
| keywords | same file | tail after that marker, split on `,`, lowercased, trailing `.` dropped |

Every landmark name is a module constant. The abstract's file is found by
scanning the source tree for `\chapter*{Abstract}` rather than hardcoding
`chapters/B-abstract.tex`: the same amount of code, and it survives a
renamed chapter.

### De-TeXing

Applied in order to the abstract body:

1. Drop `\vfill`, `\cleardoublepage`, `\phantomsection`.
2. Unwrap `\textbf{...}`, `\emph{...}`, `\textit{...}`, `\texttt{...}` to
   their argument.
3. Strip any remaining `\macro[opt]{arg}`.
4. Collapse runs of spaces and tabs; preserve blank lines as paragraph
   breaks.

Verified against Belén's abstract: five clean paragraphs, 2,637
characters, eight keywords recovered verbatim.

### Failure behaviour

A landmark that cannot be found raises an error naming that field. The
existing `--title`, `--author`, `--year` and `--degree` flags become
optional overrides: supplying one fills the gap and silences its check.
Nothing incomplete reaches `entry.yaml`, and a thesis from a different
template is still ingestable without editing a student's Overleaf
project.

### Call order

`ingest.add` becomes: fetch -> **extract** -> compile -> create ->
install. Extraction runs before the compile so a metadata failure costs
seconds rather than a full LaTeX run, matching the existing rule that a
broken project must leave no half entry behind.

### Interface change

`cli.py` currently builds the slug as `f"{year}-{name}"` before anything
is fetched. With the year extracted, slug construction moves inside
`ingest.add`, which takes the slug stem plus an overrides object instead
of four loose arguments.

### Sync

`tft sync` re-extracts, because `summary.md` is now derived. It refreshes
title, author, year, degree, keywords and the summary. Human-owned
fields (`topics`, `score`, `honours`, `photo`, `repos`, `slides`) are
preserved.

If the extracted year differs from the entry's, sync updates the `year`
field and prints a warning, but does **not** rename the folder. The slug
is an identifier and any already-shared URL must keep resolving.

## Schema

Four new fields in `entry.py`, all in `OPTIONAL`. Optional is deliberate:
the one existing entry has none of them and must keep validating
untouched.

| Field | Type | Owner | Validation |
|---|---|---|---|
| `keywords` | list of str | derived | non-empty strings when present; never checked against `topics.yaml` |
| `score` | number | human | `0 <= score <= 10` |
| `honours` | bool | human | requires `score`; a bare `honours: true` is rejected |
| `photo` | str | human | filename must exist in the entry folder |

`photo` joins `slides` in `catalog._required_files`, reusing the existing
"a declared file must be there" rule.

`store.py`'s contract changes: `summary.md` is no longer hand-written and
never overwritten. Its docstring must say so.

### Migration

`tft sync 2026-gomez-martinez-biomechanics-viz` backfills keywords and
rewrites `summary.md` from the abstract. It needs the Overleaf token and
a full compile, and lands as a reviewable diff. This is the only
migration step.

## Site

`site.record()` gains `score`, `honours` and `keywords`.

`app.js` shows a score badge on the card and folds keywords into the
free-text haystack, so searching "c3d" finds Belén's thesis. Keywords
stay out of the filter dropdowns: `topic` remains the only taxonomy
facet.

The entry page gains the portrait, the score and a keyword row styled
visually flatter than topic pills, so the filterable thing looks
clickable and the non-filterable thing does not.

## Theme

One vendored asset, `tools/tft/assets/ecl-logo.png`, the 400x400 GitHub
organization avatar. Tokens on `:root` in the existing single stylesheet,
sampled from that image:

```
--ecl-blue:  #046ba5     --ecl-navy:  #093d76
--ecl-teal:  #218880     --ecl-green: #1a6c46
```

Contrast against white, WCAG AA needing 4.5 for body text:

| Token | Ratio | Use |
|---|---|---|
| `--ecl-navy` | 10.82 | text, any size |
| `--ecl-green` | 6.41 | text, any size |
| `--ecl-blue` | 5.75 | text, any size |
| `--ecl-teal` | 4.29 | decoration only |

Teal appears in the gradient rule and nowhere near a word.

- Header: the logo at 36px beside the title, over a 3px gradient hairline
  running blue to teal to green. This is the only flourish, echoing the
  mark itself.
- Links and the entry title take `--ecl-blue`. The score badge takes
  `--ecl-green`, or `--ecl-navy` when honours is set.
- Portrait: 72px, circular, `object-fit: cover`, floated beside the entry
  heading. The whole block is absent when `photo` is unset.
- The same PNG serves as favicon.

No framework, no web fonts, still one stylesheet. Minimalistic here means
the logo and the rule carry the identity and nothing else changes.

## Testing

`tests/test_tex.py`, fixture tree per case:

- happy path: every field recovered from a template-shaped source
- missing macro: the error names the field
- override supplies a missing field and the ingest proceeds
- abstract chapter renamed: still found by scanning
- master's and PhD degree strings, with and without accents
- keyword whitespace, casing and trailing period
- nested `\textbf` inside an abstract paragraph

Existing suites extended: `test_entry.py` for the four new fields and
their validation, `test_catalog.py` for the missing-photo check,
`test_ingest.py` for the new call order and sync behaviour,
`test_site.py` and `test_app_js.py` for the new record fields.

## Out of scope

`language` is hardcoded `en` at `catalog.create` and is derivable from
`\usepackage[english]{babel}`. It was not requested and is not included.

## Note for the README

A student's portrait in a public repository is personal data. It is worth
their written consent, and removing it later means rewriting git history.
