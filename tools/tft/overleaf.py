"""Talks to the Overleaf git connector. The only module that runs git."""

import os
import subprocess
from pathlib import Path

from .errors import OverleafError

TOKEN_ENV = "OVERLEAF_GIT_TOKEN"
GIT_HOST = "git.overleaf.com"
REDACTED = "***"

# A credential helper that reads the token from the environment at git's
# request, instead of it ever appearing in a URL, argv, or .git/config.
CREDENTIAL_HELPER = f'!f(){{ echo username=git; echo "password=${TOKEN_ENV}"; }};f'
GIT_ENV = {
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "credential.helper",
    "GIT_CONFIG_VALUE_0": CREDENTIAL_HELPER,
    "GIT_TERMINAL_PROMPT": "0",
}


def token() -> str:
    """The Overleaf git token, from the environment and nowhere else."""
    value = os.environ.get(TOKEN_ENV)

    if not value:
        raise OverleafError(f"{TOKEN_ENV} is not set")

    return value


def url(project_id: str) -> str:
    return f"https://{GIT_HOST}/{project_id}"


def scrub(text: str, token: str) -> str:
    return text.replace(token, REDACTED)


def fetch(project_id: str, dest: Path) -> str:
    """Clone or update the project into dest. Returns the HEAD SHA."""
    secret = token()
    remote = url(project_id)

    if (dest / ".git").is_dir():
        _run(["git", "pull", "--ff-only", remote], secret, cwd=dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", remote, str(dest)], secret, cwd=dest.parent)

    return _run(["git", "rev-parse", "HEAD"], secret, cwd=dest).strip()


def _run(args: list[str], secret: str, cwd: Path) -> str:
    env = os.environ | GIT_ENV

    try:
        done = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        # Suppress exception chain: str(CalledProcessError) embeds the full
        # command line argv, which contains the token. Omit the chain so the
        # traceback does not leak it.
        raise OverleafError(scrub(exc.stderr or str(exc), secret)) from None

    return done.stdout
