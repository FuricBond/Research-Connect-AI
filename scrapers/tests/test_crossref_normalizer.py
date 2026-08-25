"""
Tests for scrapers.crossref.normalizer.
"""
import json
from pathlib import Path
import pytest

from scrapers.crossref.normalizer import (
    clean_jats_abstract,
    normalize_crossref_author,
    normalize_crossref_source,
    normalize_crossref_work,
    normalize_orcid,
    parse_crossref_date_parts,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "crossref"


def load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


class TestJatsAbstractCleaning:
    def test_strip_jats_paragraphs(self):
        raw = "<jats:p>Despite growing interest in Open Access...</jats:p>"
        assert clean_jats_abstract(raw) == "Despite growing interest in Open Access..."

    def test_strip_nested_formatting_and_entities(self):
        raw = "<jats:title>Abstract</jats:title><jats:p>NLP &amp; <jats:italic>deep learning</jats:italic>.</jats:p>"
        assert clean_jats_abstract(raw) == "Abstract NLP & deep learning."

    def test_empty_and_none(self):
        assert clean_jats_abstract(None) is None
        assert clean_jats_abstract("") is None
        assert clean_jats_abstract("   ") is None


class TestDatePartsParsing:
    def test_full_date(self):
        date_str, year = parse_crossref_date_parts({"date-parts": [[2018, 2, 13]]})
        assert date_str == "2018-02-13"
        assert year == 2018

    def test_year_month_date(self):
        date_str, year = parse_crossref_date_parts({"date-parts": [[2021, 10]]})
        assert date_str == "2021-10"
        assert year == 2021

    def test_year_only_date(self):
        date_str, year = parse_crossref_date_parts({"date-parts": [[2020]]})
        assert date_str == "2020"
        assert year == 2020

    def test_invalid_or_none(self):
        assert parse_crossref_date_parts(None) == (None, None)
        assert parse_crossref_date_parts({}) == (None, None)
        assert parse_crossref_date_parts({"date-parts": []}) == (None, None)


class TestOrcidNormalization:
    def test_url_orcid(self):
        assert normalize_orcid("http://orcid.org/0000-0003-1613-5981") == "0000-0003-1613-5981"
        assert normalize_orcid("https://orcid.org/0000-0003-1613-5981") == "0000-0003-1613-5981"

    def test_bare_orcid(self):
        assert normalize_orcid("0000-0003-1613-5981") == "0000-0003-1613-5981"

    def test_none(self):
        assert normalize_orcid(None) is None


class TestNormalizeAuthor:
    def test_given_and_family(self):
        raw = {
            "given": "Heather",
            "family": "Piwowar",
            "sequence": "first",
            "ORCID": "http://orcid.org/0000-0003-1613-5981",
            "affiliation": [{"name": "Impactstory, Sanford, NC, USA"}],
        }
        author = normalize_crossref_author(raw)
        assert author is not None
        assert author.full_name == "Heather Piwowar"
        assert author.orcid == "0000-0003-1613-5981"
        assert author.sequence == "first"
        assert "Impactstory, Sanford, NC, USA" in author.affiliations

    def test_name_only_consortium(self):
        raw = {"name": "The Distributed AI Consortium"}
        author = normalize_crossref_author(raw)
        assert author is not None
        assert author.full_name == "The Distributed AI Consortium"


class TestNormalizeSource:
    def test_container_and_issn(self):
        raw = {
            "container-title": ["PeerJ"],
            "publisher": "PeerJ, Inc.",
            "ISSN": ["2167-8359"],
        }
        source = normalize_crossref_source(raw)
        assert source is not None
        assert source.title == "PeerJ"
        assert source.publisher == "PeerJ, Inc."
        assert "2167-8359" in source.issn


class TestNormalizeWork:
    def test_normal_work(self):
        raw = load_fixture("work_normal.json")["message"]
        work = normalize_crossref_work(raw)

        assert work.doi == "10.7717/peerj.4375"
        assert "The state of OA" in work.title
        assert work.publication_year == 2018
        assert work.publication_date == "2018-02-13"
        assert work.volume == "6"
        assert work.page == "e4375"
        assert work.work_type == "article"
        assert work.is_oa is True
        assert len(work.authors) == 2
        assert work.authors[0].full_name == "Heather Piwowar"
        assert work.source is not None
        assert work.source.title == "PeerJ"

    def test_work_with_jats(self):
        raw = load_fixture("work_with_jats.json")
        work = normalize_crossref_work(raw)
        assert work.doi == "10.1007/s10462-021-10082-x"
        assert "<jats:" not in work.abstract
        assert "Sentiment analysis is an active research area" in work.abstract

    def test_multi_author_work(self):
        raw = load_fixture("work_multi_author.json")
        work = normalize_crossref_work(raw)
        assert len(work.authors) == 3
        assert work.authors[0].full_name == "Alice Smith"
        assert work.authors[0].orcid == "0000-0001-2345-6789"
        assert work.authors[2].full_name == "The Distributed AI Research Consortium"

    def test_book_chapter(self):
        raw = load_fixture("work_book_chapter.json")
        work = normalize_crossref_work(raw)
        assert work.work_type == "book-chapter"
        assert work.publication_year == 2019
        assert work.source.publisher == "Oxford University Press"

    def test_malformed_raises(self):
        raw = load_fixture("work_malformed.json")
        with pytest.raises(ValueError):
            normalize_crossref_work(raw)
