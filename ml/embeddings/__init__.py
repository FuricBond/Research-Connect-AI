"""
ml.embeddings — Phase 2.3B Semantic Embedding package.

Public API
----------
EmbeddingService      — model loading + batch encoding
build_research_work_text — semantic text for ResearchWorkModel
build_opportunity_text   — semantic text for OpportunityModel
compute_content_hash     — SHA-256 hash of semantic text
needs_reembedding        — decide whether a record should be (re-)embedded
"""
from ml.embeddings.service import EmbeddingService
from ml.embeddings.text_builder import build_opportunity_text, build_research_work_text
from ml.embeddings.hash_utils import compute_content_hash, needs_reembedding

__all__ = [
    "EmbeddingService",
    "build_research_work_text",
    "build_opportunity_text",
    "compute_content_hash",
    "needs_reembedding",
]
