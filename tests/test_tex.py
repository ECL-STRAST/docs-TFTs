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
