"""
Repositories layer for ResearchConnect AI.

Exports database-level retrieval mechanisms independent of HTTP/API concerns.
"""
from app.repositories.vector_repository import (
    DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_EMBEDDING_DIM,
    MAX_CANDIDATE_LIMIT,
    VectorRepository,
    VectorSearchResult,
    VectorValidationError,
    distance_to_similarity,
    sanitize_candidate_limit,
    validate_query_vector,
    vector_repository,
)

__all__ = [
    "VectorRepository",
    "VectorSearchResult",
    "VectorValidationError",
    "validate_query_vector",
    "sanitize_candidate_limit",
    "distance_to_similarity",
    "DEFAULT_CANDIDATE_LIMIT",
    "MAX_CANDIDATE_LIMIT",
    "DEFAULT_EMBEDDING_DIM",
    "vector_repository",
]
