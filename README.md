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

    tft add --overleaf <project-id> --name nieves-serrano-biomechanics-db \
            --year 2027 --title "..." --author "..." --degree bachelor

Then edit the entry's `summary.md` and replace the `CHANGE-ME` topic with
tags from `taxonomy/topics.yaml`, adding any missing tag to that file first.
Finally:

    tft validate

`validate` checks schema, topics, referenced files, and repo URL syntax.
It never checks that a URL is reachable: CI holds no secrets and reaches
nothing, and group repos may be private.

Entries may be added before the work is defended: a draft PDF, no attached
repositories and no slides are all valid.

## Other commands

    tft sync <slug>     re-pull from Overleaf and recompile
    tft build           render site/ locally
