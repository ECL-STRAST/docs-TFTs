"""Reads a thesis's own metadata out of its LaTeX sources.

Reports what it finds and returns None for what it does not; deciding
which fields are mandatory belongs to the caller, which can also accept
the human's overrides. Only malformed input raises.
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .errors import ExtractError

# The ETSIT template declares these three as \newcommand macros.
TITLE_MACRO = "tfgtitle"
AUTHOR_MACRO = "authorname"
DATE_MACRO = "fecha"

# Cover-page phrases, matched against accent-folded uppercase text so
# "Máster", "MASTER" and "máster" are one case.
DEGREES = (
    (re.compile(r"TRABAJO (?:DE )?FIN DE GRADO"), "bachelor"),
    (re.compile(r"TRABAJO (?:DE )?FIN DE MASTER"), "master"),
    (re.compile(r"TESIS DOCTORAL"), "phd"),
)

TEX_GLOB = "*.tex"

MAIN_FILE = "main.tex"
ABSTRACT_MARKER = r"\chapter*{Abstract}"
KEYWORDS_MARKER = r"\textbf{Keywords:}"

# Layout-only commands: they carry no words, so they simply go.
DROP = re.compile(r"\\(?:vfill|cleardoublepage|phantomsection|noindent)\b")
# Font switches whose argument IS the prose, so the braces are unwrapped.
UNWRAP = re.compile(r"\\(?:textbf|textit|emph|texttt|textsc)\s*\{")
# Anything else, with every brace group it owns: \addcontentsline takes
# three, and leaving them behind would drop "{chapter}{Abstract}" in the text.
MACRO = re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})*")
SPACES = re.compile(r"[ \t]+")
BLANKS = re.compile(r"\n{3,}")

YEAR = re.compile(r"(?:19|20)\d{2}")


@dataclass(frozen=True)
class Meta:
    """What a LaTeX source tree says about itself. None means not found."""
    title: str | None
    author: str | None
    year: int | None
    degree: str | None
    abstract: str | None
    keywords: tuple[str, ...]


def macro(text: str, name: str) -> str | None:
    """The argument of \\newcommand{\\name}{...}, or None if undeclared."""
    match = re.search(r"\\newcommand\s*\{\\" + name + r"\}\s*\{", text)

    if match is None:
        return None

    # match.end() - 1 is the opening brace of the value group.
    return braced(text, match.end() - 1)[0].strip()


def braced(text: str, open_at: int) -> tuple[str, int]:
    """Content of the {...} group at open_at, and the index past its close.

    Counts depth so a value containing \\emph{gait} survives intact.
    """
    depth = 0

    for i in range(open_at, len(text)):
        if text[i] == "{":
            depth += 1
            continue

        if text[i] != "}":
            continue

        depth -= 1

        if depth == 0:
            return text[open_at + 1:i], i + 1

    raise ExtractError("unbalanced braces in the LaTeX source")


def degree(src: Path) -> str | None:
    """The degree named on the cover, or None when no phrase appears."""
    found = set()

    for path in sorted(src.rglob(TEX_GLOB)):
        text = fold(path.read_text(encoding="utf-8", errors="ignore"))
        found |= {name for pattern, name in DEGREES if pattern.search(text)}

    # Two different phrases means a stray citation, not a second degree.
    if len(found) > 1:
        raise ExtractError(f"degree is ambiguous ({', '.join(sorted(found))}); pass --degree")

    return found.pop() if found else None


def fold(text: str) -> str:
    """Uppercase with accents stripped, for matching Spanish cover phrases."""
    decomposed = unicodedata.normalize("NFKD", text)

    return "".join(c for c in decomposed if not unicodedata.combining(c)).upper()


def detex(text: str) -> str:
    """LaTeX prose as plain text, paragraph breaks preserved."""
    text = DROP.sub("", text)
    text = _unwrap(text)
    text = MACRO.sub("", text)
    text = text.replace("{", "").replace("}", "")
    text = SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())

    return BLANKS.sub("\n\n", text).strip()


def read(src: Path) -> Meta:
    """Everything the source tree declares about itself."""
    main = (src / MAIN_FILE).read_text(encoding="utf-8", errors="ignore")
    abstract, keywords = _abstract(src)
    year = YEAR.search(macro(main, DATE_MACRO) or "")

    return Meta(
        title=macro(main, TITLE_MACRO),
        author=macro(main, AUTHOR_MACRO),
        year=int(year.group()) if year else None,
        degree=degree(src),
        abstract=abstract,
        keywords=keywords,
    )


def _unwrap(text: str) -> str:
    """Replace \\textbf{x} and friends with x, outermost first.

    Each pass exposes any nested switch to the next, so
    \\textbf{a \\emph{b}} resolves in two passes without recursion.
    """
    while True:
        match = UNWRAP.search(text)

        if match is None:
            return text

        inner, end = braced(text, match.end() - 1)
        text = text[:match.start()] + inner + text[end:]


def _abstract(src: Path) -> tuple[str | None, tuple[str, ...]]:
    """The English abstract and the author's keywords, both de-TeXed."""
    path = _abstract_file(src)

    if path is None:
        return None, ()

    _, _, after = path.read_text(encoding="utf-8").partition(ABSTRACT_MARKER)
    body, marker, tail = after.partition(KEYWORDS_MARKER)

    if not marker:
        return detex(body), ()

    words = [w.strip().lower() for w in detex(tail).rstrip(".").split(",")]

    return detex(body), tuple(w for w in words if w)


def _abstract_file(src: Path) -> Path | None:
    """Found by scanning, so a renamed chapter file still works."""
    for path in sorted(src.rglob(TEX_GLOB)):
        if ABSTRACT_MARKER in path.read_text(encoding="utf-8", errors="ignore"):
            return path

    return None
