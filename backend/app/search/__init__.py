"""
Search and Candidate Fusion package for ResearchConnect AI.

Exports multi-channel search utilities and fusion algorithms.
"""
from app.search.rrf import (
    DEFAULT_RRF_K,
    FusedCandidate,
    RankedCandidate,
    fuse_ranked_candidates,
)

__all__ = [
    "DEFAULT_RRF_K",
    "FusedCandidate",
    "RankedCandidate",
    "fuse_ranked_candidates",
]
