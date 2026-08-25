"""
Tests for ml.topic_analysis.normalization (slug generation, alias resolution, external taxonomy mapping).
"""
import pytest

from ml.topic_analysis.normalization import (
    TopicNormalizer,
    generate_topic_slug,
    normalize_topic_name,
)


class TestTopicNormalization:
    def test_normalize_topic_name(self):
        assert normalize_topic_name("  Natural  Language   Processing  ") == "natural language processing"
        assert normalize_topic_name("Human-Computer Interaction (HCI)") == "human-computer interaction hci"
        assert normalize_topic_name("Crème Brûlée Computing") == "creme brulee computing"
        assert normalize_topic_name(None) == ""

    def test_generate_topic_slug(self):
        assert generate_topic_slug("Natural Language Processing") == "natural-language-processing"
        assert generate_topic_slug("Artificial Intelligence (AI)") == "artificial-intelligence-ai"
        assert generate_topic_slug("Deep Learning & Neural Networks") == "deep-learning-neural-networks"
        assert generate_topic_slug(None) == ""


class TestTopicNormalizerAliases:
    @pytest.fixture
    def normalizer(self):
        return TopicNormalizer()

    def test_alias_nlp(self, normalizer):
        assert normalizer.resolve("NLP") == "natural-language-processing"
        assert normalizer.resolve("nlp") == "natural-language-processing"
        assert normalizer.resolve("Computational Linguistics") == "natural-language-processing"

    def test_alias_llm(self, normalizer):
        assert normalizer.resolve("LLM") == "large-language-models"
        assert normalizer.resolve("LLMs") == "large-language-models"
        assert normalizer.resolve("Large Language Model") == "large-language-models"
        assert normalizer.resolve("Foundation Models") == "large-language-models"
        assert normalizer.resolve("GPT") == "large-language-models"

    def test_alias_ai_and_ml(self, normalizer):
        assert normalizer.resolve("AI") == "artificial-intelligence"
        assert normalizer.resolve("ML") == "machine-learning"
        assert normalizer.resolve("DL") == "deep-learning"
        assert normalizer.resolve("RL") == "reinforcement-learning"
        assert normalizer.resolve("CV") == "computer-vision"
        assert normalizer.resolve("HCI") == "human-computer-interaction"

    def test_unknown_alias_returns_none(self, normalizer):
        assert normalizer.resolve("completely unknown buzzword 12345") is None
        assert normalizer.resolve("") is None
        assert normalizer.resolve(None) is None


class TestExternalTaxonomyMapping:
    @pytest.fixture
    def normalizer(self):
        return TopicNormalizer()

    def test_openalex_topic_mapping(self, normalizer):
        raw_topic = {
            "id": "https://openalex.org/T10028",
            "display_name": "Natural Language Processing",
            "score": 0.95,
        }
        slug, score = normalizer.resolve_openalex_topic(raw_topic)
        assert slug == "natural-language-processing"
        assert score == 0.95

    def test_crossref_subject_mapping(self, normalizer):
        assert normalizer.resolve_crossref_subject("Computer Vision and Pattern Recognition") == "computer-vision"
        assert normalizer.resolve_crossref_subject("Artificial Intelligence") == "artificial-intelligence"
        assert normalizer.resolve_crossref_subject("General Computer Science") == "computer-science"

    def test_unmapped_crossref_subject(self, normalizer):
        assert normalizer.resolve_crossref_subject("Medieval Poetry Studies") is None
