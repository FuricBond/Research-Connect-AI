"""
Tests for ml.topic_analysis.assignment (multi-evidence topic assignment and confidence scoring).
"""
import pytest

from ml.topic_analysis.assignment import TopicAssigner


class TestTopicAssigner:
    @pytest.fixture
    def assigner(self):
        return TopicAssigner()

    def test_explicit_openalex_topic_assignment(self, assigner):
        title = "An Empirical Analysis of Search Engines"
        openalex_topics = [
            {"id": "https://openalex.org/T10028", "display_name": "Information Retrieval", "score": 0.95}
        ]

        result = assigner.assign_topics(title=title, openalex_topics=openalex_topics)
        assert len(result.assigned_topics) >= 1

        ir_topic = next((t for t in result.assigned_topics if t.topic_slug == "information-retrieval"), None)
        assert ir_topic is not None
        assert ir_topic.assignment_method == "SOURCE_EXPLICIT"
        assert ir_topic.confidence_score >= 0.90
        assert "OpenAlex" in ir_topic.source
        assert result.primary_topic is not None

    def test_multi_evidence_confidence_aggregation(self, assigner):
        # OpenAlex indicates NLP, Title indicates NLP, Crossref indicates Artificial Intelligence
        title = "Modern Natural Language Processing Techniques"
        abstract = "We present advanced NLP and Large Language Models for automated question answering."
        openalex_topics = [
            {"id": "https://openalex.org/T1", "display_name": "Natural Language Processing", "score": 0.90}
        ]
        crossref_subjects = ["Artificial Intelligence"]

        result = assigner.assign_topics(
            title=title,
            abstract=abstract,
            openalex_topics=openalex_topics,
            crossref_subjects=crossref_subjects,
        )

        assigned_slugs = [t.topic_slug for t in result.assigned_topics]
        assert "natural-language-processing" in assigned_slugs
        assert "artificial-intelligence" in assigned_slugs
        assert "large-language-models" in assigned_slugs

        # NLP had both explicit OpenAlex and title rule evidence, so it should have strong confidence
        nlp_topic = next(t for t in result.assigned_topics if t.topic_slug == "natural-language-processing")
        assert nlp_topic.confidence_score >= 0.95
        assert nlp_topic.evidence_count >= 2

    def test_primary_topic_selection(self, assigner):
        title = "Large Language Models in Question Answering"
        abstract = "An evaluation of LLMs for medical informatics and general AI."

        result = assigner.assign_topics(title=title, abstract=abstract)
        assert result.primary_topic is not None
        # Should select Large Language Models as primary because it appears directly in title and has high specificity
        assert result.primary_topic.topic_slug in ["large-language-models", "question-answering"]
        assert result.primary_topic.is_primary is True

    def test_ancestor_slugs_attached(self, assigner):
        title = "Transformer Architectures for Deep Learning"
        result = assigner.assign_topics(title=title)

        trans_topic = next((t for t in result.assigned_topics if t.topic_slug == "transformers"), None)
        if trans_topic:
            assert "deep-learning" in trans_topic.ancestor_slugs
            assert "machine-learning" in trans_topic.ancestor_slugs
            assert "artificial-intelligence" in trans_topic.ancestor_slugs

    def test_assign_research_work_dict(self, assigner):
        work_dict = {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "title": "Deep Reinforcement Learning for Autonomous Robotics",
            "abstract": "We explore deep Q-networks and policy gradients in robotic manipulation.",
            "raw_metadata": {
                "topics": [{"display_name": "Robotics", "score": 0.92}],
                "crossref": {"subject": ["Artificial Intelligence"]},
            },
        }
        result = assigner.assign_research_work(work_dict)
        assert result.entity_id == "123e4567-e89b-12d3-a456-426614174000"
        assigned_slugs = [t.topic_slug for t in result.assigned_topics]
        assert "robotics" in assigned_slugs
        assert "reinforcement-learning" in assigned_slugs or "deep-learning" in assigned_slugs

    def test_assign_opportunity_dict(self, assigner):
        opp_dict = {
            "id": "123e4567-e89b-12d3-a456-426614174001",
            "title": "International Conference on Computer Vision and Pattern Recognition",
            "summary": "Special session on object detection and generative AI.",
        }
        result = assigner.assign_opportunity(opp_dict)
        assigned_slugs = [t.topic_slug for t in result.assigned_topics]
        assert "computer-vision" in assigned_slugs
        assert any(slug in assigned_slugs for slug in ["object-detection", "generative-ai"])
