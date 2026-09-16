# Thesis catalog design

Date: 2026-09-16
Status: approved, pending implementation plan

## Purpose

Turn `ECL-STRAST/docs-TFTs` into a browsable catalog of the research
group's past Bachelor's, Master's and PhD theses. Each entry gathers the
compiled PDF, an English summary, links to attached code and docs
repositories, and an optional presentation. A companion private repo
mirrors the LaTeX sources and anything not cleared for publication.

The catalog is entity-agnostic from day one so scientific publications
can be added later without migrating anything.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Role of the repo | Browsable catalog, not a preservation archive | Links out to Overleaf and GitHub; only the PDF is held here |
| Surface | Static site on GitHub Pages | Filtering and search over dozens of entries |
| Ingest | Local script clones Overleaf and compiles with latexmk | Reproducible PDFs, no TeX toolchain in CI |
| Private material | Separate private repo, linked by URL | Duplicates trivially for publications later; no submodule friction |
| Facets | Year, degree, topics, has-code, has-slides | Supervisors recorded and displayed, not filtered |
| Prose language | English | Widest reach, regardless of the language of the thesis itself |
| Site builder | Python, shared with the ingest tool | One language, one dependency set, decade-scale maintainability |

### Why not a private submodule

A submodule would pin the source revision that produced each PDF, but it
costs a pointer bump on every source update and a PAT in CI. Recording
the Overleaf commit SHA in `entry.yaml` gives the same provenance for
free. Papers are edited far more often than theses are defended, so that
friction would land exactly where it hurts most once publications are
added.

### Why not a private monorepo publishing a public subset

Strongest leak protection, but every paper would have to be authored
inside one private repo, while each paper is its own Overleaf project
with its own coauthors. It would also make the public repo generated
output that can never be edited by hand.

## Repository layout

```
docs-TFTs/                        (public)
|-- README.md                     what this is + how to add an entry
|-- content/
|   |-- theses/
|   |   `-- 2024-perez-vr-cpr-training/
|   |       |-- entry.yaml        all metadata
|   |       |-- summary.md        1-2 paragraphs, English
|   |       |-- thesis.pdf        compiled by the ingest tool
|   |       `-- slides.pdf        optional, any format
|   `-- publications/             later, identical shape
|-- taxonomy/topics.yaml          controlled tag vocabulary
|-- tools/tft/                    python package
|-- site/                         build output, gitignored
`-- .github/workflows/            validate.yml, pages.yml
```

Entry folders are named `<year>-<surname>-<slug>`: sortable, unique,
readable, and stable forever. The private repo mirrors the same names
under `sources/theses/<folder>/`, so no mapping table is needed.

## Metadata schema

```yaml
type: thesis                  # thesis | publication
title: VR-based CPR training assessment
author: Maria Perez
year: 2024
degree: bachelor              # thesis only: bachelor | master | phd
supervisors: [R. Garcia Carmona]
topics: [vr, medical-training]
language: es                  # language of the document itself
overleaf:
  project_id: 65f0c1...
  commit: a3f19c2             # revision compiled into thesis.pdf
  main: main.tex              # only when root-file detection is ambiguous
  mirror: https://github.com/ECL-STRAST/docs-TFTs-private/tree/main/...
repos:
  code: [https://github.com/ECL-STRAST/vr-cpr-simulation]
  docs: https://github.com/ECL-STRAST/vr-cpr-docs
slides: slides.pdf            # omit if none
```

`degree` is required when `type` is `thesis`. Publications will add a
`venue` field under the same rule. Everything else is common to both.

### Clearance by construction

There is no `publishable` flag. Presence in the public repo *is* the
clearance. An entry not cleared for publication lives only in the
private repo, using the same `entry.yaml` shape, and the tooling builds
a members-only site from it locally. This removes the class of bug where
a mis-set flag leaks a PDF.

## Tooling

One Python package, `tools/tft/`, in strict layers. Nothing above the
driver layer sees a git command or a latexmk invocation.

```
  CLI            tft add / sync / validate / build
                          |
  Services       catalog.py   ingest.py   site.py
                          |
  Drivers        overleaf.py   latex.py   store.py
                 (git)         (latexmk)  (fs + yaml)
```

| Command | Behaviour |
|---|---|
| `tft add --overleaf <id> --name <n>` | Clone, compile, create the entry folder with `thesis.pdf` and stubbed `entry.yaml` + `summary.md`; mirror sources into the private repo |
| `tft sync <entry>` | Re-pull, recompile, refresh the PDF and `overleaf.commit`; no-op when the SHA is unchanged |
| `tft validate` | Schema, topics against the vocabulary, referenced files exist, repo URLs resolve |
| `tft build` | Render `site/` from the catalog |

### Constraints

- `OVERLEAF_GIT_TOKEN` is read from the environment by the overleaf
  driver, injected into the clone URL in memory, and scrubbed from any
  error it raises. `.env` is gitignored. The token is never written to
  disk and never reaches GitHub.
- Clones land in `.work/<entry>/` (gitignored). Sources are copied from
  there into the private repo checkout, the PDF into the public entry
  folder.
- The private repo defaults to the sibling `../docs-TFTs-private`,
  overridable in `tft.toml` at the repo root, since the path varies per
  machine.
- The main `.tex` is the one at the source root containing
  `\documentclass`; `overleaf.main` resolves ambiguity.
- A compile failure aborts cleanly: the latexmk log stays in `.work/`,
  nothing is copied, and the entry keeps its previous PDF. A broken
  Overleaf project can never blank out an archived thesis.

## Site

`tft build` emits a fully static `site/`: an index page, one page per
entry, the PDFs, and an `index.json` of every entry's metadata.
Filtering by year, degree, topics, has-code and has-slides, plus
free-text search over title, author and summary, runs client-side in
vanilla JavaScript against that JSON. No framework and no CDN, so a copy
of `site/` works offline.

Dependencies, in total: PyYAML, Jinja2, markdown.

## CI

```
  PR / push ---> validate.yml   tft validate + pytest
  push main ---> pages.yml      tft build ---> deploy Pages
```

Neither workflow talks to Overleaf, compiles LaTeX, or touches the
private repo; the PDFs are already committed, so the site build reads
nothing but files in the public repo. Ingest is deliberately a local,
human-run step. CI therefore holds no secrets, and a CI compromise
exposes nothing that is not already published.

## Testing

Tests are written before the code they cover.

- catalog/store: entry round-trip, folder-name generation, and a
  distinct error per schema violation
- overleaf driver: URL construction and token scrubbing, exercised
  against a local throwaway git remote, no network
- latex driver: unit-tested against a stubbed runner; one integration
  test compiles a two-line `.tex`, skipped when `latexmk` is absent
- site build: golden-file comparison over a small fixture catalog

## Bootstrapping

The README's "add an entry" recipe is three steps: `tft add`, fill in
`summary.md` and the topics, `tft validate`. The first real thesis run
through it becomes the worked example.
