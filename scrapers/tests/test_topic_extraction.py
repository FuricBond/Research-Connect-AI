"""
Tests for ml.topic_analysis.extraction (keyword & keyphrase extraction).
"""
import pytest

from ml.topic_analysis.extraction import KeywordExtractor


class TestKeywordExtractor:
    @pytest.fixture
    def extractor(self):
        return KeywordExtractor()

    def test_extract_keywords_from_title(self, extractor):
        title = "A Scalable Framework for Distributed Deep Learning on Cloud Infrastructure"
        kws = extractor.extract_keywords(title=title)

        kw_terms = [k.keyword for k in kws]
        assert any("deep learning" in term for term in kw_terms)
        assert any("cloud infrastructure" in term or "distributed" in term for term in kw_terms)

        # Check that 'deep learning' matched canonical slug
        dl_kw = next((k for k in kws if "deep learning" in k.keyword), None)
        assert dl_kw is not None
        assert dl_kw.canonical_topic_slug == "deep-learning"
        assert dl_kw.is_title is True

    def test_stopword_removal(self, extractor):
        title = "The Study of and In an Artificial Intelligence System"
        kws = extractor.extract_keywords(title=title)
        kw_terms = [k.keyword for k in kws]

        # Stopwords should not be extracted as standalone unigrams
        assert "the" not in kw_terms
        assert "and" not in kw_terms
        assert "in" not in kw_terms
        assert any("artificial intelligence" in term for term in kw_terms)

    def test_source_keyword_integration(self, extractor):
        title = "Transformer Models in Healthcare"
        source_kws = ["Large Language Models", "Clinical Informatics"]
        kws = extractor.extract_keywords(title=title, source_keywords=source_kws)

        slugs = [k.canonical_topic_slug for k in kws if k.canonical_topic_slug]
        assert "large-language-models" in slugs
        assert "medical-informatics" in slugs or "transformers" in slugs

    def test_empty_and_none_text(self, extractor):
        assert extractor.extract_keywords(title=None, abstract=None) == []
        assert extractor.extract_keywords(title="", abstract="") == []
