"""The catalog as a whole: locating, listing, creating and checking entries."""

from functools import cmp_to_key
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


def _cmp_entries(e1: Entry, e2: Entry) -> int:
    """Compare entries by year descending, then slug descending."""
    if e1.year != e2.year:
        return e2.year - e1.year
    if e1.slug != e2.slug:
        return -1 if e1.slug > e2.slug else 1
    return 0


class Catalog:
    def __init__(self, cfg: Config):
        self._cfg = cfg

    def entries(self) -> list[Entry]:
        """Every entry in the catalog, newest first."""
        found = []

        for collection in COLLECTIONS.values():
            found += [store.read(d) for d in store.dirs(self._content(collection))]

        return sorted(found, key=cmp_to_key(_cmp_entries))

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
