"""Compiles a LaTeX source tree. The only module that runs latexmk."""

import subprocess
from pathlib import Path

from .errors import CompileError

LATEXMK = "latexmk"
LOG_NAME = "latexmk.log"
ROOT_MARKER = "\\documentclass"
# minted needs shell access to run Pygments; this lets a compiled
# document execute shell commands, so only compile trusted sources.
SHELL_ESCAPE = "-shell-escape"


def find_main(src: Path) -> Path:
    """The root .tex at the top of the source tree."""
    roots = [p for p in sorted(src.glob("*.tex")) if ROOT_MARKER in p.read_text(errors="ignore")]

    if not roots:
        raise CompileError(f"no root .tex found in {src}")

    if len(roots) > 1:
        names = ", ".join(p.name for p in roots)
        raise CompileError(f"several root files ({names}); set overleaf.main")

    return roots[0]


def build(src: Path, main: Path, out: Path) -> Path:
    """Compile main into out. On failure the log is kept for the human."""
    out.mkdir(parents=True, exist_ok=True)
    args = [
        LATEXMK, "-pdf", "-interaction=nonstopmode", "-halt-on-error",
        SHELL_ESCAPE, f"-outdir={out}", main.name,
    ]

    try:
        subprocess.run(args, cwd=src, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise CompileError(f"{LATEXMK} is not installed") from None
    except subprocess.CalledProcessError as exc:
        (out / LOG_NAME).write_text((exc.output or "") + (exc.stderr or ""), encoding="utf-8")
        raise CompileError(f"{main.name} failed to compile; see {out / LOG_NAME}") from None

    return out / f"{main.stem}.pdf"
