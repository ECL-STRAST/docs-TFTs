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
