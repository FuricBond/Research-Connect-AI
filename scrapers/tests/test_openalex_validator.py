"""
Tests for scrapers.openalex.validator.

All tests use in-memory Normalized* model instances — no network or DB calls.
"""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scrapers.openalex.models import (
    NormalizedInstitution,
    NormalizedResearchSource,
    NormalizedResearcher,
    NormalizedWork,
)
from scrapers.openalex.validator import (
    validate_institution,
    validate_research_source,
    validate_researcher,
    validate_work,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_work(**overrides) -> NormalizedWork:
    defaults = dict(
        openalex_id="W1234567",
        title="A valid title",
        publication_year=2023,
        cited_by_count=10,
        is_oa=False,
    )
    defaults.update(overrides)
    return NormalizedWork(**defaults)


def make_researcher(**overrides) -> NormalizedResearcher:
    defaults = dict(
        openalex_id="A1234567",
        display_name="Jane Doe",
        works_count=5,
        cited_by_count=20,
    )
    defaults.update(overrides)
    return NormalizedResearcher(**defaults)


def make_source(**overrides) -> NormalizedResearchSource:
    defaults = dict(
        openalex_id="S1234567",
        display_name="Journal of Science",
        works_count=1000,
        cited_by_count=50000,
    )
    defaults.update(overrides)
    return NormalizedResearchSource(**defaults)


def make_institution(**overrides) -> NormalizedInstitution:
    defaults = dict(
        openalex_id="I1234567",
        display_name="Test University",
        works_count=100,
        cited_by_count=5000,
    )
    defaults.update(overrides)
    return NormalizedInstitution(**defaults)


# ── Work validation ───────────────────────────────────────────────────────────


class TestValidateWork:
    def test_valid_work(self):
        is_valid, errors = validate_work(make_work())
        assert is_valid is True
        assert errors == []

    def test_invalid_openalex_id_pattern(self):
        is_valid, errors = validate_work(make_work(openalex_id="INVALID123"))
        assert is_valid is False
        assert any("W\\d+" in e for e in errors)

    def test_empty_title(self):
        is_valid, errors = validate_work(make_work(title="   "))
        assert is_valid is False
        assert any("title" in e for e in errors)

    def test_publication_year_too_old(self):
        is_valid, errors = validate_work(make_work(publication_year=999))
        assert is_valid is False
        assert any("publication_year" in e for e in errors)

    def test_publication_year_too_far_future(self):
        is_valid, errors = validate_work(make_work(publication_year=2101))
        assert is_valid is False
        assert any("publication_year" in e for e in errors)

    def test_valid_publication_year_boundary(self):
        is_valid, _ = validate_work(make_work(publication_year=1000))
        assert is_valid is True
        is_valid, _ = validate_work(make_work(publication_year=2100))
        assert is_valid is True

    def test_negative_cited_by_count(self):
        is_valid, errors = validate_work(make_work(cited_by_count=-1))
        assert is_valid is False
        assert any("cited_by_count" in e for e in errors)

    def test_invalid_landing_url(self):
        is_valid, errors = validate_work(make_work(landing_page_url="not-a-url"))
        assert is_valid is False
        assert any("landing_page_url" in e for e in errors)

    def test_valid_landing_url(self):
        is_valid, errors = validate_work(make_work(landing_page_url="https://doi.org/10.1234/test"))
        assert is_valid is True

    def test_empty_doi_is_invalid(self):
        is_valid, errors = validate_work(make_work(doi=""))
        assert is_valid is False
        assert any("doi" in e for e in errors)

    def test_none_doi_is_ok(self):
        is_valid, _ = validate_work(make_work(doi=None))
        assert is_valid is True

    def test_missing_optional_fields_still_valid(self):
        w = make_work(
            doi=None,
            abstract=None,
            publication_year=None,
            landing_page_url=None,
            work_type=None,
            language=None,
        )
        is_valid, errors = validate_work(w)
        assert is_valid is True


# ── Researcher validation ─────────────────────────────────────────────────────


class TestValidateResearcher:
    def test_valid_researcher(self):
        is_valid, errors = validate_researcher(make_researcher())
        assert is_valid is True

    def test_invalid_id_pattern(self):
        is_valid, errors = validate_researcher(make_researcher(openalex_id="NOTANID"))
        assert is_valid is False
        assert any("A\\d+" in e for e in errors)

    def test_empty_display_name(self):
        is_valid, errors = validate_researcher(make_researcher(display_name=""))
        assert is_valid is False

    def test_negative_works_count(self):
        is_valid, errors = validate_researcher(make_researcher(works_count=-5))
        assert is_valid is False

    def test_negative_cited_by_count(self):
        is_valid, errors = validate_researcher(make_researcher(cited_by_count=-1))
        assert is_valid is False

    def test_zero_counts_ok(self):
        is_valid, _ = validate_researcher(make_researcher(works_count=0, cited_by_count=0))
        assert is_valid is True


# ── ResearchSource validation ─────────────────────────────────────────────────


class TestValidateResearchSource:
    def test_valid_source(self):
        is_valid, errors = validate_research_source(make_source())
        assert is_valid is True

    def test_invalid_id_pattern(self):
        is_valid, errors = validate_research_source(make_source(openalex_id="X1234567"))
        assert is_valid is False
        assert any("S\\d+" in e for e in errors)

    def test_empty_display_name(self):
        is_valid, errors = validate_research_source(make_source(display_name=""))
        assert is_valid is False

    def test_invalid_homepage_url(self):
        is_valid, errors = validate_research_source(make_source(homepage_url="not-a-url"))
        assert is_valid is False

    def test_valid_homepage_url(self):
        is_valid, _ = validate_research_source(make_source(homepage_url="https://peerj.com"))
        assert is_valid is True

    def test_none_homepage_url_ok(self):
        is_valid, _ = validate_research_source(make_source(homepage_url=None))
        assert is_valid is True


# ── Institution validation ────────────────────────────────────────────────────


class TestValidateInstitution:
    def test_valid_institution(self):
        is_valid, errors = validate_institution(make_institution())
        assert is_valid is True

    def test_invalid_id_pattern(self):
        is_valid, errors = validate_institution(make_institution(openalex_id="W1234567"))
        assert is_valid is False
        assert any("I\\d+" in e for e in errors)

    def test_empty_display_name(self):
        is_valid, errors = validate_institution(make_institution(display_name=""))
        assert is_valid is False

    def test_invalid_homepage_url(self):
        is_valid, errors = validate_institution(make_institution(homepage_url="ftp://invalid"))
        assert is_valid is False

    def test_none_optional_fields_ok(self):
        is_valid, _ = validate_institution(
            make_institution(ror=None, country_code=None, institution_type=None, homepage_url=None)
        )
        assert is_valid is True
