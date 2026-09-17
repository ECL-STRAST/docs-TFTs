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

### LaTeX requirements

A minimal TeX install is not enough. The group's theses need:
`acronym appendix booktabs enumitem eso-pic eurosym fancyvrb float framed
mathrsfs mathtools minted multirow placeins siunitx subfig titlesec xcolor`.
On Debian/Ubuntu:

    sudo apt install texlive-latex-extra texlive-latex-recommended \
            texlive-science texlive-fonts-extra python3-pygments

`texlive-full` also works if you'd rather not think about it.
`python3-pygments` is required because `minted` shells out to it.

`tft` compiles with `-shell-escape` for `minted`, which lets the document
run shell commands during compilation. Only compile sources you trust.

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

## Other commands

    tft sync <slug>     re-pull from Overleaf and recompile
    tft build           render site/ locally
