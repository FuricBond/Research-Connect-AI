"""
Deterministic Benchmark Dataset & Ground Truth Scenarios for Phase 2.4H.

Defines 16 representative evaluation scenarios covering:
  - Vector vs Lexical vs Topic retrieval behaviors
  - Cross-channel candidate fusion (RRF)
  - Publication type compatibility & deadline urgency
  - Edge cases, missing data, and degraded signals

Ground Truth Categorization:
  - 'SYNTHETIC_FIXTURE': Constructive test case where relevance is mathematically defined.
  - 'HEURISTIC_METADATA': Inferred ground truth derived from deterministic taxonomy overlap,
    publication type compatibility, and lexical/semantic similarity.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any
import uuid


class GroundTruthCategory(str, Enum):
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    HEURISTIC_METADATA = "HEURISTIC_METADATA"


@dataclass(frozen=True)
class BenchmarkQueryScenario:
    """Represents a single deterministic benchmark query scenario."""

    scenario_id: str
    name: str
    category: GroundTruthCategory
    description: str
    query_type: str  # 'RESEARCH_SEARCH', 'SIMILAR_RESEARCH', 'OPPORTUNITY_MATCH'
    query_payload: dict[str, Any]
    candidate_fixtures: list[dict[str, Any]]
    expected_top_ids: list[str]
    graded_relevance: dict[str, float]  # ID -> graded relevance score [0.0 - 3.0]
    metadata: dict[str, Any] = field(default_factory=dict)


def get_benchmark_dataset() -> list[BenchmarkQueryScenario]:
    """Return the complete suite of 16 deterministic benchmark scenarios."""
    now = datetime.now(timezone.utc)
    scenarios: list[BenchmarkQueryScenario] = []

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Exact Research-Topic Match
    # ─────────────────────────────────────────────────────────────────────────
    id_1_src = "11111111-0001-0000-0000-000000000000"
    id_1_c1 = "11111111-0001-0000-0000-000000000001"
    id_1_c2 = "11111111-0001-0000-0000-000000000002"
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_01_EXACT_TOPIC_MATCH",
            name="Exact Research-Topic Match",
            category=GroundTruthCategory.HEURISTIC_METADATA,
            description="Query matches exact canonical topics and high semantic proximity.",
            query_type="SIMILAR_RESEARCH",
            query_payload={"work_id": id_1_src, "title": "Graph Neural Networks for Drug Discovery"},
            candidate_fixtures=[
                {
                    "id": id_1_c1,
                    "title": "Deep Graph Architectures for Molecular Property Prediction",
                    "semantic_similarity": 0.94,
                    "lexical_score": 2.1,
                    "topic_similarity": 0.95,
                    "publication_year": 2024,
                    "work_type": "article",
                },
                {
                    "id": id_1_c2,
                    "title": "General Survey on Deep Learning Techniques",
                    "semantic_similarity": 0.50,
                    "lexical_score": 0.5,
                    "topic_similarity": 0.30,
                    "publication_year": 2018,
                    "work_type": "article",
                },
            ],
            expected_top_ids=[id_1_c1],
            graded_relevance={id_1_c1: 3.0, id_1_c2: 1.0},
        )
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Strong Semantic Match with Different Terminology (Paraphrase / Synonym)
    # ─────────────────────────────────────────────────────────────────────────
    id_2_c1 = "22222222-0002-0000-0000-000000000001"
    id_2_c2 = "22222222-0002-0000-0000-000000000002"
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_02_SEMANTIC_SYNONYM",
            name="Strong Semantic Match with Different Terminology",
            category=GroundTruthCategory.SYNTHETIC_FIXTURE,
            description="Query uses synonyms (e.g. 'autonomous driving vehicles' vs 'self-driving cars'). Vector channel dominates lexical channel.",
            query_type="RESEARCH_SEARCH",
            query_payload={"q": "autonomous vehicular path navigation"},
            candidate_fixtures=[
                {
                    "id": id_2_c1,
                    "title": "Self-Driving Car Trajectory Planning in Urban Scenarios",
                    "semantic_similarity": 0.92,
                    "lexical_score": 0.1,  # Low lexical overlap, high semantic similarity
                    "publication_year": 2025,
                },
                {
                    "id": id_2_c2,
                    "title": "Navigation Algorithms for Marine Vessels",
                    "semantic_similarity": 0.45,
                    "lexical_score": 1.8,  # Lexical match on 'navigation' but different domain
                    "publication_year": 2020,
                },
            ],
            expected_top_ids=[id_2_c1],
            graded_relevance={id_2_c1: 3.0, id_2_c2: 0.5},
        )
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Strong Lexical Match with Weaker Semantic Similarity
    # ─────────────────────────────────────────────────────────────────────────
    id_3_c1 = "33333333-0003-0000-0000-000000000001"
    id_3_c2 = "33333333-0003-0000-0000-000000000002"
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_03_LEXICAL_KEYWORD_MATCH",
            name="Strong Lexical Match with Specific Technical Acronyms",
            category=GroundTruthCategory.SYNTHETIC_FIXTURE,
            description="Query searches specific acronym/named method (e.g. 'BERT-wwm-ext').",
            query_type="RESEARCH_SEARCH",
            query_payload={"q": "BERT-wwm-ext language representations"},
            candidate_fixtures=[
                {
                    "id": id_3_c1,
                    "title": "Pre-Training with Whole Word Masking for Chinese BERT (BERT-wwm-ext)",
                    "semantic_similarity": 0.85,
                    "lexical_score": 3.4,
                    "publication_year": 2021,
                },
                {
                    "id": id_3_c2,
                    "title": "General Contextualized Word Representations",
                    "semantic_similarity": 0.78,
                    "lexical_score": 0.4,
                    "publication_year": 2019,
                },
            ],
            expected_top_ids=[id_3_c1],
            graded_relevance={id_3_c1: 3.0, id_3_c2: 1.5},
        )
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Shared Taxonomy Ancestor without Exact Topic Overlap (DAG Hierarchical Proximity)
    # ─────────────────────────────────────────────────────────────────────────
    id_4_src = "44444444-0004-0000-0000-000000000000"
    id_4_c1 = "44444444-0004-0000-0000-000000000001"
    id_4_c2 = "44444444-0004-0000-0000-000000000002"
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_04_DAG_ANCESTOR_PROXIMITY",
            name="Shared Taxonomy Ancestor without Exact Topic Overlap",
            category=GroundTruthCategory.HEURISTIC_METADATA,
            description="Child topics under the same parent node in the Taxonomy DAG share moderate hierarchical proximity.",
            query_type="SIMILAR_RESEARCH",
            query_payload={"work_id": id_4_src, "topic": "Convolutional Neural Networks"},
            candidate_fixtures=[
                {
                    "id": id_4_c1,
                    "title": "Vision Transformers for Object Detection",
                    "semantic_similarity": 0.82,
                    "lexical_score": 0.8,
                    "topic_similarity": 0.65,  # Sibling under Computer Vision
                    "publication_year": 2024,
                },
                {
                    "id": id_4_c2,
                    "title": "Geological Soil Mechanics in Coastal Areas",
                    "semantic_similarity": 0.10,
                    "lexical_score": 0.0,
                    "topic_similarity": 0.0,  # Unrelated subtree
                    "publication_year": 2022,
                },
            ],
            expected_top_ids=[id_4_c1],
            graded_relevance={id_4_c1: 2.5, id_4_c2: 0.0},
        )
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Strong Topic Overlap
    # ─────────────────────────────────────────────────────────────────────────
    id_5_src = "55555555-0005-0000-0000-000000000000"
    id_5_c1 = "55555555-0005-0000-0000-000000000001"
    id_5_c2 = "55555555-0005-0000-0000-000000000002"
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_05_STRONG_TOPIC_OVERLAP",
            name="Strong Multi-Topic Canonical Overlap",
            category=GroundTruthCategory.HEURISTIC_METADATA,
            description="Candidates sharing 3+ primary topics outrank single-topic matches.",
            query_type="SIMILAR_RESEARCH",
            query_payload={"work_id": id_5_src},
            candidate_fixtures=[
                {
                    "id": id_5_c1,
                    "title": "Federated Learning for Privacy-Preserving Healthcare Informatics",
                    "semantic_similarity": 0.90,
                    "lexical_score": 1.4,
                    "topic_similarity": 0.95,
                    "shared_topics": ["Federated Learning", "Privacy", "Healthcare"],
                    "publication_year": 2024,
                },
                {
                    "id": id_5_c2,
                    "title": "Privacy Laws and Regulatory Policy in Digital Media",
                    "semantic_similarity": 0.40,
                    "lexical_score": 0.6,
                    "topic_similarity": 0.30,
                    "shared_topics": ["Privacy"],
                    "publication_year": 2023,
                },
            ],
            expected_top_ids=[id_5_c1],
            graded_relevance={id_5_c1: 3.0, id_5_c2: 1.0},
        )
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Similar Research with Different Publication Years (Freshness Decay)
    # ─────────────────────────────────────────────────────────────────────────
    id_6_src = "66666666-0006-0000-0000-000000000000"
    id_6_c1 = "66666666-0006-0000-0000-000000000001"  # Contemporary (2025)
    id_6_c2 = "66666666-0006-0000-0000-000000000002"  # Older (2014)
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_06_RECENCY_FRESHNESS",
            name="Similar Research with Recency Decay Evaluation",
            category=GroundTruthCategory.SYNTHETIC_FIXTURE,
            description="Two papers with equal semantic/topic match where contemporary paper receives higher rank due to freshness bonus.",
            query_type="SIMILAR_RESEARCH",
            query_payload={"work_id": id_6_src},
            candidate_fixtures=[
                {
                    "id": id_6_c1,
                    "title": "Modern Diffusion Models for Image Synthesis",
                    "semantic_similarity": 0.90,
                    "lexical_score": 1.0,
                    "topic_similarity": 0.85,
                    "publication_year": 2025,
                },
                {
                    "id": id_6_c2,
                    "title": "Foundational Diffusion Probabilistic Models",
                    "semantic_similarity": 0.90,
                    "lexical_score": 1.0,
                    "topic_similarity": 0.85,
                    "publication_year": 2014,
                },
            ],
            expected_top_ids=[id_6_c1],
            graded_relevance={id_6_c1: 3.0, id_6_c2: 2.0},
        )
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 7. Strong Research → Conference Match
    # ─────────────────────────────────────────────────────────────────────────
    id_7_src = "77777777-0007-0000-0000-000000000000"
    id_7_c1 = "77777777-0007-0000-0000-000000000001"
    id_7_c2 = "77777777-0007-0000-0000-000000000002"
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_07_RESEARCH_TO_CONFERENCE",
            name="Strong Research → Conference Opportunity Match",
            category=GroundTruthCategory.HEURISTIC_METADATA,
            description="Paper article matching a flagship conference with compatible publication type and active deadline.",
            query_type="OPPORTUNITY_MATCH",
            query_payload={"work_id": id_7_src, "work_type": "article"},
            candidate_fixtures=[
                {
                    "id": id_7_c1,
                    "title": "International Conference on Machine Learning (ICML 2026)",
                    "opportunity_type": "CONFERENCE",
                    "semantic_similarity": 0.91,
                    "topic_similarity": 0.90,
                    "type_compatibility": 1.00,
                    "urgency": 0.80,
                    "deadline": (now + timedelta(days=25)).isoformat(),
                },
                {
                    "id": id_7_c2,
                    "title": "Workshop on Classical Physics and Metallurgy",
                    "opportunity_type": "WORKSHOP",
                    "semantic_similarity": 0.15,
                    "topic_similarity": 0.05,
                    "type_compatibility": 0.70,
                    "urgency": 0.20,
                    "deadline": (now + timedelta(days=80)).isoformat(),
                },
            ],
            expected_top_ids=[id_7_c1],
            graded_relevance={id_7_c1: 3.0, id_7_c2: 0.0},
        )
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 8. Strong Research → Journal Match
    # ─────────────────────────────────────────────────────────────────────────
    id_8_src = "88888888-0008-0000-0000-000000000000"
    id_8_c1 = "88888888-0008-0000-0000-000000000001"
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_08_RESEARCH_TO_JOURNAL",
            name="Strong Research → Journal Opportunity Match",
            category=GroundTruthCategory.HEURISTIC_METADATA,
            description="Research work matched to premier peer-reviewed Journal CFP.",
            query_type="OPPORTUNITY_MATCH",
            query_payload={"work_id": id_8_src, "work_type": "article"},
            candidate_fixtures=[
                {
                    "id": id_8_c1,
                    "title": "IEEE Transactions on Pattern Analysis and Machine Intelligence (TPAMI)",
                    "opportunity_type": "JOURNAL",
                    "semantic_similarity": 0.93,
                    "topic_similarity": 0.92,
                    "type_compatibility": 1.00,
                    "urgency": 0.50,
                }
            ],
            expected_top_ids=[id_8_c1],
            graded_relevance={id_8_c1: 3.0},
        )
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 9. Weak Opportunity Compatibility (Mismatch in Domain & Type)
    # ─────────────────────────────────────────────────────────────────────────
    id_9_src = "99999999-0009-0000-0000-000000000000"
    id_9_c1 = "99999999-0009-0000-0000-000000000001"
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_09_WEAK_COMPATIBILITY",
            name="Weak Opportunity Compatibility Filter/Rejection",
            category=GroundTruthCategory.SYNTHETIC_FIXTURE,
            description="Opportunity with low semantic match and mismatching discipline.",
            query_type="OPPORTUNITY_MATCH",
            query_payload={"work_id": id_9_src},
            candidate_fixtures=[
                {
                    "id": id_9_c1,
                    "title": "Annual Symposium on Medieval Ceramic Art",
                    "opportunity_type": "CONFERENCE",
                    "semantic_similarity": 0.12,
                    "topic_similarity": 0.0,
                    "type_compatibility": 0.50,
                    "urgency": 0.10,
                }
            ],
            expected_top_ids=[],
            graded_relevance={id_9_c1: 0.0},
        )
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 10. Imminent Opportunity Deadline
    # ─────────────────────────────────────────────────────────────────────────
    id_10_src = "10101010-0010-0000-0000-000000000000"
    id_10_c1 = "10101010-0010-0000-0000-000000000001"
    id_10_c2 = "10101010-0010-0000-0000-000000000002"
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_10_IMMINENT_DEADLINE",
            name="Imminent vs Distant Opportunity Deadline Urgency",
            category=GroundTruthCategory.SYNTHETIC_FIXTURE,
            description="Equal semantic relevance where upcoming deadline within 14 days receives higher urgency boost than deadline in 85 days.",
            query_type="OPPORTUNITY_MATCH",
            query_payload={"work_id": id_10_src},
            candidate_fixtures=[
                {
                    "id": id_10_c1,
                    "title": "Special Issue on Safe AI — Submission Closing Soon",
                    "opportunity_type": "JOURNAL",
                    "semantic_similarity": 0.85,
                    "topic_similarity": 0.80,
                    "type_compatibility": 1.00,
                    "urgency": 0.84,  # ~14 days left
                },
                {
                    "id": id_10_c2,
                    "title": "Special Issue on Safe AI — Long Horizon Call",
                    "opportunity_type": "JOURNAL",
                    "semantic_similarity": 0.85,
                    "topic_similarity": 0.80,
                    "type_compatibility": 1.00,
                    "urgency": 0.05,  # ~85 days left
                },
            ],
            expected_top_ids=[id_10_c1],
            graded_relevance={id_10_c1: 3.0, id_10_c2: 2.0},
        )
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 11. Distant Deadline
    # ─────────────────────────────────────────────────────────────────────────
    id_11_src = "11111111-0011-0000-0000-000000000000"
    id_11_c1 = "11111111-0011-0000-0000-000000000001"
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_11_DISTANT_DEADLINE",
            name="Distant Deadline Evaluation",
            category=GroundTruthCategory.SYNTHETIC_FIXTURE,
            description="Opportunity with deadline > 90 days out receives 0.0 urgency weight without penalty to relevance.",
            query_type="OPPORTUNITY_MATCH",
            query_payload={"work_id": id_11_src},
            candidate_fixtures=[
                {
                    "id": id_11_c1,
                    "title": "Conference on Evolutionary Systems (2027)",
                    "opportunity_type": "CONFERENCE",
                    "semantic_similarity": 0.88,
                    "topic_similarity": 0.80,
                    "type_compatibility": 1.00,
                    "urgency": 0.0,
                }
            ],
            expected_top_ids=[id_11_c1],
            graded_relevance={id_11_c1: 2.5},
        )
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 12. Missing Embedding (Graceful Degradation to Lexical/Topic)
    # ─────────────────────────────────────────────────────────────────────────
    id_12_src = "12121212-0012-0000-0000-000000000000"
    id_12_c1 = "12121212-0012-0000-0000-000000000001"
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_12_MISSING_EMBEDDING",
            name="Missing Vector Embedding Resilience",
            category=GroundTruthCategory.SYNTHETIC_FIXTURE,
            description="Candidate with NULL embedding still ranks appropriately via lexical and topic channels.",
            query_type="SIMILAR_RESEARCH",
            query_payload={"work_id": id_12_src},
            candidate_fixtures=[
                {
                    "id": id_12_c1,
                    "title": "Algorithmic Game Theory Principles",
                    "semantic_similarity": 0.0,
                    "has_embedding": False,
                    "lexical_score": 2.4,
                    "topic_similarity": 0.90,
                    "publication_year": 2023,
                }
            ],
            expected_top_ids=[id_12_c1],
            graded_relevance={id_12_c1: 2.0},
        )
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 13. Missing Topic Metadata
    # ─────────────────────────────────────────────────────────────────────────
    id_13_src = "13131313-0013-0000-0000-000000000000"
    id_13_c1 = "13131313-0013-0000-0000-000000000001"
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_13_MISSING_TOPIC_METADATA",
            name="Missing Topic Metadata Resilience",
            category=GroundTruthCategory.SYNTHETIC_FIXTURE,
            description="Candidate with zero topic tags relies cleanly on semantic and lexical channels.",
            query_type="SIMILAR_RESEARCH",
            query_payload={"work_id": id_13_src},
            candidate_fixtures=[
                {
                    "id": id_13_c1,
                    "title": "Quantum Error Mitigation in Superconducting Qubits",
                    "semantic_similarity": 0.92,
                    "lexical_score": 1.8,
                    "topic_similarity": 0.0,
                    "has_topics": False,
                    "publication_year": 2024,
                }
            ],
            expected_top_ids=[id_13_c1],
            graded_relevance={id_13_c1: 2.5},
        )
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 14. No Relevant Candidates
    # ─────────────────────────────────────────────────────────────────────────
    id_14_c1 = "14141414-0014-0000-0000-000000000001"
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_14_NO_RELEVANT_CANDIDATES",
            name="Zero-Relevance Empty / Near-Empty Results",
            category=GroundTruthCategory.SYNTHETIC_FIXTURE,
            description="Gibberish or completely unrepresented query.",
            query_type="RESEARCH_SEARCH",
            query_payload={"q": "xyzqjk999182 non-existent term"},
            candidate_fixtures=[],
            expected_top_ids=[],
            graded_relevance={},
        )
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 15. Candidate Retrieved by Multiple Channels (Dual-Channel Provenance)
    # ─────────────────────────────────────────────────────────────────────────
    id_15_c1 = "15151515-0015-0000-0000-000000000001"
    id_15_c2 = "15151515-0015-0000-0000-000000000002"
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_15_MULTI_CHANNEL_PROVENANCE",
            name="Multi-Channel Provenance (Dual Vector + Lexical RRF)",
            category=GroundTruthCategory.SYNTHETIC_FIXTURE,
            description="Candidate retrieved independently by both semantic vector and lexical full-text channels outranks single-channel candidates.",
            query_type="RESEARCH_SEARCH",
            query_payload={"q": "reinforcement learning robotics control"},
            candidate_fixtures=[
                {
                    "id": id_15_c1,
                    "title": "Reinforcement Learning for Dexterous Robotic Manipulation",
                    "semantic_similarity": 0.88,
                    "lexical_score": 2.0,
                    "retrieval_sources": ["vector", "lexical"],
                    "publication_year": 2024,
                },
                {
                    "id": id_15_c2,
                    "title": "General Robotics Dynamics and Control Systems",
                    "semantic_similarity": 0.65,
                    "lexical_score": 0.0,
                    "retrieval_sources": ["vector"],
                    "publication_year": 2024,
                },
            ],
            expected_top_ids=[id_15_c1],
            graded_relevance={id_15_c1: 3.0, id_15_c2: 1.0},
        )
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 16. Tied Candidate Scores (Deterministic Tie-Breaking)
    # ─────────────────────────────────────────────────────────────────────────
    id_16_c1 = "16161616-0016-0000-0000-000000000001"
    id_16_c2 = "16161616-0016-0000-0000-000000000002"
    scenarios.append(
        BenchmarkQueryScenario(
            scenario_id="SCENARIO_16_TIED_SCORES_DETERMINISM",
            name="Tied Score Deterministic Ordering",
            category=GroundTruthCategory.SYNTHETIC_FIXTURE,
            description="Candidates with identical score tied across all signals break ties deterministically by entity UUID string.",
            query_type="RESEARCH_SEARCH",
            query_payload={"q": "information theory basics"},
            candidate_fixtures=[
                {
                    "id": id_16_c2,  # lexicographically greater
                    "title": "Information Theory Volume B",
                    "semantic_similarity": 0.80,
                    "lexical_score": 1.0,
                    "publication_year": 2020,
                },
                {
                    "id": id_16_c1,  # lexicographically smaller
                    "title": "Information Theory Volume A",
                    "semantic_similarity": 0.80,
                    "lexical_score": 1.0,
                    "publication_year": 2020,
                },
            ],
            expected_top_ids=[id_16_c1, id_16_c2],
            graded_relevance={id_16_c1: 2.0, id_16_c2: 2.0},
        )
    )

    return scenarios
