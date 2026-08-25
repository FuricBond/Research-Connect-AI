"""
Tests for scrapers.crossref.validator.
"""
import pytest

from scrapers.crossref.models import (
    NormalizedCrossrefAuthor,
    NormalizedCrossrefSource,
    NormalizedCrossrefWork,
)
from scrapers.crossref.validator import (
    validate_crossref_author,
    validate_crossref_source,
    validate_crossref_work,
)


def make_valid_work(**kwargs) -> NormalizedCrossrefWork:
    defaults = {
        "doi": "10.7717/peerj.4375",
        "title": "A Valid Title",
        "publication_year": 2023,
        "cited_by_count": 10,
        "reference_count": 5,
    }
    defaults.update(kwargs)
    return NormalizedCrossrefWork(**defaults)


class TestValidateCrossrefWork:
    def test_valid_work(self):
        work = make_valid_work()
        is_valid, errors = validate_crossref_work(work)
        assert is_valid is True
        assert errors == []

    def test_invalid_doi(self):
        work = make_valid_work(doi="invalid-doi")
        is_valid, errors = validate_crossref_work(work)
        assert is_valid is False
        assert any("valid canonical DOI" in err for err in errors)

    def test_empty_title(self):
        work = make_valid_work(title="   ")
        is_valid, errors = validate_crossref_work(work)
        assert is_valid is False
        assert any("title is required" in err for err in errors)

    def test_invalid_year_range(self):
        work = make_valid_work(publication_year=999)
        is_valid, errors = validate_crossref_work(work)
        assert is_valid is False
        assert any("publication_year" in err for err in errors)

        work2 = make_valid_work(publication_year=2105)
        is_valid2, errors2 = validate_crossref_work(work2)
        assert is_valid2 is False

    def test_negative_counts(self):
        work = make_valid_work(cited_by_count=-1)
        is_valid, errors = validate_crossref_work(work)
        assert is_valid is False
        assert any("cited_by_count" in err for err in errors)


class TestValidateCrossrefAuthor:
    def test_valid_author(self):
        author = NormalizedCrossrefAuthor(
            full_name="Jane Doe",
            orcid="0000-0003-1613-5981",
        )
        is_valid, errors = validate_crossref_author(author)
        assert is_valid is True

    def test_empty_name(self):
        author = NormalizedCrossrefAuthor(full_name="")
        is_valid, errors = validate_crossref_author(author)
        assert is_valid is False
        assert any("full_name is required" in err for err in errors)

    def test_invalid_orcid(self):
        author = NormalizedCrossrefAuthor(
            full_name="Jane Doe",
            orcid="invalid-orcid",
        )
        is_valid, errors = validate_crossref_author(author)
        assert is_valid is False
        assert any("orcid" in err for err in errors)


class TestValidateCrossrefSource:
    def test_valid_source(self):
        source = NormalizedCrossrefSource(title="Journal of AI")
        is_valid, errors = validate_crossref_source(source)
        assert is_valid is True

    def test_empty_title(self):
        source = NormalizedCrossrefSource(title="")
        is_valid, errors = validate_crossref_source(source)
        assert is_valid is False
