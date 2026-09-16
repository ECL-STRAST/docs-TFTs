import subprocess

import pytest

from tft import overleaf
from tft.errors import OverleafError

TOKEN = "olp_secret123"


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def remote(tmp_path):
    """A local git repo standing in for an Overleaf project."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git("init", "-q", "-b", "main", cwd=origin)
    (origin / "main.tex").write_text("\\documentclass{article}\n\\begin{document}x\\end{document}\n")
    _git("add", "-A", cwd=origin)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init", cwd=origin)

    return origin


def test_url_embeds_the_token():
    assert overleaf.url("abc123", TOKEN) == f"https://git:{TOKEN}@git.overleaf.com/abc123"


def test_scrub_removes_every_occurrence():
    text = f"fatal: https://git:{TOKEN}@git.overleaf.com/abc failed, token {TOKEN}"

    scrubbed = overleaf.scrub(text, TOKEN)

    assert TOKEN not in scrubbed
    assert scrubbed.count("***") == 2


def test_token_missing_from_environment(monkeypatch):
    monkeypatch.delenv(overleaf.TOKEN_ENV, raising=False)

    with pytest.raises(OverleafError, match=overleaf.TOKEN_ENV):
        overleaf.token()


def test_fetch_clones_then_pulls(tmp_path, remote, monkeypatch):
    monkeypatch.setattr(overleaf, "url", lambda project_id, token: str(remote))
    monkeypatch.setenv(overleaf.TOKEN_ENV, TOKEN)
    dest = tmp_path / "work" / "2027-x"

    first = overleaf.fetch("abc123", dest)

    assert (dest / "main.tex").is_file()
    assert len(first) == 40

    # A second call must update in place, not fail on the existing directory.
    assert overleaf.fetch("abc123", dest) == first


def test_fetch_scrubs_the_token_from_failures(tmp_path, monkeypatch):
    monkeypatch.setenv(overleaf.TOKEN_ENV, TOKEN)
    # A local path that does not exist makes git fail without any network,
    # and carries the token into the error message git prints back.
    monkeypatch.setattr(
        overleaf, "url",
        lambda project_id, token: f"{tmp_path}/missing-{token}",
    )

    with pytest.raises(OverleafError) as caught:
        overleaf.fetch("does-not-exist", tmp_path / "dest")

    assert TOKEN not in str(caught.value)
    assert "***" in str(caught.value)


def test_token_not_stored_in_git_config(tmp_path, remote, monkeypatch):
    """After clone, .git/config must not contain the token."""
    monkeypatch.setattr(overleaf, "url", lambda project_id, token: str(remote))
    monkeypatch.setenv(overleaf.TOKEN_ENV, TOKEN)
    dest = tmp_path / "work" / "cloned"

    overleaf.fetch("abc123", dest)

    config = (dest / ".git" / "config").read_text()
    assert TOKEN not in config
    # Origin is still reachable for future pulls (without credentials).
    assert "url = https://git.overleaf.com/abc123" in config


def test_scrub_fallback_on_empty_stderr(tmp_path, monkeypatch):
    """When git writes no stderr, str(CalledProcessError) must be scrubbed."""
    monkeypatch.setenv(overleaf.TOKEN_ENV, TOKEN)

    def stub_run(*args, **kwargs):
        # Simulate git failure with empty stderr (e.g., permission denied).
        exc = subprocess.CalledProcessError(1, ["git", "clone", f"https://git:{TOKEN}@git.overleaf.com/xyz"])
        exc.stderr = ""
        raise exc

    monkeypatch.setattr(subprocess, "run", stub_run)

    with pytest.raises(OverleafError) as caught:
        overleaf.fetch("xyz", tmp_path / "dest")

    assert TOKEN not in str(caught.value)
    assert "***" in str(caught.value)
