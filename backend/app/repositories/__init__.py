"""
Repositories layer for ResearchConnect AI.

Exports database-level retrieval mechanisms independent of HTTP/API concerns.
"""
from app.repositories.lexical_repository import (
    DEFAULT_FTS_CONFIG,
    LexicalRepository,
    LexicalSearchResult,
    build_opportunity_tsvector,
    build_research_work_tsvector,
    lexical_repository,
)
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
    # Vector Retrieval
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
    # Lexical Retrieval
    "LexicalRepository",
    "LexicalSearchResult",
    "DEFAULT_FTS_CONFIG",
    "build_research_work_tsvector",
    "build_opportunity_tsvector",
    "lexical_repository",
]
