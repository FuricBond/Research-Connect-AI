"""
Unit Tests for Phase 2.4M Empirical Academic Evaluation Dataset.
"""
from __future__ import annotations

import pytest

from app.evaluation.empirical_dataset import (
    AnnotationSource,
    DifficultyLevel,
    get_empirical_evaluation_dataset,
)


class TestEmpiricalEvaluationDataset:
    """Test suite verifying empirical dataset scale, disciplinary balance, and schema correctness."""

    @pytest.fixture
    def dataset(self):
        return get_empirical_evaluation_dataset()

    def test_dataset_size_meets_requirements(self, dataset) -> None:
        """Verify dataset contains at least 100 queries."""
        assert len(dataset) >= 100
        assert len(dataset) == 108

    def test_nine_disciplines_representation_and_balance(self, dataset) -> None:
        """Verify all 9 disciplines are represented without CS/AI dominance."""
        expected_disciplines = {
            "Computer Science",
            "Medicine",
            "Biology",
            "Mathematics",
            "Physics",
            "Engineering",
            "Social Sciences",
            "Economics",
            "Environmental Science",
        }
        actual_disciplines = {q.discipline for q in dataset}
        assert expected_disciplines == actual_disciplines

        # Discipline counts
        counts: dict[str, int] = {}
        for q in dataset:
            counts[q.discipline] = counts.get(q.discipline, 0) + 1

        total = len(dataset)
        cs_share = counts["Computer Science"] / total
        assert cs_share <= 0.20, f"Computer Science share is {cs_share:.1%}, must be <= 20%"

        for disc, count in counts.items():
            share = count / total
            assert share >= 0.08, f"Discipline {disc} has too few queries ({share:.1%})"

    def test_unique_query_ids_and_non_empty_text(self, dataset) -> None:
        """Verify query IDs are unique and query texts are meaningful."""
        query_ids = [q.query_id for q in dataset]
        assert len(query_ids) == len(set(query_ids)), "Duplicate query IDs found!"

        for q in dataset:
            assert len(q.query_text.strip()) >= 15
            assert len(q.candidate_fixtures) >= 3
            assert len(q.graded_relevance) == len(q.candidate_fixtures)

    def test_graded_relevance_scores_valid(self, dataset) -> None:
        """Verify graded relevance scores are in range [0.0, 3.0]."""
        for q in dataset:
            for cid, score in q.graded_relevance.items():
                assert 0.0 <= score <= 3.0, f"Invalid relevance score {score} for candidate {cid}"
            # Must have at least one highly relevant or relevant candidate
            has_relevant = any(score >= 2.0 for score in q.graded_relevance.values())
            assert has_relevant is True, f"Query {q.query_id} has no relevant candidates"

    def test_annotation_provenance_schema(self, dataset) -> None:
        """Verify explicit annotation provenance metadata."""
        for q in dataset:
            assert q.provenance is not None
            assert q.provenance.source in [
                AnnotationSource.EXPERT_DERIVED_RUBRIC,
                AnnotationSource.HUMAN_ANNOTATED,
                AnnotationSource.SYNTHETIC_BENCHMARK,
            ]
            assert len(q.provenance.annotator_role) > 0
            assert q.provenance.guidelines_version.startswith("v")

    def test_feature_slices_represented(self, dataset) -> None:
        """Verify queries include acronyms, ambiguity, and interdisciplinarity."""
        acronym_queries = [q for q in dataset if q.has_acronym]
        interdisciplinary_queries = [q for q in dataset if q.is_interdisciplinary]
        ambiguous_queries = [q for q in dataset if q.is_ambiguous]

        assert len(acronym_queries) >= 20
        assert len(interdisciplinary_queries) >= 20
        assert len(ambiguous_queries) >= 3
