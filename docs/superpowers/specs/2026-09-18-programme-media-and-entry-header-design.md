# Programme, Media and Entry Header — Design

**Date:** 2026-09-18
**Status:** approved in conversation, pending written review

## Goal

Four changes to the thesis catalog:

1. Show the degree programme ("Grado en Ingeniería Biomédica"), extracted
   from the thesis cover.
2. Extract the supervisor list, which is entered by hand today.
3. Let an entry carry a thesis image and a thesis video, both shown
   before the abstract.
4. Give the entry page the ECL header the index page already has.

## Context

`tft` derives `title`, `author`, `year`, `degree`, `abstract` and
`keywords` from a thesis's LaTeX. `tools/tft/tex.py` is the driver that
reads the source and reports what it finds; `ingest.py` applies the
human's overrides and decides what is mandatory. The layer chain is
`cli -> ingest -> tex`, and `tex.py` never sees `Entry`, `Catalog` or
YAML.

The ETSIT cover declares the programme immediately above the degree
phrase, and `main.tex` declares `\supervisor`:

```latex
{\Large\rm \textbf{ GRADO EN INGENIERÍA BIOMÉDICA}} \\
\vspace{2.0cm}
{\Large\rm \textbf{TRABAJO FIN DE GRADO}} \\
```

Both landmarks were verified against the one ingested thesis.

## Schema

Three new fields in `entry.py`, all in `OPTIONAL`, and one change of
ownership.

| Field | Type | Owner | Validation |
|---|---|---|---|
| `programme` | str | derived | non-empty string when present |
| `image` | str | human | a bare filename that exists in the entry folder |
| `video` | str | human | a URL on an allowed host, parseable to a video id |
| `supervisors` | list of str | **derived** (was human) | unchanged: non-empty strings |

The existing entry must keep validating untouched, so every new field is
optional.

### Ownership change

`supervisors` moves from human-owned to derived. The spec of
2026-09-17 lists it among the fields `sync` preserves; **that list is
amended here** to `topics`, `score`, `honours`, `photo`, `image`,
`video`, `repos`, `slides`.

This is safe because the template's `\supervisor` macro holds every
supervisor, separated by commas, newlines or `\\`. A co-supervisor is
therefore never lost to a re-sync, because the macro is the source of
truth for the whole list.

## Extraction

`tex.Meta` gains `programme: str | None` and
`supervisors: tuple[str, ...]`.

### Programme

```
(?:GRADO|M[ÁA]STER)\s+EN\s+([^\\}\n]+)     case-insensitive
```

Matched against the **original** text, not the accent-folded text used
for degree detection, so "INGENIERÍA BIOMÉDICA" keeps its accents. The
whole matched phrase is stored, not just the tail after `EN`.

The pattern cannot collide with the degree phrases: `TRABAJO FIN DE
GRADO` has no `EN` after `GRADO`.

**Search scope: only the file that declares the degree.** Searching every
`.tex` would let body prose ("el grado en ingeniería...") match, since
the pattern is case-insensitive. The programme belongs on the cover, and
the cover is the file carrying the degree phrase. This requires
`degree()` to be refactored so the file holding the match is available
to the programme reader; the returned degree value and its error
behaviour do not change.

Two different programmes in that file raise `ExtractError` naming the
ambiguity, mirroring how `degree()` already treats two different degrees.

`programme` is NOT added to the mandatory set: a thesis on another
template simply has none, and `None` is not an error. There is no
`--programme` override flag; a missing programme is fixed in the LaTeX
or left blank.

### Supervisors

Read the `\supervisor` macro with the existing `macro()` reader, then
split on commas, newlines and `\\`, de-TeX each part, strip it, and drop
empties. One supervisor yields a one-element tuple.

`supervisors` is NOT mandatory — a thesis with no `\supervisor` macro
yields `()`, and ingest does not abort.

## Rendering

### Entry page header

The entry page gains the index page's header: the ECL mark, the site
title linking home, and the gradient rule beneath. Asset paths are two
levels up (`../../assets/...`), matching the existing stylesheet and
favicon links. The existing "← All entries" link is replaced by the
header's home link rather than duplicated.

### Programme

