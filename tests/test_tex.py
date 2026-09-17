import pytest

from tft import tex
from tft.errors import ExtractError

MAIN = r"""
\newcommand{\authorname}{Belén Gómez Martínez}
\newcommand{\tfgtitle}{Design and development of an environment}
\newcommand{\fecha}{Junio 2026}
\begin{document}
\end{document}
"""


def test_reads_the_template_macros():
    assert tex.macro(MAIN, tex.TITLE_MACRO) == "Design and development of an environment"
    assert tex.macro(MAIN, tex.AUTHOR_MACRO) == "Belén Gómez Martínez"
    assert tex.macro(MAIN, tex.DATE_MACRO) == "Junio 2026"


def test_absent_macro_is_none_not_an_error():
    # tex reports what it finds; ingest decides what is mandatory.
    assert tex.macro(MAIN, "nosuchmacro") is None


def test_macro_value_may_contain_nested_braces():
    source = r"\newcommand{\tfgtitle}{A study of \emph{gait} in adults}"

    assert tex.macro(source, tex.TITLE_MACRO) == r"A study of \emph{gait} in adults"


def test_unbalanced_braces_are_reported():
    with pytest.raises(ExtractError, match="unbalanced"):
        tex.macro(r"\newcommand{\tfgtitle}{never closed", tex.TITLE_MACRO)


def test_meta_is_frozen():
    meta = tex.Meta(
        title="t", author="a", year=2026, degree="bachelor",
        abstract="text", keywords=("gait",),
    )

    with pytest.raises(AttributeError):
        meta.title = "other"


def _tree(tmp_path, **files):
    """A source tree: _tree(p, **{"main.tex": "...", "ch/a.tex": "..."})."""
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    return tmp_path


def test_bachelor_degree_from_the_cover(tmp_path):
    src = _tree(tmp_path, **{"chapters/0-preamble.tex": "TRABAJO FIN DE GRADO"})

    assert tex.degree(src) == "bachelor"


def test_degree_phrase_with_the_optional_de(tmp_path):
    src = _tree(tmp_path, **{"main.tex": "TRABAJO DE FIN DE GRADO"})

    assert tex.degree(src) == "bachelor"


def test_master_degree_is_accent_insensitive(tmp_path):
    src = _tree(tmp_path, **{"main.tex": "Trabajo de Fin de Máster"})

    assert tex.degree(src) == "master"


def test_phd_degree(tmp_path):
    src = _tree(tmp_path, **{"main.tex": "TESIS DOCTORAL"})

    assert tex.degree(src) == "phd"


def test_no_degree_phrase_is_none(tmp_path):
    src = _tree(tmp_path, **{"main.tex": "nothing relevant here"})

    assert tex.degree(src) is None


def test_two_degrees_is_ambiguous(tmp_path):
    src = _tree(
        tmp_path,
        **{"main.tex": "TRABAJO FIN DE GRADO", "biblio.tex": "Tesis Doctoral"},
    )

    with pytest.raises(ExtractError, match="ambiguous"):
        tex.degree(src)


ABSTRACT = r"""
\cleardoublepage
\phantomsection
\chapter*{Abstract}
\addcontentsline{toc}{chapter}{Abstract}
This Bachelor Thesis presents \textbf{CHLOE}, a web-based application.

It reads \textbf{C3D \emph{marker}} data and renders it in a browser.

\vfill
\textbf{Keywords:} Biomedical engineering, biomechanics, Motion Capture, C3D.
"""

FULL_MAIN = r"""
\newcommand{\authorname}{Belén Gómez Martínez}
\newcommand{\tfgtitle}{Design and development of an environment}
\newcommand{\fecha}{Junio 2026}
TRABAJO FIN DE GRADO
"""


def test_detex_unwraps_nested_emphasis():
    assert tex.detex(r"A \textbf{bold \emph{and italic} run} here") == "A bold and italic run here"


def test_detex_removes_a_macro_with_every_brace_group():
    assert tex.detex(r"\addcontentsline{toc}{chapter}{Abstract} text") == "text"


def test_detex_keeps_paragraph_breaks():
    assert tex.detex("One.\n\nTwo.") == "One.\n\nTwo."


def test_reads_the_abstract_and_keywords(tmp_path):
    src = _tree(tmp_path, **{"main.tex": FULL_MAIN, "chapters/B-abstract.tex": ABSTRACT})

    meta = tex.read(src)

    assert meta.abstract.startswith("This Bachelor Thesis presents CHLOE")
    assert "C3D marker" in meta.abstract
    assert "Keywords" not in meta.abstract
    assert meta.keywords == (
        "biomedical engineering", "biomechanics", "motion capture", "c3d",
    )


def test_abstract_is_found_whatever_the_chapter_is_called(tmp_path):
    src = _tree(tmp_path, **{"main.tex": FULL_MAIN, "parts/summary-en.tex": ABSTRACT})

    assert tex.read(src).abstract.startswith("This Bachelor Thesis")


def test_read_returns_every_field(tmp_path):
    src = _tree(tmp_path, **{"main.tex": FULL_MAIN, "chapters/B-abstract.tex": ABSTRACT})

    meta = tex.read(src)

    assert meta.title == "Design and development of an environment"
    assert meta.author == "Belén Gómez Martínez"
    assert meta.year == 2026
    assert meta.degree == "bachelor"


def test_missing_pieces_are_none_not_errors(tmp_path):
    src = _tree(tmp_path, **{"main.tex": "\\begin{document}\\end{document}"})

    meta = tex.read(src)

    assert meta.title is None
    assert meta.author is None
    assert meta.year is None
    assert meta.degree is None
    assert meta.abstract is None
    assert meta.keywords == ()


def test_abstract_without_keywords_yields_no_keywords(tmp_path):
    body = "\\chapter*{Abstract}\nJust prose, no keyword line.\n"
    src = _tree(tmp_path, **{"main.tex": FULL_MAIN, "chapters/B-abstract.tex": body})

    meta = tex.read(src)

    assert meta.abstract == "Just prose, no keyword line."
    assert meta.keywords == ()


def test_year_comes_from_the_spanish_date_macro(tmp_path):
    main = "\\newcommand{\\fecha}{Septiembre 2031}"
    src = _tree(tmp_path, **{"main.tex": main})

    assert tex.read(src).year == 2031


def test_undecodable_bytes_in_abstract_do_not_crash(tmp_path):
    src = _tree(tmp_path, **{"main.tex": FULL_MAIN})
    body = b"\\chapter*{Abstract}\nCaf\xe9 con leche, then prose.\n"
    (src / "chapters").mkdir()
    (src / "chapters" / "B-abstract.tex").write_bytes(body)

    assert tex.read(src).abstract is not None


def test_read_without_a_main_tex_returns_all_none(tmp_path):
    # A different template may root itself in another file; read() must
    # report absence, not crash, so overrides can still rescue it.
    src = _tree(tmp_path, **{"other-root.tex": "\\documentclass{article}"})

    meta = tex.read(src)

    assert meta.title is None
    assert meta.author is None
    assert meta.year is None
    assert meta.degree is None
    assert meta.abstract is None
    assert meta.keywords == ()
