"""Talks to the Overleaf git connector. The only module that runs git."""

import os
import subprocess
from pathlib import Path

from .errors import OverleafError

TOKEN_ENV = "OVERLEAF_GIT_TOKEN"
GIT_HOST = "git.overleaf.com"
REDACTED = "***"


def token() -> str:
    """The Overleaf git token, from the environment and nowhere else."""
    value = os.environ.get(TOKEN_ENV)

    if not value:
        raise OverleafError(f"{TOKEN_ENV} is not set")

    return value


def url(project_id: str, token: str) -> str:
    return f"https://git:{token}@{GIT_HOST}/{project_id}"


def scrub(text: str, token: str) -> str:
    return text.replace(token, REDACTED)


def fetch(project_id: str, dest: Path) -> str:
    """Clone or update the project into dest. Returns the HEAD SHA."""
    secret = token()
    remote = url(project_id, secret)

    if (dest / ".git").is_dir():
        _run(["git", "pull", "--ff-only", remote], secret, cwd=dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", remote, str(dest)], secret, cwd=dest.parent)

    return _run(["git", "rev-parse", "HEAD"], secret, cwd=dest).strip()


def _run(args: list[str], secret: str, cwd: Path) -> str:
    try:
        done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise OverleafError(scrub(exc.stderr or str(exc), secret)) from None

    return done.stdout
