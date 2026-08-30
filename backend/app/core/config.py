from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ResearchConnect AI"
    app_env: str = "development"
    database_url: str = (
        "postgresql+psycopg://researchconnect:researchconnect"
        "@localhost:5432/researchconnect"
    )
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Phase 2.2A — OpenAlex API configuration
    openalex_api_base_url: str = "https://api.openalex.org"
    openalex_email: str = ""  # Optional: enables polite pool access

    # Phase 2.2B — Crossref API configuration
    crossref_api_base_url: str = "https://api.crossref.org"
    crossref_email: str = ""  # Optional: for polite pool access
    crossref_user_agent: str = (
        "ResearchConnect-AI/1.0 (https://researchconnect.ai; mailto:info@researchconnect.ai)"
    )

    # Phase 2.3B — Semantic Embedding configuration
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384
    embedding_batch_size: int = 32
    embedding_device: str = "cpu"  # cpu | cuda | mps

    # Phase 2.4B — Hybrid Search & Candidate Fusion configuration
    hybrid_search_default_limit: int = 20
    hybrid_search_max_limit: int = 100
    hybrid_search_candidate_multiplier: float = 2.5
    hybrid_search_rrf_k: int = 60

    # Phase 2.4C — Similar Research Retrieval configuration
    similar_research_default_limit: int = 20
    similar_research_max_limit: int = 100
    similar_research_candidate_multiplier: float = 2.5
    similar_research_semantic_weight: float = 0.60
    similar_research_lexical_weight: float = 0.20
    similar_research_topic_weight: float = 0.20

    # Phase 2.4D — Research ↔ Opportunity Matching configuration
    research_opportunity_default_limit: int = 20
    research_opportunity_max_limit: int = 100
    research_opportunity_candidate_multiplier: float = 2.5
    research_opportunity_semantic_weight: float = 0.50
    research_opportunity_lexical_weight: float = 0.20
    research_opportunity_topic_weight: float = 0.20
    research_opportunity_type_weight: float = 0.10

    # Phase 2.4E — Hybrid Ranking Engine configuration
    hybrid_ranking_default_limit: int = 20
    hybrid_ranking_max_limit: int = 100
    hybrid_ranking_research_similarity_semantic_weight: float = 0.50
    hybrid_ranking_research_similarity_lexical_weight: float = 0.20
    hybrid_ranking_research_similarity_topic_weight: float = 0.20
    hybrid_ranking_research_similarity_freshness_weight: float = 0.10
    hybrid_ranking_opportunity_semantic_weight: float = 0.45
    hybrid_ranking_opportunity_lexical_weight: float = 0.15
    hybrid_ranking_opportunity_topic_weight: float = 0.20
    hybrid_ranking_opportunity_type_weight: float = 0.10
    hybrid_ranking_opportunity_urgency_weight: float = 0.10
    hybrid_ranking_freshness_half_life_years: float = 5.0
    hybrid_ranking_urgency_window_days: float = 90.0

    # Phase 2.4F — Explainable Results configuration
    explainability_high_threshold: float = 0.75
    explainability_positive_threshold: float = 0.50
    explainability_weak_threshold: float = 0.25
    explainability_max_reasons: int = 6

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
