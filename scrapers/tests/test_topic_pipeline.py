"""
Tests for ml.topic_analysis.process_topics CLI pipeline.
"""
import uuid
from unittest.mock import MagicMock, patch
import pytest

from ml.topic_analysis.process_topics import run_topic_processing


class DummyWork:
    def __init__(self, id, title, abstract=None, raw_metadata=None):
        self.id = id
        self.title = title
        self.abstract = abstract
        self.raw_metadata = raw_metadata or {}


class DummyOpp:
    def __init__(self, id, title, summary=None, description=None):
        self.id = id
        self.title = title
        self.summary = summary
        self.description = description


class TestTopicProcessingPipeline:
    def test_dry_run_research_works(self):
        dummy_work = DummyWork(
            id=uuid.uuid4(),
            title="Deep Reinforcement Learning for Robotic Control",
            abstract="We propose a policy gradient algorithm for robots.",
            raw_metadata={"topics": [{"display_name": "Robotics", "score": 0.95}]},
        )

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.side_effect = [
            [],              # TopicModel cache
            [dummy_work],    # ResearchWorkModel query
        ]
        mock_session.execute.return_value = mock_result

        with patch("app.db.session.SessionLocal") as MockSessionLocal:
            MockSessionLocal.return_value.__enter__.return_value = mock_session

            stats = run_topic_processing(dry_run=True, limit=5)

        assert stats["mode"] == "research_works"
        assert stats["dry_run"] is True
        assert stats["entities_processed"] == 1
        assert stats["errors"] == 0

    def test_dry_run_opportunities(self):
        dummy_opp = DummyOpp(
            id=uuid.uuid4(),
            title="International Conference on Natural Language Processing (NLP)",
            summary="Submissions on large language models and information retrieval.",
        )

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.side_effect = [
            [],             # TopicModel cache
            [dummy_opp],    # OpportunityModel query
        ]
        mock_session.execute.return_value = mock_result

        with patch("app.db.session.SessionLocal") as MockSessionLocal:
            MockSessionLocal.return_value.__enter__.return_value = mock_session

            stats = run_topic_processing(
                process_opportunities=True,
                dry_run=True,
                limit=5,
            )

        assert stats["mode"] == "opportunities"
        assert stats["dry_run"] is True
        assert stats["entities_processed"] == 1
        assert stats["errors"] == 0
