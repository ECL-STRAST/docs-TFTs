import pytest

from tft import entry
from tft.errors import BadValue, MissingField, UnknownField

MINIMAL = {
    "type": "thesis",
    "title": "A database for biomechanical data",
    "author": "Silvia Nieves Serrano",
    "year": 2027,
    "degree": "bachelor",
    "topics": ["biomechanics"],
    "language": "en",
}


def test_minimal_entry_round_trips():
    parsed = entry.from_dict("2027-nieves-serrano-biomechanics-db", MINIMAL)

    assert parsed.slug == "2027-nieves-serrano-biomechanics-db"
    assert parsed.title == MINIMAL["title"]
    assert parsed.topics == ("biomechanics",)
    assert entry.to_dict(parsed) == MINIMAL


def test_optional_blocks_survive_the_round_trip():
    data = MINIMAL | {
        "supervisors": ["Rodrigo Garcia Carmona"],
        "overleaf": {"project_id": "698b41fa174f9aec00db94cb", "commit": "a3f19c2"},
        "repos": {"code": ["https://github.com/ECL-STRAST/libremotion-chloe"]},
        "slides": "slides.pdf",
    }

    parsed = entry.from_dict("2027-x", data)

    assert parsed.overleaf.project_id == "698b41fa174f9aec00db94cb"
    assert parsed.repos.code == ("https://github.com/ECL-STRAST/libremotion-chloe",)
    assert parsed.slides == "slides.pdf"
    assert entry.to_dict(parsed) == data


def test_unfinished_entry_is_valid():
    # No repos, no slides, no overleaf commit: the work is still in progress.
    parsed = entry.from_dict("2027-x", MINIMAL)

    assert parsed.repos.code == ()
    assert parsed.slides is None
    assert parsed.overleaf is None


@pytest.mark.parametrize("field", ["type", "title", "author", "year", "topics", "language"])
def test_missing_mandatory_field(field):
    data = {k: v for k, v in MINIMAL.items() if k != field}

    with pytest.raises(MissingField, match=field):
        entry.from_dict("2027-x", data)


def test_thesis_requires_a_degree():
    data = {k: v for k, v in MINIMAL.items() if k != "degree"}

    with pytest.raises(MissingField, match="degree"):
        entry.from_dict("2027-x", data)


def test_publication_does_not_require_a_degree():
    data = {k: v for k, v in MINIMAL.items() if k != "degree"} | {"type": "publication"}

    assert entry.from_dict("2027-x", data).degree is None


def test_publication_with_invalid_degree_is_rejected():
    data = {k: v for k, v in MINIMAL.items() if k != "type"} | {"type": "publication", "degree": "postdoc"}

    with pytest.raises(BadValue, match="degree"):
        entry.from_dict("2027-x", data)


def test_unknown_field_is_rejected():
    with pytest.raises(UnknownField, match="titel"):
        entry.from_dict("2027-x", MINIMAL | {"titel": "typo"})


def test_unknown_type_is_rejected():
    with pytest.raises(BadValue, match="type"):
        entry.from_dict("2027-x", MINIMAL | {"type": "poster"})


def test_unknown_degree_is_rejected():
    with pytest.raises(BadValue, match="degree"):
        entry.from_dict("2027-x", MINIMAL | {"degree": "postdoc"})


def test_year_must_be_an_integer():
    with pytest.raises(BadValue, match="year"):
        entry.from_dict("2027-x", MINIMAL | {"year": "2027"})


def test_topics_must_not_be_empty():
    with pytest.raises(BadValue, match="topics"):
        entry.from_dict("2027-x", MINIMAL | {"topics": []})


def test_doc_name_per_type():
    assert entry.DOC_NAME["thesis"] == "thesis.pdf"
    assert entry.DOC_NAME["publication"] == "paper.pdf"
