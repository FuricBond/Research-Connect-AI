"""
Reciprocal Rank Fusion (RRF) utility for Phase 2.4B.

Implements rank-based fusion across multiple candidate retrieval systems:
  - Lexical full-text search
  - pgvector semantic vector search
  - Future candidate signals

Formula
-------
For candidate d across retrieval systems {1, 2, ..., M}:

    RRF_score(d) = Σ 1 / (k + rank_i(d))

where:
  - rank_i(d) is the 1-based rank position of candidate d in system i.
  - k is the RRF smoothing constant (default: 60).

Key Design Properties
---------------------
1. Rank-based: Does not depend on arbitrary scale differences between lexical scores
   (e.g. ts_rank) and vector cosine similarities ([0, 1]).
2. Generic: Supports arbitrary entity types and $N$ retrieval systems.
3. Segregated: Candidate identity is keyed on `(entity_type, entity_id)` to prevent
   collisions between research works and opportunities.
4. Deterministic: Deterministic tie-breaking ensures reproducible candidate lists.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence
import uuid

logger = logging.getLogger(__name__)

DEFAULT_RRF_K: int = 60


# ── Protocol for Ranked Candidate Inputs ──────────────────────────────────────


class RankedCandidate(Protocol):
    """Protocol for any candidate result object passed into RRF fusion."""

    entity_id: uuid.UUID
    entity_type: str
    rank: int


# ── Fused Result Container ───────────────────────────────────────────────────


@dataclass(frozen=True)
class FusedCandidate:
    """
    Lightweight, immutable result of Reciprocal Rank Fusion.

    Attributes
    ----------
    entity_id:
        Primary key UUID of the candidate entity.
    entity_type:
        Type of entity (e.g. "research_work", "opportunity").
    rrf_score:
        Fused reciprocal rank score (higher is better).
    ranks:
        Mapping of source system name to 1-based rank position (e.g. {"lexical": 1, "vector": 3}).
    scores:
        Mapping of source system name to raw system score (e.g. {"lexical": 0.42, "vector": 0.89}).
    retrieval_sources:
        Sorted list of retrieval systems that found this candidate.
    entity:
        Optional attached ORM model or metadata object.
    """

    entity_id: uuid.UUID
    entity_type: str
    rrf_score: float
    ranks: dict[str, int] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    retrieval_sources: list[str] = field(default_factory=list)
    entity: Any | None = None


# ── Generic Fusion Function ───────────────────────────────────────────────────


def fuse_ranked_candidates(
    ranked_lists: Mapping[str, Sequence[Any]],
    *,
    k: int = DEFAULT_RRF_K,
    limit: int | None = None,
) -> list[FusedCandidate]:
    """
    Fuse multiple ranked candidate result lists using Reciprocal Rank Fusion.

    Parameters
    ----------
    ranked_lists:
        Mapping of system name (e.g. "lexical", "vector") to a sequence of candidate
        result objects. Each object must have `entity_id` and `entity_type`.
        If an object has a `rank` attribute, it is used; otherwise its 1-based index
        in the sequence is treated as its rank.
    k:
        RRF smoothing constant (default: 60). Must be positive.
    limit:
        Optional maximum number of fused candidates to return.

    Returns
    -------
    list[FusedCandidate]
        Deduplicated fused candidates ordered by `rrf_score` descending.

    Raises
    ------
    ValueError:
        If k <= 0.
    """
    if k <= 0:
        raise ValueError(f"RRF constant k must be positive, got {k}.")

    # Key: (entity_type, entity_id) -> metadata dictionary
    candidates_map: dict[tuple[str, uuid.UUID], dict[str, Any]] = {}

    for system_name, items in ranked_lists.items():
        for idx, item in enumerate(items, start=1):
            entity_id: uuid.UUID = getattr(item, "entity_id")
            entity_type: str = getattr(item, "entity_type")
            rank: int = getattr(item, "rank", idx)
            entity_obj: Any | None = getattr(item, "entity", None)

            key = (entity_type, entity_id)
            if key not in candidates_map:
                candidates_map[key] = {
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "rrf_score": 0.0,
                    "ranks": {},
                    "scores": {},
                    "entity": entity_obj,
                }

            # If entity object was not attached previously, attach it if available
            if candidates_map[key]["entity"] is None and entity_obj is not None:
                candidates_map[key]["entity"] = entity_obj

            # Compute reciprocal rank component
            reciprocal_rank = 1.0 / (k + rank)
            candidates_map[key]["rrf_score"] += reciprocal_rank
            candidates_map[key]["ranks"][system_name] = rank

            # Extract raw score if available (e.g. lexical_score, similarity, score)
            raw_score: float | None = None
            if getattr(item, "lexical_score", None) is not None:
                raw_score = float(getattr(item, "lexical_score"))
            elif getattr(item, "similarity", None) is not None:
                raw_score = float(getattr(item, "similarity"))
            elif getattr(item, "score", None) is not None:
                raw_score = float(getattr(item, "score"))

            if raw_score is not None:
                candidates_map[key]["scores"][system_name] = raw_score

    # Construct FusedCandidate list
    fused: list[FusedCandidate] = []
    for (entity_type, entity_id), data in candidates_map.items():
        sources = sorted(list(data["ranks"].keys()))
        fused.append(
            FusedCandidate(
                entity_id=entity_id,
                entity_type=entity_type,
                rrf_score=round(data["rrf_score"], 8),
                ranks=data["ranks"],
                scores=data["scores"],
                retrieval_sources=sources,
                entity=data["entity"],
            )
        )

    # Deterministic sort: descending by rrf_score, tie-break by str(entity_id)
    fused.sort(key=lambda c: (-c.rrf_score, str(c.entity_id)))

    if limit is not None and limit > 0:
        fused = fused[:limit]

    return fused
