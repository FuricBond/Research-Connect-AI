"""
Unit tests for Reciprocal Rank Fusion (RRF) in app.search.rrf.
"""
from __future__ import annotations

from dataclasses import dataclass
import uuid
import pytest

from app.search.rrf import (
    DEFAULT_RRF_K,
    FusedCandidate,
    fuse_ranked_candidates,
)


@dataclass
class DummyCandidate:
    entity_id: uuid.UUID
    entity_type: str
    rank: int | None = None
    lexical_score: float | None = None
    similarity: float | None = None
    entity: str | None = None


class TestRRFCalculation:
    """Tests verifying RRF formula, rank weighting, and candidate fusion."""

    def test_single_result_list(self):
        id_1 = uuid.uuid4()
        id_2 = uuid.uuid4()

        items = [
            DummyCandidate(entity_id=id_1, entity_type="research_work", rank=1),
            DummyCandidate(entity_id=id_2, entity_type="research_work", rank=2),
        ]

        fused = fuse_ranked_candidates({"lexical": items}, k=60)

        assert len(fused) == 2
        # Score for rank 1: 1 / (60 + 1) = 1/61 ≈ 0.01639344
        # Score for rank 2: 1 / (60 + 2) = 1/62 ≈ 0.01612903
        assert fused[0].entity_id == id_1
        assert fused[0].rrf_score == pytest.approx(1.0 / 61.0, rel=1e-5)
        assert fused[0].ranks == {"lexical": 1}
        assert fused[0].retrieval_sources == ["lexical"]

        assert fused[1].entity_id == id_2
        assert fused[1].rrf_score == pytest.approx(1.0 / 62.0, rel=1e-5)
        assert fused[1].ranks == {"lexical": 2}

    def test_two_lists_overlapping_and_disjoint_candidates(self):
        """
        List 1 (Lexical):
          - A (rank 1)
          - B (rank 2)
          - C (rank 3)
        List 2 (Vector):
          - B (rank 1)
          - D (rank 2)
          - A (rank 3)

        Fused scores (k=60):
          - A: 1/(60+1) + 1/(60+3) = 1/61 + 1/63 ≈ 0.01639344 + 0.01587302 = 0.03226646
          - B: 1/(60+2) + 1/(60+1) = 1/62 + 1/61 ≈ 0.01612903 + 0.01639344 = 0.03252247
          - D: 1/(60+2) = 1/62 ≈ 0.01612903
          - C: 1/(60+3) = 1/63 ≈ 0.01587302

        Expected Order: B > A > D > C
        """
        id_a = uuid.uuid4()
        id_b = uuid.uuid4()
        id_c = uuid.uuid4()
        id_d = uuid.uuid4()

        lexical = [
            DummyCandidate(entity_id=id_a, entity_type="research_work", rank=1, lexical_score=0.9),
            DummyCandidate(entity_id=id_b, entity_type="research_work", rank=2, lexical_score=0.7),
            DummyCandidate(entity_id=id_c, entity_type="research_work", rank=3, lexical_score=0.5),
        ]
        vector = [
            DummyCandidate(entity_id=id_b, entity_type="research_work", rank=1, similarity=0.95),
            DummyCandidate(entity_id=id_d, entity_type="research_work", rank=2, similarity=0.88),
            DummyCandidate(entity_id=id_a, entity_type="research_work", rank=3, similarity=0.82),
        ]

        fused = fuse_ranked_candidates({"lexical": lexical, "vector": vector}, k=60)

        assert len(fused) == 4
        # Winner must be B
        assert fused[0].entity_id == id_b
        assert fused[0].rrf_score == pytest.approx(1.0 / 62.0 + 1.0 / 61.0, rel=1e-5)
        assert fused[0].ranks == {"lexical": 2, "vector": 1}
        assert fused[0].scores == {"lexical": 0.7, "vector": 0.95}
        assert fused[0].retrieval_sources == ["lexical", "vector"]

        # Runner-up must be A
        assert fused[1].entity_id == id_a
        assert fused[1].rrf_score == pytest.approx(1.0 / 61.0 + 1.0 / 63.0, rel=1e-5)
        assert fused[1].ranks == {"lexical": 1, "vector": 3}
        assert fused[1].scores == {"lexical": 0.9, "vector": 0.82}
        assert fused[1].retrieval_sources == ["lexical", "vector"]

        # Third must be D (only in vector)
        assert fused[2].entity_id == id_d
        assert fused[2].rrf_score == pytest.approx(1.0 / 62.0, rel=1e-5)
        assert fused[2].ranks == {"vector": 2}
        assert fused[2].retrieval_sources == ["vector"]

        # Fourth must be C (only in lexical)
        assert fused[3].entity_id == id_c
        assert fused[3].rrf_score == pytest.approx(1.0 / 63.0, rel=1e-5)
        assert fused[3].ranks == {"lexical": 3}
        assert fused[3].retrieval_sources == ["lexical"]

    def test_custom_k_parameter(self):
        id_1 = uuid.uuid4()
        items = [DummyCandidate(entity_id=id_1, entity_type="opportunity", rank=1)]

        fused_k20 = fuse_ranked_candidates({"lexical": items}, k=20)
        assert fused_k20[0].rrf_score == pytest.approx(1.0 / 21.0, rel=1e-5)

        fused_k100 = fuse_ranked_candidates({"lexical": items}, k=100)
        assert fused_k100[0].rrf_score == pytest.approx(1.0 / 101.0, rel=1e-5)

    def test_invalid_k_raises_error(self):
        with pytest.raises(ValueError, match="must be positive"):
            fuse_ranked_candidates({}, k=0)
        with pytest.raises(ValueError, match="must be positive"):
            fuse_ranked_candidates({}, k=-5)

    def test_limit_capping(self):
        ids = [uuid.uuid4() for _ in range(10)]
        items = [
            DummyCandidate(entity_id=item_id, entity_type="research_work", rank=idx)
            for idx, item_id in enumerate(ids, start=1)
        ]
        fused = fuse_ranked_candidates({"lexical": items}, limit=3)
        assert len(fused) == 3
        assert fused[0].entity_id == ids[0]
        assert fused[1].entity_id == ids[1]
        assert fused[2].entity_id == ids[2]

    def test_entity_type_segregation(self):
        """
        Verify that candidates sharing the exact same UUID but belonging to different
        entity_types (e.g. research_work vs opportunity) are treated as distinct entities.
        """
        shared_uuid = uuid.uuid4()

        work_candidate = DummyCandidate(
            entity_id=shared_uuid, entity_type="research_work", rank=1
        )
        opp_candidate = DummyCandidate(
            entity_id=shared_uuid, entity_type="opportunity", rank=1
        )

        fused = fuse_ranked_candidates(
            {"channel_a": [work_candidate], "channel_b": [opp_candidate]}
        )

        assert len(fused) == 2
        types = {c.entity_type for c in fused}
        assert types == {"research_work", "opportunity"}

    def test_empty_lists_return_empty(self):
        assert fuse_ranked_candidates({}) == []
        assert fuse_ranked_candidates({"lexical": [], "vector": []}) == []

    def test_deterministic_tie_breaking(self):
        """When RRF scores are equal, ordering is deterministic by entity_id."""
        id_1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
        id_2 = uuid.UUID("00000000-0000-0000-0000-000000000002")

        # Give both the exact same score from disjoint single-rank lists
        list_1 = [DummyCandidate(entity_id=id_2, entity_type="research_work", rank=1)]
        list_2 = [DummyCandidate(entity_id=id_1, entity_type="research_work", rank=1)]

        fused = fuse_ranked_candidates({"sys1": list_1, "sys2": list_2})
        assert len(fused) == 2
        assert fused[0].rrf_score == fused[1].rrf_score
        # Deterministic secondary sort by str(entity_id)
        assert fused[0].entity_id == id_1
        assert fused[1].entity_id == id_2