Displayed title-cased by a Jinja filter that lowercases Spanish
connectives (`en`, `de`, `del`, `la`, `el`, `los`, `las`, `y`, `e`)
except in first position: `GRADO EN INGENIERÍA BIOMÉDICA` renders as
`Grado en Ingeniería Biomédica`. The stored value is unchanged; casing is
presentation only.

It joins the existing meta line beneath the title.

`programme` DOES enter `index.json`, and joins the free-text search
haystack in `app.js`, so searching "biomédica" finds the thesis. The card
itself keeps showing `degree` — the level — and not the programme: the
card's meta line is already `author · year · degree`, and a full
programme name would wrap it on a phone. It remains, like `keywords`, a
searchable field that is not a filter facet.

### Image and video

Both render **before** the abstract, after the score row:

- `image` as `<img class="thesis-image" src="{{ entry.image }}">`, copied
  into the built entry folder like `photo` and `slides`.
- `video` as a responsive 16:9 `<iframe>` wrapped in a container div.

Neither enters `index.json`. The card list stays text-only, as `photo`
already does — a list page that pulls a video frame per entry is slow on
exactly the phone-shaped viewport this site has to work on.

### Video safety

The stored URL is never interpolated into the `iframe src`. At schema
level a validator parses the URL into a `(host, id)` pair and rejects
anything else; the template builds the embed URL from the id alone.

Allowed hosts and the id they yield:

| Input | Id |
|---|---|
| `https://www.youtube.com/watch?v=<id>` | `<id>` |
| `https://youtu.be/<id>` | `<id>` |
| `https://vimeo.com/<digits>` | `<digits>` |

Ids are restricted to `[A-Za-z0-9_-]` (YouTube) and digits (Vimeo).
Anything else — another host, a `javascript:` URL, a bare string — is a
`BadValue` naming the field.

This is deliberate: interpolating a stored URL into an `iframe src`
accepts any origin and any scheme, and entry.yaml is repo content that
arrives through pull requests.

### File validation

`image` joins `photo` and `slides` in the existing `_check_filename`
validator (rejecting non-strings, blanks, and `/`, `\`, `..`), in
`catalog._required_files` behind `tft validate`, and in
`site._verify_files`, which runs before the output directory is wiped.

`video` is a URL, not a filename: it goes through the video validator
above and never through `_check_filename`, and no file is expected on
disk for it.

## Documentation

The README's manual-fields table gains `image` and `video`, and
`supervisors` moves out of the hand-entered list.

A short section documents the edit-one-field workflow, which is
currently undocumented:

> To change a field you own — a score, a photo, an image, a video —
> edit `content/theses/<slug>/entry.yaml` and run
> `tft validate && tft build`. Do **not** use `tft sync` for this: sync
> re-pulls from Overleaf and recompiles the LaTeX, which is for picking
> up changes to the thesis itself, not for applying your own edits.

The portrait-consent note extends to `image` and `video`: a recognisable
student in either is personal data on the same footing as a portrait.

## Out of Scope

- A `tft set` command. Explicitly declined; editing YAML plus
  `tft validate && tft build` is the documented workflow.
- Self-hosted video. Files in the repo would hit GitHub's 100MB
  per-file and ~1GB Pages limits and live in git history forever.
- Extracting `\tfgtitlees` (the Spanish title). Noted as available,
  not requested.
- Any change to `language`, still out of scope from the previous spec.

## Testing

- Extractor: programme read from real cover text with accents intact;
  programme absent yields `None`; two programmes raise; body-text
  "grado en ..." outside the cover file does not match; supervisors
  split on each of comma, newline and `\\`; a missing `\supervisor`
  yields `()`.
- Schema: each new field round-trips; `image` rejects traversal, blanks
  and non-strings; `video` accepts each allowed form and rejects another
  host, a `javascript:` URL and a non-string; the pre-existing entry
  still validates untouched.
- Site: image and video both render before the abstract; neither appears
  in `index.json`; the entry page carries the header and the gradient
  rule; a declared-but-missing `image` fails the build before the output
  directory is wiped; programme renders title-cased.
- Migration: `tft sync` on the live entry backfills `programme` and
  `supervisors` without disturbing `topics`, `score` or the summary.
