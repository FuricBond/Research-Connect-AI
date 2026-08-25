"""
Tests for scrapers.crossref.doi_utils (canonicalization and validation).
"""
import pytest

from scrapers.crossref.doi_utils import canonicalize_doi, is_valid_doi


class TestDoiCanonicalization:
    def test_bare_doi(self):
        assert canonicalize_doi("10.7717/peerj.4375") == "10.7717/peerj.4375"

    def test_https_doi_org_url(self):
        assert canonicalize_doi("https://doi.org/10.7717/peerj.4375") == "10.7717/peerj.4375"

    def test_http_doi_org_url(self):
        assert canonicalize_doi("http://doi.org/10.1007/s10462-021-10082-x") == "10.1007/s10462-021-10082-x"

    def test_dx_doi_org_resolver(self):
        assert canonicalize_doi("https://dx.doi.org/10.1145/3318464.3389700") == "10.1145/3318464.3389700"

    def test_doi_scheme_prefix(self):
        assert canonicalize_doi("doi:10.1093/oso/9780198828044.003.0003") == "10.1093/oso/9780198828044.003.0003"
        assert canonicalize_doi("DOI:10.1093/oso/9780198828044.003.0003") == "10.1093/oso/9780198828044.003.0003"

    def test_whitespace_stripping(self):
        assert canonicalize_doi("   10.1234/ABC-123   ") == "10.1234/ABC-123"

    def test_url_encoded_slash(self):
        assert canonicalize_doi("10.1000%2F182") == "10.1000/182"

    def test_trailing_punctuation_removal(self):
        assert canonicalize_doi("https://doi.org/10.1234/test.") == "10.1234/test"
        assert canonicalize_doi("https://doi.org/10.1234/test;") == "10.1234/test"
        assert canonicalize_doi("10.1234/test,") == "10.1234/test"

    def test_preserves_suffix_casing(self):
        # DOIs may have case-sensitive suffixes; suffix case should be preserved
        assert canonicalize_doi("10.1234/AbC-XyZ") == "10.1234/AbC-XyZ"

    def test_invalid_and_empty_inputs(self):
        assert canonicalize_doi(None) is None
        assert canonicalize_doi("") is None
        assert canonicalize_doi("   ") is None
        assert canonicalize_doi("not-a-doi") is None
        assert canonicalize_doi("http://example.com/paper/123") is None
        assert canonicalize_doi("10.123") is None  # no slash or suffix


class TestDoiValidation:
    def test_valid_dois(self):
        assert is_valid_doi("10.7717/peerj.4375") is True
        assert is_valid_doi("https://doi.org/10.1145/3318464.3389700") is True

    def test_invalid_dois(self):
        assert is_valid_doi(None) is False
        assert is_valid_doi("") is False
        assert is_valid_doi("invalid") is False
