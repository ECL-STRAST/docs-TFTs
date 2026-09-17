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
OPTIONAL = (
    "degree", "venue", "supervisors", "overleaf", "repos", "slides",
    "keywords", "score", "honours", "photo",
)

MAX_SCORE = 10

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
    keywords: tuple[str, ...] = ()
    score: float | None = None
    honours: bool = False
    photo: str | None = None
    summary: str = ""   # summary.md's body, attached by the store


def from_dict(slug: str, data: dict) -> Entry:
    """Parse and validate one entry.yaml. Raises a SchemaError subclass."""
    _reject_unknown(data)
    _require(data, MANDATORY)

    kind = _one_of(data, "type", TYPES)

    # A thesis has a degree; a publication will have a venue instead.
    if kind == THESIS:
        _require(data, ("degree",))

    # Degree enum is unconditional: if present, must be valid.
    if "degree" in data:
        _one_of(data, "degree", DEGREES)

    _check_types(data)
    _check_score(data)
    _check_keywords(data)
    _check_filename(data, "photo")
    _check_filename(data, "slides")

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
        keywords=tuple(data.get("keywords", ())),
        score=data.get("score"),
        honours=bool(data.get("honours", False)),
        photo=data.get("photo"),
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

    # 0 is a real score, so _put's truthiness test would lose it.
    if entry.score is not None:
        out["score"] = entry.score

    _put(out, "honours", entry.honours)
    _put(out, "keywords", list(entry.keywords))
    _put(out, "photo", entry.photo)

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


def _check_score(data: dict) -> None:
    score = data.get("score")

    if score is not None:
        # bool is an int subclass; honours must not sneak in as a score.
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise BadValue("score must be a number")

        if not 0 <= score <= MAX_SCORE:
            raise BadValue(f"score must be between 0 and {MAX_SCORE}, got {score}")

    # An honours mark qualifies a score; alone it says nothing.
    if data.get("honours") and score is None:
        raise BadValue("honours needs a score")


def _check_keywords(data: dict) -> None:
    if "keywords" not in data:
        return

    keywords = data["keywords"]

    if not isinstance(keywords, list) or not keywords:
        raise BadValue("keywords must be a non-empty list")

    for word in keywords:
        if not isinstance(word, str) or not word.strip():
            raise BadValue("keywords must be non-empty strings")


def _check_filename(data: dict, name: str) -> None:
    """A declared file (photo, slides) must be a bare name in the folder."""
    value = data.get(name)

    if value is None:
        return

    if not isinstance(value, str) or not value.strip():
        raise BadValue(f"{name} must be a non-empty string")

    if "/" in value or "\\" in value or ".." in value:
        raise BadValue(f"{name} must not contain a path separator")


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
