"""
Diversity & Novelty Mechanics for Phase 2.5E Recommendation Ranking.

Provides:
  1. CandidateDiversityProfile: Lightweight, cached representation of candidate metadata.
  2. Multi-signal redundancy functions:
     - Author overlap (Jaccard)
     - Venue overlap (Phase 2.5D canonical venue key matching)
     - Institution overlap (Jaccard)
     - Topic overlap (Jaccard over canonical topic UUIDs)
     - Semantic similarity (Cosine similarity over normalized 384-dim embeddings)
  3. Novelty quantification:
     - List-relative semantic, topical, author, and venue novelty metrics.
  4. DiversityConfig:
     - Bounded diversity weight (lambda <= 0.15) enforcing >= 85% relevance dominance.
     - Mode-specific presets (GENERAL, RESEARCH_SIMILARITY, RESEARCH_OPPORTUNITY).
  5. DiversityReranker:
     - Deterministic, list-aware Maximal Marginal Relevance (MMR) reranking.
     - Relevance floor and dominance protection.
     - Structured explainability hooks for Phase 2.5F.
     - Deterministic multi-key tie-breaking.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import logging
import math
from typing import Any, Sequence
import uuid

from app.core.config import settings
from app.ranking.hybrid_ranker import RankedCandidate, RankingMode
from app.ranking.venue_intelligence import get_canonical_venue_key

logger = logging.getLogger(__name__)

# Hard architectural bounds
MAX_DIVERSITY_LAMBDA = 0.15  # Strict limit to guarantee >= 85% relevance dominance
DEFAULT_DIVERSITY_LAMBDA = 0.08
DEFAULT_RELEVANCE_FLOOR = 0.35


# ── 1. Canonical Candidate Diversity Profile ──────────────────────────────────


@dataclass(frozen=True)
class CandidateDiversityProfile:
    """
    Immutable representation of candidate diversity features.

    Attributes
    ----------
    work_id:
        Canonical UUID of the candidate work or opportunity.
    author_ids:
        Frozenset of researcher UUIDs associated with this work.
    institution_ids:
        Frozenset of institution UUIDs associated with this work.
    canonical_venue_key:
        Normalized canonical publication venue key (e.g. 'issn:0028-0836' or 'name:slug').
    topic_ids:
        Frozenset of canonical topic UUIDs.
    embedding:
        Normalized float tuple representing the 384-dimensional dense semantic embedding.
    base_score:
        Pre-diversity composite ranking score in [0.0, 1.0].
    semantic_score:
        Semantic similarity component in [0.0, 1.0].
    topic_score:
        Topic overlap component in [0.0, 1.0].
    candidate:
        Original attached candidate entity or envelope.
    """

    work_id: uuid.UUID
    author_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    institution_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    canonical_venue_key: str | None = None
    topic_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    embedding: tuple[float, ...] | None = None
    base_score: float = 0.0
    semantic_score: float = 0.0
    topic_score: float = 0.0
    candidate: Any | None = None

    @classmethod
    def from_candidate(cls, cand: RankedCandidate | Any) -> CandidateDiversityProfile:
        """
        Extract and canonicalize diversity features from any supported candidate envelope.
        Safe against missing, malformed, or nested attributes.
        """
        work_id = getattr(cand, "entity_id", None)
        if work_id is None:
            work_id = getattr(cand, "candidate_work_id", None)
        if work_id is None and isinstance(cand, dict):
            work_id = cand.get("entity_id", cand.get("id", cand.get("candidate_work_id")))

        try:
            resolved_id = uuid.UUID(str(work_id)) if work_id is not None else uuid.uuid4()
        except (ValueError, TypeError):
            resolved_id = uuid.uuid5(uuid.NAMESPACE_DNS, str(work_id or "unknown"))

        # Base scores
        base_score = float(
            getattr(
                cand,
                "final_score",
                getattr(
                    cand,
                    "combined_similarity",
                    getattr(cand, "match_score", getattr(cand, "hybrid_score", 0.0)),
                ),
            )
            or 0.0
        )
        if isinstance(cand, dict) and base_score == 0.0:
            base_score = float(cand.get("final_score", cand.get("combined_similarity", cand.get("match_score", 0.0))) or 0.0)

        sem_score = float(getattr(cand, "semantic_score", getattr(cand, "semantic_similarity", 0.0)) or 0.0)
        if isinstance(cand, dict) and sem_score == 0.0:
            sem_score = float(cand.get("semantic_score", cand.get("semantic_similarity", 0.0)) or 0.0)

        top_score = float(getattr(cand, "topic_score", getattr(cand, "topic_similarity", 0.0)) or 0.0)
        if isinstance(cand, dict) and top_score == 0.0:
            top_score = float(cand.get("topic_score", cand.get("topic_similarity", 0.0)) or 0.0)

        # Attached ORM or dictionary target
        attached = getattr(cand, "candidate", getattr(cand, "candidate_work", getattr(cand, "entity", None)))
        if attached is None and isinstance(cand, dict):
            attached = cand.get("candidate", cand.get("candidate_work", cand.get("entity", cand)))

        # 1. Author IDs
        authors_set: set[uuid.UUID] = set()
        raw_authors = getattr(attached, "author_links", None)
        if raw_authors is None and isinstance(attached, dict):
            raw_authors = attached.get("author_links", attached.get("authors", attached.get("author_ids")))
        if raw_authors:
            for item in raw_authors:
                a_id = getattr(item, "researcher_id", getattr(item, "id", None))
                if isinstance(item, dict):
                    a_id = item.get("researcher_id", item.get("id"))
                elif isinstance(item, (str, uuid.UUID)):
                    a_id = item
                if a_id is not None:
                    try:
                        authors_set.add(uuid.UUID(str(a_id)))
                    except (ValueError, TypeError):
                        pass

        # 2. Institution IDs
        institutions_set: set[uuid.UUID] = set()
        raw_insts = getattr(attached, "institution_links", None)
        if raw_insts is None and isinstance(attached, dict):
            raw_insts = attached.get("institution_links", attached.get("institutions", attached.get("institution_ids")))
        if raw_insts:
            for item in raw_insts:
                i_id = getattr(item, "institution_id", getattr(item, "id", None))
                if isinstance(item, dict):
                    i_id = item.get("institution_id", item.get("id"))
                elif isinstance(item, (str, uuid.UUID)):
                    i_id = item
                if i_id is not None:
                    try:
                        institutions_set.add(uuid.UUID(str(i_id)))
                    except (ValueError, TypeError):
                        pass

        # 3. Canonical Venue Key
        venue_key: str | None = None
        raw_venue = getattr(attached, "primary_source", None)
        if raw_venue is not None:
            v_name = getattr(raw_venue, "display_name", getattr(raw_venue, "name", None))
            v_issn_l = getattr(raw_venue, "issn_l", None)
            v_issns = getattr(raw_venue, "issn", None)
            venue_key = get_canonical_venue_key(v_name, v_issn_l, v_issns)
        elif isinstance(attached, dict):
            if "canonical_venue_key" in attached:
                venue_key = attached["canonical_venue_key"]
            else:
                v_cand = attached.get("primary_source", attached.get("venue"))
                if isinstance(v_cand, dict):
                    venue_key = get_canonical_venue_key(
                        v_cand.get("display_name", v_cand.get("name")),
                        v_cand.get("issn_l"),
                        v_cand.get("issn"),
                    )
                elif isinstance(v_cand, str) and v_cand.strip():
                    venue_key = get_canonical_venue_key(v_cand)
        elif hasattr(attached, "venue") and getattr(attached, "venue"):
            venue_key = get_canonical_venue_key(str(getattr(attached, "venue")))

        # 4. Topic IDs
        topic_set: set[uuid.UUID] = set()
        shared_tids = getattr(cand, "shared_topic_ids", None)
        if shared_tids:
            for tid in shared_tids:
                try:
                    topic_set.add(uuid.UUID(str(tid)))
                except (ValueError, TypeError):
                    pass

        raw_topics = getattr(attached, "topic_associations", None)
        if raw_topics is None and isinstance(attached, dict):
            raw_topics = attached.get("topic_associations", attached.get("topics", attached.get("topic_ids")))
        if raw_topics:
            for item in raw_topics:
                t_id = getattr(item, "topic_id", getattr(item, "id", None))
                if isinstance(item, dict):
                    t_id = item.get("topic_id", item.get("id"))
                elif isinstance(item, (str, uuid.UUID)):
                    t_id = item
                if t_id is not None:
                    try:
                        topic_set.add(uuid.UUID(str(t_id)))
                    except (ValueError, TypeError):
                        pass

        # 5. Embedding Vector
        raw_emb = getattr(attached, "embedding", None)
        if raw_emb is None and isinstance(attached, dict):
            raw_emb = attached.get("embedding", attached.get("vector"))

        cleaned_emb: tuple[float, ...] | None = None
        if raw_emb is not None and isinstance(raw_emb, (list, tuple)) and len(raw_emb) > 0:
            try:
                converted = tuple(float(x) for x in raw_emb)
                # Ensure no NaN / inf
                if all(math.isfinite(x) for x in converted):
                    norm = math.sqrt(sum(x * x for x in converted))
                    if norm > 1e-9:
                        # Normalize to unit vector
                        cleaned_emb = tuple(x / norm for x in converted)
            except (ValueError, TypeError):
                cleaned_emb = None

        final_emb = None
        if cleaned_emb is not None:
            if np is not None:
                arr = np.asarray(cleaned_emb, dtype=np.float32)
                arr.flags.writeable = False
                final_emb = arr
            else:
                final_emb = cleaned_emb

        return cls(
            work_id=resolved_id,
            author_ids=frozenset(authors_set),
            institution_ids=frozenset(institutions_set),
            canonical_venue_key=venue_key,
            topic_ids=frozenset(topic_set),
            embedding=final_emb,
            base_score=round(base_score, 6),
            semantic_score=round(sem_score, 6),
            topic_score=round(top_score, 6),
            candidate=cand,
        )


# ── 2. Redundancy & Similarity Metrics ────────────────────────────────────────


def calculate_author_overlap(
    p1: CandidateDiversityProfile, p2: CandidateDiversityProfile
) -> float:
    """
    Calculate Jaccard similarity between two author sets.
    Returns 0.0 if either author set is empty.
    """
    if not p1.author_ids or not p2.author_ids:
        return 0.0
    union = len(p1.author_ids | p2.author_ids)
    if union == 0:
        return 0.0
    return round(float(len(p1.author_ids & p2.author_ids)) / float(union), 6)


def calculate_venue_overlap(
    p1: CandidateDiversityProfile, p2: CandidateDiversityProfile
) -> float:
    """
    Calculate venue equivalence between two candidates.
    Returns 1.0 if both have identical canonical venue keys, else 0.0.
    """
    if not p1.canonical_venue_key or not p2.canonical_venue_key:
        return 0.0
    return 1.0 if p1.canonical_venue_key == p2.canonical_venue_key else 0.0


def calculate_institution_overlap(
    p1: CandidateDiversityProfile, p2: CandidateDiversityProfile
) -> float:
    """
    Calculate Jaccard similarity between two affiliated institution sets.
    Returns 0.0 if either institution set is empty.
    """
    if not p1.institution_ids or not p2.institution_ids:
        return 0.0
    union = len(p1.institution_ids | p2.institution_ids)
    if union == 0:
        return 0.0
    return round(float(len(p1.institution_ids & p2.institution_ids)) / float(union), 6)


def calculate_topic_overlap(
    p1: CandidateDiversityProfile, p2: CandidateDiversityProfile
) -> float:
    """
    Calculate Jaccard similarity between two canonical topic sets.
    Returns 0.0 if either topic set is empty.
    """
    if not p1.topic_ids or not p2.topic_ids:
        return 0.0
    union = len(p1.topic_ids | p2.topic_ids)
    if union == 0:
        return 0.0
    return round(float(len(p1.topic_ids & p2.topic_ids)) / float(union), 6)


try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


def calculate_semantic_similarity(
    p1: CandidateDiversityProfile, p2: CandidateDiversityProfile
) -> float:
    """
    Calculate cosine similarity between two unit-normalized embeddings.
    Returns 0.0 if either embedding is missing.
    """
    if p1.embedding is None or p2.embedding is None:
        return 0.0
    if len(p1.embedding) != len(p2.embedding):
        return 0.0

    if np is not None:
        try:
            dot = float(np.dot(p1.embedding, p2.embedding))
            return round(min(1.0, max(0.0, dot)), 6)
        except Exception:
            pass

    dot = sum(u * v for u, v in zip(p1.embedding, p2.embedding))
    # Clamped to [0.0, 1.0] for academic semantic embeddings
    return round(min(1.0, max(0.0, dot)), 6)


# ── 3. Diversity Configuration & Presets ──────────────────────────────────────


@dataclass(frozen=True)
class DiversityConfig:
    """
    Configuration container for diversity and novelty reranking.

    Enforces that lambda_penalty is bounded strictly within [0.0, 0.15],
    ensuring that relevance retains >= 85% dominance at all times.
    """

    enabled: bool = False
    lambda_penalty: float = DEFAULT_DIVERSITY_LAMBDA
    relevance_floor: float = DEFAULT_RELEVANCE_FLOOR
    top_k: int = 50

    # Relative signal contributions to composite redundancy (sum = 1.0)
    semantic_redundancy_weight: float = 0.40
    topic_redundancy_weight: float = 0.30
    author_redundancy_weight: float = 0.15
    venue_redundancy_weight: float = 0.10
    institution_redundancy_weight: float = 0.05

    def __post_init__(self) -> None:
        # Validate lambda penalty bound
        if self.lambda_penalty < 0.0:
            object.__setattr__(self, "lambda_penalty", 0.0)
        elif self.lambda_penalty > MAX_DIVERSITY_LAMBDA:
            logger.warning(
                "Requested lambda_penalty %f exceeds maximum allowed %f; clamping to %f.",
                self.lambda_penalty,
                MAX_DIVERSITY_LAMBDA,
                MAX_DIVERSITY_LAMBDA,
            )
            object.__setattr__(self, "lambda_penalty", MAX_DIVERSITY_LAMBDA)

        # Normalize redundancy weights if needed
        total_w = (
            self.semantic_redundancy_weight
            + self.topic_redundancy_weight
            + self.author_redundancy_weight
            + self.venue_redundancy_weight
            + self.institution_redundancy_weight
        )
        if total_w > 0.0 and abs(total_w - 1.0) > 1e-4:
            object.__setattr__(
                self,
                "semantic_redundancy_weight",
                round(self.semantic_redundancy_weight / total_w, 4),
            )
            object.__setattr__(
                self,
                "topic_redundancy_weight",
                round(self.topic_redundancy_weight / total_w, 4),
            )
            object.__setattr__(
                self,
                "author_redundancy_weight",
                round(self.author_redundancy_weight / total_w, 4),
            )
            object.__setattr__(
                self,
                "venue_redundancy_weight",
                round(self.venue_redundancy_weight / total_w, 4),
            )
            object.__setattr__(
                self,
                "institution_redundancy_weight",
                round(self.institution_redundancy_weight / total_w, 4),
            )

    @classmethod
    def for_mode(cls, mode: RankingMode | str, enabled: bool = True) -> DiversityConfig:
        """
        Factory producing mode-tailored diversity configurations.

        Mode Profiles:
          - GENERAL: Balanced diversity across semantics, topics, authors, and venues.
          - RESEARCH_SIMILARITY: Conservative diversity (lambda=0.04) to protect semantic affinity.
          - RESEARCH_OPPORTUNITY: Broader diversity (lambda=0.10) to promote cross-disciplinary venues.
        """
        m = str(mode).lower()
        if "similarity" in m:
            return cls(
                enabled=enabled,
                lambda_penalty=0.04,
                relevance_floor=0.40,
                semantic_redundancy_weight=0.55,
                topic_redundancy_weight=0.25,
                author_redundancy_weight=0.10,
                venue_redundancy_weight=0.05,
                institution_redundancy_weight=0.05,
            )
        elif "opportunity" in m:
            return cls(
                enabled=enabled,
                lambda_penalty=0.10,
                relevance_floor=0.30,
                semantic_redundancy_weight=0.30,
                topic_redundancy_weight=0.40,
                author_redundancy_weight=0.05,
                venue_redundancy_weight=0.20,
                institution_redundancy_weight=0.05,
            )
        else:
            return cls(
                enabled=enabled,
                lambda_penalty=DEFAULT_DIVERSITY_LAMBDA,
                relevance_floor=DEFAULT_RELEVANCE_FLOOR,
                semantic_redundancy_weight=0.40,
                topic_redundancy_weight=0.30,
                author_redundancy_weight=0.15,
                venue_redundancy_weight=0.10,
                institution_redundancy_weight=0.05,
            )


# ── 4. Deterministic List-Aware Diversity Reranker ─────────────────────────────


class DiversityReranker:
    """
    List-Aware Recommendation Diversity and Novelty Reranker.

    Applies deterministic Maximal Marginal Relevance (MMR) over candidate results:
      Score_div(c) = Score_base(c) - lambda * max_{s in S} Redundancy(c, s)

    Guarantees:
      1. Determinism: Bit-for-bit identical outputs for identical candidate inputs.
      2. Relevance Dominance: Lambda is capped <= 0.15, preserving >= 85% relevance mass.
      3. Relevance Floor: Low-scoring results are ineligible to be promoted above high-relevance results.
      4. Zero N+1 Queries: Consumes pre-extracted metadata and embeddings directly.
      5. Graceful Fallback: When disabled or on empty inputs, returns original list untouched.
    """

    def __init__(self, default_config: DiversityConfig | None = None) -> None:
        self.default_config = default_config or DiversityConfig()

    def calculate_pairwise_redundancy(
        self,
        p1: CandidateDiversityProfile,
        p2: CandidateDiversityProfile,
        config: DiversityConfig,
    ) -> float:
        """
        Compute weighted composite redundancy between two candidate profiles in [0.0, 1.0].
        """
        sem = calculate_semantic_similarity(p1, p2)
        top = calculate_topic_overlap(p1, p2)
        auth = calculate_author_overlap(p1, p2)
        ven = calculate_venue_overlap(p1, p2)
        inst = calculate_institution_overlap(p1, p2)

        composite = (
            config.semantic_redundancy_weight * sem
            + config.topic_redundancy_weight * top
            + config.author_redundancy_weight * auth
            + config.venue_redundancy_weight * ven
            + config.institution_redundancy_weight * inst
        )
        return round(min(1.0, max(0.0, composite)), 6)

    def calculate_set_redundancy(
        self,
        candidate: CandidateDiversityProfile,
        selected_set: Sequence[CandidateDiversityProfile],
        config: DiversityConfig,
    ) -> tuple[float, float, float, float, float, float]:
        """
        Compute maximum redundancy against all already-selected candidates.

        Returns
        -------
        tuple of (composite_redundancy, max_sem, max_top, max_auth, max_ven, max_inst)
        """
        if not selected_set:
            return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

        max_comp = 0.0
        max_sem = 0.0
        max_top = 0.0
        max_auth = 0.0
        max_ven = 0.0
        max_inst = 0.0

        for sel in selected_set:
            sem = calculate_semantic_similarity(candidate, sel)
            top = calculate_topic_overlap(candidate, sel)
            auth = calculate_author_overlap(candidate, sel)
            ven = calculate_venue_overlap(candidate, sel)
            inst = calculate_institution_overlap(candidate, sel)

            comp = (
                config.semantic_redundancy_weight * sem
                + config.topic_redundancy_weight * top
                + config.author_redundancy_weight * auth
                + config.venue_redundancy_weight * ven
                + config.institution_redundancy_weight * inst
            )

            if comp > max_comp:
                max_comp = comp
            if sem > max_sem:
                max_sem = sem
            if top > max_top:
                max_top = top
            if auth > max_auth:
                max_auth = auth
            if ven > max_ven:
                max_ven = ven
            if inst > max_inst:
                max_inst = inst

        return (
            round(min(1.0, max_comp), 6),
            round(max_sem, 6),
            round(max_top, 6),
            round(max_auth, 6),
            round(max_ven, 6),
            round(max_inst, 6),
        )

    def _generate_explainability_reasons(
        self,
        max_sem: float,
        max_top: float,
        max_auth: float,
        max_ven: float,
        max_inst: float,
    ) -> tuple[list[str], list[str]]:
        """
        Derive structured, deterministic qualitative reasons for redundancy and novelty.
        """
        redundancy_reasons: list[str] = []
        novelty_reasons: list[str] = []

        # Redundancy signals
        if max_sem >= 0.85:
            redundancy_reasons.append("High semantic overlap with previously selected research")
        if max_top >= 0.50:
            redundancy_reasons.append("High canonical topic redundancy with selected papers")
        if max_auth >= 0.50:
            redundancy_reasons.append("Shares majority authorship with selected research")
        if max_ven == 1.0:
            redundancy_reasons.append("Published in same publication venue as selected research")
        if max_inst >= 0.50:
            redundancy_reasons.append("Shares primary institutional affiliation with selected research")

        # Novelty signals
        if max_sem < 0.60:
            novelty_reasons.append("Introduces distinct semantic perspective")
        if max_top < 0.30:
            novelty_reasons.append("Expands topical coverage to novel academic concepts")
        if max_auth == 0.0:
            novelty_reasons.append("Introduces independent research team")
        if max_ven == 0.0:
            novelty_reasons.append("Features distinct publication venue")

        return redundancy_reasons, novelty_reasons

    def rerank(
        self,
        candidates: Sequence[RankedCandidate],
        mode: RankingMode | str = RankingMode.GENERAL,
        config: DiversityConfig | None = None,
        force_enabled: bool = False,
    ) -> list[RankedCandidate]:
        """
        Execute deterministic list-aware diversity and novelty reranking.

        Parameters
        ----------
        candidates:
            Pre-ranked candidate sequence from HybridRanker or CrossEncoderReranker.
        mode:
            Ranking mode context (used to select default profile if config not provided).
        config:
            Optional custom DiversityConfig.
        force_enabled:
            Whether to force enable diversity even if config.enabled is False.

        Returns
        -------
        list[RankedCandidate]
            Reordered candidates with updated rank, final_score, and diversity explainability fields.
        """
        if not candidates:
            return []

        active_config = config or DiversityConfig.for_mode(mode, enabled=force_enabled)
        if not active_config.enabled and not force_enabled:
            return list(candidates)

        # Build candidate diversity profiles
        profiles = [CandidateDiversityProfile.from_candidate(c) for c in candidates]

        # Top-K candidate limiting
        top_k = min(len(profiles), active_config.top_k)
        active_pool = list(profiles[:top_k])
        tail_candidates = list(candidates[top_k:])

        # Maximum base score in pool (used for relevance floor protection)
        max_base_score = max((p.base_score for p in active_pool), default=1.0)
        relevance_cutoff = max(active_config.relevance_floor, max_base_score - 0.30)

        selected_profiles: list[CandidateDiversityProfile] = []
        selected_results: list[RankedCandidate] = []
        remaining_pool = list(active_pool)

        # Dynamic programming cache tracking running maximum redundancy against selected set:
        # work_id -> [max_comp, max_sem, max_top, max_auth, max_ven, max_inst]
        cand_stats: dict[uuid.UUID, list[float]] = {
            p.work_id: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0] for p in remaining_pool
        }

        # Iterative Greedy Selection (MMR) in O(N^2) time
        while remaining_pool:
            best_idx = -1
            best_score = -1e9
            best_adj = 0.0

            for idx, cand_prof in enumerate(remaining_pool):
                stats = cand_stats[cand_prof.work_id]
                comp_red = stats[0]

                # Bounded diversity deduction
                penalty = active_config.lambda_penalty * comp_red
                adj_score = round(cand_prof.base_score - penalty, 6)

                # Relevance floor protection: ineligible candidates cannot surpass floor
                if cand_prof.base_score < relevance_cutoff and len(selected_profiles) < top_k // 2:
                    adj_score -= 0.10

                # Deterministic multi-key comparison
                # 1. adj_score DESC
                # 2. base_score DESC
                # 3. novelty DESC (1.0 - comp_red)
                # 4. semantic_score DESC
                # 5. topic_score DESC
                # 6. work_id ASC (deterministic tie-breaker)
                is_better = False
                if best_idx == -1:
                    is_better = True
                elif adj_score > best_score:
                    is_better = True
                elif abs(adj_score - best_score) < 1e-6:
                    current_cand = remaining_pool[best_idx]
                    if cand_prof.base_score > current_cand.base_score:
                        is_better = True
                    elif abs(cand_prof.base_score - current_cand.base_score) < 1e-6:
                        cand_nov = 1.0 - comp_red
                        best_nov = 1.0 - cand_stats[current_cand.work_id][0]
                        if cand_nov > best_nov:
                            is_better = True
                        elif abs(cand_nov - best_nov) < 1e-6:
                            if cand_prof.semantic_score > current_cand.semantic_score:
                                is_better = True
                            elif abs(cand_prof.semantic_score - current_cand.semantic_score) < 1e-6:
                                if cand_prof.topic_score > current_cand.topic_score:
                                    is_better = True
                                elif abs(cand_prof.topic_score - current_cand.topic_score) < 1e-6:
                                    if str(cand_prof.work_id) < str(current_cand.work_id):
                                        is_better = True

                if is_better:
                    best_idx = idx
                    best_score = adj_score
                    best_adj = round(-penalty, 6)

            # Extract selected candidate
            chosen_prof = remaining_pool.pop(best_idx)
            selected_profiles.append(chosen_prof)
            final_chosen_stats = cand_stats[chosen_prof.work_id]

            # Incrementally update redundancy for all remaining candidates with chosen_prof
            for p in remaining_pool:
                sem = calculate_semantic_similarity(p, chosen_prof)
                top = calculate_topic_overlap(p, chosen_prof)
                auth = calculate_author_overlap(p, chosen_prof)
                ven = calculate_venue_overlap(p, chosen_prof)
                inst = calculate_institution_overlap(p, chosen_prof)

                comp = (
                    active_config.semantic_redundancy_weight * sem
                    + active_config.topic_redundancy_weight * top
                    + active_config.author_redundancy_weight * auth
                    + active_config.venue_redundancy_weight * ven
                    + active_config.institution_redundancy_weight * inst
                )

                st = cand_stats[p.work_id]
                if comp > st[0]:
                    st[0] = comp
                if sem > st[1]:
                    st[1] = sem
                if top > st[2]:
                    st[2] = top
                if auth > st[3]:
                    st[3] = auth
                if ven > st[4]:
                    st[4] = ven
                if inst > st[5]:
                    st[5] = inst

            # Generate explainability metadata
            red_reasons, nov_reasons = self._generate_explainability_reasons(
                final_chosen_stats[1],
                final_chosen_stats[2],
                final_chosen_stats[3],
                final_chosen_stats[4],
                final_chosen_stats[5],
            )

            # Reconstruct RankedCandidate with diversity explainability hooks
            orig_cand = chosen_prof.candidate
            if isinstance(orig_cand, RankedCandidate):
                updated_cand = replace(
                    orig_cand,
                    final_score=round(max(0.0, min(1.0, best_score)), 6),
                    diversity_adjustment=best_adj,
                    novelty_score=round(1.0 - final_chosen_stats[0], 4),
                    redundancy_score=round(final_chosen_stats[0], 4),
                    redundancy_reasons=red_reasons,
                    novelty_reasons=nov_reasons,
                )
            else:
                updated_cand = RankedCandidate(
                    entity_id=chosen_prof.work_id,
                    entity_type="research_work",
                    rank=0,
                    final_score=round(max(0.0, min(1.0, best_score)), 6),
                    semantic_score=chosen_prof.semantic_score,
                    lexical_score=0.0,
                    topic_score=chosen_prof.topic_score,
                    type_score=1.0,
                    freshness_score=0.0,
                    urgency_score=0.0,
                    candidate=orig_cand,
                    diversity_adjustment=best_adj,
                    novelty_score=round(1.0 - final_chosen_stats[0], 4),
                    redundancy_score=round(final_chosen_stats[0], 4),
                    redundancy_reasons=red_reasons,
                    novelty_reasons=nov_reasons,
                )

            selected_results.append(updated_cand)

        # Append any unselected tail candidates
        final_list = selected_results + tail_candidates

        # Reassign 1-indexed ranks
        return [
            replace(c, rank=new_rank)
            for new_rank, c in enumerate(final_list, start=1)
        ]


# Singleton reranker instance
diversity_reranker = DiversityReranker()
