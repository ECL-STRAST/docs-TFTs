"""Reads a thesis's own metadata out of its LaTeX sources.

Reports what it finds and returns None for what it does not; deciding
which fields are mandatory belongs to the caller, which can also accept
the human's overrides. Only malformed input raises.
"""

import re
from dataclasses import dataclass

from .errors import ExtractError

# The ETSIT template declares these three as \newcommand macros.
TITLE_MACRO = "tfgtitle"
AUTHOR_MACRO = "authorname"
DATE_MACRO = "fecha"


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
