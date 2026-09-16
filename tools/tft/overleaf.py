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


def _tokenless_url(project_id: str) -> str:
    """Git URL without credentials. Safe to store in .git/config."""
    return f"https://{GIT_HOST}/{project_id}"


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
        # Remove the token from .git/config after clone. The credential
        # was only needed for initial checkout; subsequent pulls pass the
        # remote URL explicitly and do not use the stored origin.
        safe_remote = _tokenless_url(project_id)
        _run(["git", "remote", "set-url", "origin", safe_remote], secret, cwd=dest)

    return _run(["git", "rev-parse", "HEAD"], secret, cwd=dest).strip()


def _run(args: list[str], secret: str, cwd: Path) -> str:
    try:
        done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        # Suppress exception chain: str(CalledProcessError) embeds the full
        # command line argv, which contains the token. Omit the chain so the
        # traceback does not leak it.
        raise OverleafError(scrub(exc.stderr or str(exc), secret)) from None

    return done.stdout
