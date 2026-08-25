"""
Tests for scrapers.openalex.normalizer.

All tests use local fixture data — no network calls.
"""
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scrapers.openalex.normalizer import (
    extract_openalex_id,
    normalize_institution,
    normalize_research_source,
    normalize_researcher,
    normalize_work,
    _normalise_doi,
    _normalise_orcid,
    _normalise_ror,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "openalex"


def load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


# ── extract_openalex_id ───────────────────────────────────────────────────────


class TestExtractOpenAlexId:
    def test_full_work_url(self):
        assert extract_openalex_id("https://openalex.org/W2741809807") == "W2741809807"

    def test_full_author_url(self):
        assert extract_openalex_id("https://openalex.org/A5048491430") == "A5048491430"

    def test_full_source_url(self):
        assert extract_openalex_id("https://openalex.org/S1983995261") == "S1983995261"

    def test_full_institution_url(self):
        assert extract_openalex_id("https://openalex.org/I18014758") == "I18014758"

    def test_compact_id_passthrough(self):
        assert extract_openalex_id("W1234567") == "W1234567"

    def test_none_returns_none(self):
        assert extract_openalex_id(None) is None

    def test_empty_string_returns_none(self):
        assert extract_openalex_id("") is None

    def test_random_string_returns_none(self):
        assert extract_openalex_id("not-an-openalex-url") is None


# ── DOI / ORCID / ROR normalisation ──────────────────────────────────────────


class TestIdNormalisation:
    def test_normalise_doi_strips_prefix(self):
        assert _normalise_doi("https://doi.org/10.1234/test") == "10.1234/test"

    def test_normalise_doi_none(self):
        assert _normalise_doi(None) is None

    def test_normalise_doi_already_bare(self):
        assert _normalise_doi("10.1234/test") == "10.1234/test"

    def test_normalise_orcid_strips_prefix(self):
        assert _normalise_orcid("https://orcid.org/0000-0003-1613-5981") == "0000-0003-1613-5981"

    def test_normalise_orcid_none(self):
        assert _normalise_orcid(None) is None

    def test_normalise_ror_strips_prefix(self):
        assert _normalise_ror("https://ror.org/0213rcc28") == "0213rcc28"

    def test_normalise_ror_none(self):
        assert _normalise_ror(None) is None


# ── normalize_researcher ──────────────────────────────────────────────────────


class TestNormalizeResearcher:
    def test_normal_author_fixture(self):
        raw = load_fixture("author.json")
        researcher = normalize_researcher(raw)
        assert researcher.openalex_id == "A5048491430"
        assert researcher.display_name == "Heather Piwowar"
        assert researcher.orcid == "0000-0003-1613-5981"
        assert researcher.works_count == 42
        assert researcher.cited_by_count == 3200

    def test_missing_id_raises(self):
        with pytest.raises(ValueError, match="missing valid id"):
            normalize_researcher({"id": None, "display_name": "Someone"})

    def test_missing_display_name_raises(self):
        with pytest.raises(ValueError, match="missing display_name"):
            normalize_researcher({"id": "https://openalex.org/A1234567", "display_name": ""})

    def test_embedded_stub_normalises(self):
        stub = {
            "id": "https://openalex.org/A5048491430",
            "display_name": "Heather Piwowar",
            "orcid": "https://orcid.org/0000-0003-1613-5981",
        }
        r = normalize_researcher(stub)
        assert r.openalex_id == "A5048491430"
        assert r.orcid == "0000-0003-1613-5981"
        assert r.works_count == 0  # not in stub — defaults to 0


# ── normalize_research_source ─────────────────────────────────────────────────


class TestNormalizeResearchSource:
    def test_normal_source_fixture(self):
        raw = load_fixture("source.json")
        source = normalize_research_source(raw)
        assert source.openalex_id == "S1983995261"
        assert source.display_name == "PeerJ"
        assert source.issn_l == "2167-8359"
        assert source.is_oa is True
        assert source.is_in_doaj is True
        assert source.works_count == 25000
        assert source.host_organization == "PeerJ, Inc."

    def test_missing_id_raises(self):
        with pytest.raises(ValueError):
            normalize_research_source({"id": None, "display_name": "Something"})

    def test_issn_list(self):
        raw = load_fixture("source.json")
        source = normalize_research_source(raw)
        assert isinstance(source.issn, list)
        assert "2167-8359" in source.issn


# ── normalize_institution ─────────────────────────────────────────────────────


class TestNormalizeInstitution:
    def test_normal_institution_fixture(self):
        raw = load_fixture("institution.json")
        inst = normalize_institution(raw)
        assert inst.openalex_id == "I18014758"
        assert inst.display_name == "Simon Fraser University"
        assert inst.ror == "0213rcc28"
        assert inst.country_code == "CA"
        assert inst.institution_type == "education"
        assert inst.homepage_url == "https://www.sfu.ca"

    def test_missing_id_raises(self):
        with pytest.raises(ValueError):
            normalize_institution({"id": None, "display_name": "Uni"})

    def test_missing_display_name_raises(self):
        with pytest.raises(ValueError):
            normalize_institution({"id": "https://openalex.org/I1234567", "display_name": ""})


# ── normalize_work ────────────────────────────────────────────────────────────


class TestNormalizeWork:
    def test_normal_work_fixture(self):
        raw = load_fixture("work_normal.json")
        work = normalize_work(raw)
        assert work.openalex_id == "W2741809807"
        assert "Open Access" in work.title
        assert work.doi == "10.7717/peerj.4375"
        assert work.publication_year == 2018
        assert work.work_type == "article"
        assert work.language == "en"
        assert work.cited_by_count == 1245
        assert work.is_oa is True
        assert work.oa_status == "gold"

    def test_abstract_reconstructed(self):
        raw = load_fixture("work_normal.json")
        work = normalize_work(raw)
        assert work.abstract is not None
        assert "Open" in work.abstract

    def test_work_without_abstract(self):
        raw = load_fixture("work_no_abstract.json")
        work = normalize_work(raw)
        assert work.abstract is None

    def test_inverted_index_abstract(self):
        raw = load_fixture("work_inverted_index.json")
        work = normalize_work(raw)
        assert work.abstract == "Machine learning is transforming research."

    def test_multi_author_work(self):
        raw = load_fixture("work_multi_author.json")
        work = normalize_work(raw)
        assert len(work.authorships) == 3
        positions = [a.author_position for a in work.authorships]
        assert "first" in positions
        assert "last" in positions

    def test_primary_source_extracted(self):
        raw = load_fixture("work_normal.json")
        work = normalize_work(raw)
        assert work.primary_source is not None
        assert work.primary_source.openalex_id == "S1983995261"
        assert work.primary_source.display_name == "PeerJ"

    def test_no_primary_source_when_null(self):
        raw = load_fixture("work_no_abstract.json")
        work = normalize_work(raw)
        assert work.primary_source is None

    def test_missing_id_raises(self):
        with pytest.raises(ValueError, match="missing valid id"):
            normalize_work({"id": None, "title": "Some title"})

    def test_missing_title_raises(self):
        with pytest.raises(ValueError, match="missing title"):
            normalize_work({"id": "https://openalex.org/W1234567", "title": ""})

    def test_raw_metadata_contains_topics(self):
        raw = load_fixture("work_normal.json")
        work = normalize_work(raw)
        assert work.raw_metadata is not None
        assert "topics" in work.raw_metadata
        assert "keywords" in work.raw_metadata

    def test_institutions_extracted_from_authorships(self):
        raw = load_fixture("work_multi_author.json")
        work = normalize_work(raw)
        all_institutions = [
            inst
            for authorship in work.authorships
            for inst in authorship.institutions
        ]
        assert len(all_institutions) >= 2

    def test_malformed_work_raises(self):
        raw = load_fixture("work_malformed.json")
        with pytest.raises((ValueError, Exception)):
            normalize_work(raw)
