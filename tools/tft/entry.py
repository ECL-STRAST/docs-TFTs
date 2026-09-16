"""The catalog's domain type and the rules an entry.yaml must satisfy."""

from dataclasses import dataclass, field
from typing import Any

from .errors import BadValue, MissingField, UnknownField

THESIS = "thesis"
PUBLICATION = "publication"
TYPES = (THESIS, PUBLICATION)

DEGREES = ("bachelor", "master", "phd")

DOC_NAME = {THESIS: "thesis.pdf", PUBLICATION: "paper.pdf"}

MANDATORY = ("type", "title", "author", "year", "topics", "language")
OPTIONAL = ("degree", "venue", "supervisors", "overleaf", "repos", "slides")

TEXT_FIELDS = ("title", "author", "language")


@dataclass(frozen=True)
class Overleaf:
    project_id: str
    commit: str | None = None
    main: str | None = None     # only when root-file detection is ambiguous
    mirror: str | None = None   # URL of the source mirror in the private repo


@dataclass(frozen=True)
class Repos:
    code: tuple[str, ...] = ()
    docs: str | None = None


@dataclass(frozen=True)
class Entry:
    slug: str
    type: str
    title: str
    author: str
    year: int
    topics: tuple[str, ...]
    language: str
    degree: str | None = None
    venue: str | None = None
    supervisors: tuple[str, ...] = ()
    overleaf: Overleaf | None = None
    repos: Repos = field(default_factory=Repos)
    slides: str | None = None
    summary: str = ""   # summary.md's body, attached by the store


def from_dict(slug: str, data: dict) -> Entry:
    """Parse and validate one entry.yaml. Raises a SchemaError subclass."""
    _reject_unknown(data)
    _require(data, MANDATORY)

    kind = _one_of(data, "type", TYPES)

    # A thesis has a degree; a publication will have a venue instead.
    if kind == THESIS:
        _require(data, ("degree",))
        _one_of(data, "degree", DEGREES)

    _check_types(data)

    return Entry(
        slug=slug,
        type=kind,
        title=data["title"],
        author=data["author"],
        year=data["year"],
        topics=tuple(data["topics"]),
        language=data["language"],
        degree=data.get("degree"),
        venue=data.get("venue"),
        supervisors=tuple(data.get("supervisors", ())),
        overleaf=_overleaf(data.get("overleaf")),
        repos=_repos(data.get("repos")),
        slides=data.get("slides"),
    )


def to_dict(entry: Entry) -> dict:
    """Serialise back to the entry.yaml shape, omitting what is unset."""
    out: dict[str, Any] = {
        "type": entry.type,
        "title": entry.title,
        "author": entry.author,
        "year": entry.year,
    }

    _put(out, "degree", entry.degree)
    _put(out, "venue", entry.venue)
    _put(out, "supervisors", list(entry.supervisors))

    out["topics"] = list(entry.topics)
    out["language"] = entry.language

    if entry.overleaf is not None:
        out["overleaf"] = _put_all(
            project_id=entry.overleaf.project_id,
            commit=entry.overleaf.commit,
            main=entry.overleaf.main,
            mirror=entry.overleaf.mirror,
        )

    repos = _put_all(code=list(entry.repos.code), docs=entry.repos.docs)
    _put(out, "repos", repos)
    _put(out, "slides", entry.slides)

    return out


def _reject_unknown(data: dict) -> None:
    for key in data:
        if key not in MANDATORY and key not in OPTIONAL:
            raise UnknownField(f"unknown field: {key}")


def _require(data: dict, names: tuple[str, ...]) -> None:
    for name in names:
        if name not in data:
            raise MissingField(f"missing field: {name}")


def _one_of(data: dict, name: str, allowed: tuple[str, ...]) -> str:
    value = data[name]

    if value not in allowed:
        raise BadValue(f"{name} must be one of {', '.join(allowed)}, got {value!r}")

    return value


def _check_types(data: dict) -> None:
    if not isinstance(data["year"], int):
        raise BadValue("year must be an integer")

    for name in TEXT_FIELDS:
        if not isinstance(data[name], str) or not data[name].strip():
            raise BadValue(f"{name} must be a non-empty string")

    topics = data["topics"]

    if not isinstance(topics, list) or not topics:
        raise BadValue("topics must be a non-empty list")


def _overleaf(raw: dict | None) -> Overleaf | None:
    if raw is None:
        return None

    if "project_id" not in raw:
        raise MissingField("missing field: overleaf.project_id")

    return Overleaf(
        project_id=raw["project_id"],
        commit=raw.get("commit"),
        main=raw.get("main"),
        mirror=raw.get("mirror"),
    )


def _repos(raw: dict | None) -> Repos:
    if raw is None:
        return Repos()

    return Repos(code=tuple(raw.get("code", ())), docs=raw.get("docs"))


def _put(out: dict, name: str, value: Any) -> None:
    if value:
        out[name] = value


def _put_all(**values: Any) -> dict:
    return {name: value for name, value in values.items() if value}
