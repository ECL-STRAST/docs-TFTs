"""Brings an Overleaf project into the catalog: fetch, compile, mirror."""

import dataclasses
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import latex, overleaf, store, tex
from .catalog import COLLECTIONS, Catalog
from .config import Config
from .entry import DOC_NAME, THESIS, Entry, Overleaf
from .errors import ExtractError

SOURCES = "sources"

# Everything an entry cannot be created without. Each may instead be
# supplied by hand when a thesis does not follow the group's template.
REQUIRED = ("title", "author", "year", "degree", "abstract", "keywords")


@dataclass(frozen=True)
class Overrides:
    """What the human supplies when the source does not declare it."""
    title: str | None = None
    author: str | None = None
    year: int | None = None
    degree: str | None = None


@dataclass(frozen=True)
class SyncResult:
    """What a sync did, and anything the human should look at."""
    changed: bool
    warnings: tuple[str, ...] = ()


class Ingest:
    def __init__(self, cfg: Config, catalog: Catalog, fetch=overleaf.fetch, build=latex.build):
        self._cfg = cfg
        self._catalog = catalog
        self._fetch = fetch
        self._build = build

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

    def _compile(self, work: Path, main: str | None) -> Path:
        root = work / main if main else latex.find_main(work)

        return self._build(work, root, self._cfg.work / "out")

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

    def _install(self, entry: Entry, folder: Path, pdf: Path, work: Path, sha, project_id) -> None:
        """Everything that must only happen once the compile has succeeded."""
        # Mirror first: it is the likeliest step to fail (missing private
        # repo, rmtree of the old mirror). Failing here must not leave the
        # public PDF and entry.yaml disagreeing about which commit built it.
        mirror = self._mirror(entry, work)

        target = folder / DOC_NAME[entry.type]
        tmp = target.with_name(target.name + ".tmp")

        # Remove the partial temp file on a failed copy (disk full,
        # interrupted): the live PDF must stay untouched either way.
        try:
            shutil.copyfile(pdf, tmp)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        os.replace(tmp, target)
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
        collection = COLLECTIONS[entry.type]
        dest = self._cfg.private / SOURCES / collection / entry.slug

        if dest.exists():
            shutil.rmtree(dest)

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(work, dest, ignore=shutil.ignore_patterns(".git"))

        return f"{self._cfg.mirror_base}/{collection}/{entry.slug}"


# Fields the CLI can supply; the rest must be fixed in the LaTeX itself.
OVERRIDABLE = ("title", "author", "year", "degree")


def _year_drift(was: int, now: int, slug: str) -> tuple[str, ...]:
    """The slug embeds the year, but renaming would break shared URLs."""
    if was == now:
        return ()

    return (f"{slug}: year is now {now}; the folder name still says {was}",)


def _remedy(missing: list[str]) -> str:
    """What the human can do about each field that could not be read."""
    flags = [f"--{name}" for name in missing if name in OVERRIDABLE]

    if not flags:
        return "fix the thesis source"

    return f"pass {' '.join(flags)}"
