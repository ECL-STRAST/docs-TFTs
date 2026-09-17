import shutil

import pytest

from tft import latex
from tft.errors import CompileError

DOC = "\\documentclass{article}\n\\begin{document}\nHello.\n\\end{document}\n"


def test_find_main_picks_the_root_document(tmp_path):
    (tmp_path / "main.tex").write_text(DOC)
    (tmp_path / "chapter.tex").write_text("Just a fragment.\n")

    assert latex.find_main(tmp_path) == tmp_path / "main.tex"


def test_find_main_without_any_document(tmp_path):
    (tmp_path / "chapter.tex").write_text("Just a fragment.\n")

    with pytest.raises(CompileError, match="no root"):
        latex.find_main(tmp_path)


def test_find_main_with_several_documents(tmp_path):
    (tmp_path / "main.tex").write_text(DOC)
    (tmp_path / "poster.tex").write_text(DOC)

    with pytest.raises(CompileError, match="overleaf.main"):
        latex.find_main(tmp_path)


def test_build_failure_writes_the_log(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    out = tmp_path / "out"

    def fail(args, **kwargs):
        raise _fake_failure("! Undefined control sequence.\n")

    monkeypatch.setattr(latex.subprocess, "run", fail)

    with pytest.raises(CompileError):
        latex.build(src, src / "main.tex", out)

    assert "Undefined control sequence" in (out / latex.LOG_NAME).read_text()


def test_build_passes_shell_escape(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    out = tmp_path / "out"
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return _fake_success()

    monkeypatch.setattr(latex.subprocess, "run", fake_run)

    latex.build(src, src / "main.tex", out)

    assert latex.SHELL_ESCAPE in seen["args"]


def _fake_success():
    import subprocess

    return subprocess.CompletedProcess("latexmk", 0)


def _fake_failure(output):
    import subprocess

    return subprocess.CalledProcessError(1, "latexmk", output=output, stderr="")


@pytest.mark.skipif(shutil.which("latexmk") is None, reason="latexmk not installed")
def test_build_produces_a_pdf(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.tex").write_text(DOC)
    out = tmp_path / "out"

    pdf = latex.build(src, src / "main.tex", out)

    assert pdf.is_file()
    assert pdf.read_bytes().startswith(b"%PDF")
