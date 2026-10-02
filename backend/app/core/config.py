from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Phase 6.4 — the local-development connection string. Production refuses these
# credentials (app.core.security.validate_security_settings), so a deployment that forgets
# DATABASE_URL fails at startup instead of silently using them.
DEVELOPMENT_DATABASE_URL = (
    "postgresql+psycopg://researchconnect:researchconnect@localhost:5432/researchconnect"
)


class Settings(BaseSettings):
    app_name: str = "ResearchConnect AI"
    # development | test | production, case-insensitive. Any other value is refused, so a
    # mistyped "Production" or "prod" can never run with development defaults.
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = DEVELOPMENT_DATABASE_URL
    # Next.js dev server (Phase 2.4K migrated the frontend from Vite :5173 to Next.js :3000).
    # Exact origins only (scheme://host[:port]); a wildcard is refused because the API
    # accepts credentials.
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Phase 6 — Authentication & identity
    # HMAC signing secret. Leave empty in development to use an ephemeral per-process
    # key (tokens are invalidated on restart). Mandatory when APP_ENV=production: at least
    # 32 characters and not trivially repetitive.
    auth_secret_key: str = ""
    # Symmetric algorithms only: the key is a shared secret, never a public key.
    auth_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    auth_issuer: str = "researchconnect-ai"
    # There is no token revocation, so lifetimes are capped at 7 days.
    auth_access_token_expire_minutes: int = Field(default=480, ge=1, le=10_080)
    # bcrypt accepts 4-31; production requires at least 10.
    auth_bcrypt_rounds: int = Field(default=12, ge=4, le=31)
    auth_login_rate_limit_per_minute: int = Field(default=10, ge=1)
    # Developer-only: trust a raw X-User-ID header as identity and allow anonymous
    # profile bootstrap. Spoofable by design — refused at startup when APP_ENV=production.
    auth_dev_identity_enabled: bool = False

    # Honour X-Forwarded-For / X-Real-IP for client identification (rate limiting).
    # Enable only when the API sits behind a reverse proxy that overwrites these headers.
    trust_proxy_headers: bool = False

    # Phase 6 — Structured logging (both case-insensitive)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["text", "json"] = "text"

    # Phase 6.4 — Interactive API documentation (/docs, /redoc, /openapi.json). Unset means
    # served outside production and not in production; set true or false to override.
    api_docs_enabled: bool | None = None

    # Phase 6.3 — Background scheduler (docs/architecture/phase6-3-scheduler.md).
    # Off by default: when false no scheduler task starts, no job runs and nothing polls
    # the database, so tests and the host development loop are unaffected.
    scheduler_enabled: bool = False
    # The only job that makes outbound requests (WikiCFP ingestion). It needs its own
    # switch so that enabling local maintenance never starts third-party scraping.
    scheduler_opportunity_refresh_enabled: bool = False
    scheduler_opportunity_refresh_topic: str = "artificial intelligence"
    scheduler_opportunity_refresh_max_pages: int = Field(default=1, ge=1, le=20)
    # Seconds between the starts of consecutive runs of each job.
    scheduler_opportunity_refresh_interval_seconds: int = Field(default=86_400, ge=60)
    scheduler_adaptive_refresh_interval_seconds: int = Field(default=21_600, ge=60)
    scheduler_governance_refresh_interval_seconds: int = Field(default=43_200, ge=60)
    scheduler_reminder_interval_seconds: int = Field(default=300, ge=60)
    scheduler_deadline_expiry_interval_seconds: int = Field(default=3_600, ge=60)

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
    # Load the embedding model in the background at startup, so the first literature search
    # does not pay for it. Off by default: tests and the host development loop never load
    # the model unless a search asks for it. Compose turns it on.
    embedding_warmup_on_startup: bool = False

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

    # Phase 2.4E/2.4J — Hybrid Ranking Engine configuration
    hybrid_ranking_default_limit: int = 20
    hybrid_ranking_max_limit: int = 100
    hybrid_ranking_research_similarity_semantic_weight: float = 0.50
    hybrid_ranking_research_similarity_lexical_weight: float = 0.20
    hybrid_ranking_research_similarity_topic_weight: float = 0.20
    hybrid_ranking_research_similarity_freshness_weight: float = 0.10
    hybrid_ranking_opportunity_semantic_weight: float = 0.40
    hybrid_ranking_opportunity_lexical_weight: float = 0.15
    hybrid_ranking_opportunity_topic_weight: float = 0.20
    hybrid_ranking_opportunity_type_weight: float = 0.10
    hybrid_ranking_opportunity_urgency_weight: float = 0.05
    hybrid_ranking_opportunity_quality_weight: float = 0.10
    hybrid_ranking_predatory_penalty_factor: float = 0.20
    opportunity_quality_indexing_weight: float = 0.70
    opportunity_quality_status_weight: float = 0.30
    hybrid_ranking_freshness_half_life_years: float = 5.0
    hybrid_ranking_urgency_window_days: float = 90.0

    # Phase 2.4F — Explainable Results configuration
    explainability_high_threshold: float = 0.75
    explainability_positive_threshold: float = 0.50
    explainability_weak_threshold: float = 0.25
    explainability_max_reasons: int = 8

    # Phase 2.4K — Production Hardening (Rate Limiting & Response Caching)
    discovery_rate_limiting_enabled: bool = True
    discovery_rate_limit_per_minute: int = Field(default=60, ge=1)
    discovery_cache_enabled: bool = True
    discovery_cache_ttl_seconds: int = 60
    discovery_cache_max_entries: int = 1000

    # Phase 2.4M — Lightweight Cross-Encoder Reranking configuration
    reranker_enabled: bool = False
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_top_k: int = 20
    reranker_weight: float = 0.10
    reranker_timeout_ms: int = 200
    reranker_max_batch_size: int = 32

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("app_env", "log_format", mode="before")
    @classmethod
    def _lowercase(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("log_level", mode="before")
    @classmethod
    def _uppercase(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("cors_origins")
    @classmethod
    def _exact_origins(cls, origins: list[str]) -> list[str]:
        """
        Each entry must be exactly what a browser sends in the Origin header. Anything else
        either never matches (a trailing slash or a path silently breaks the frontend) or,
        for a wildcard, lets every site make credentialed requests.
        """
        for origin in origins:
            if "*" in origin:
                raise ValueError(
                    "CORS_ORIGINS must list exact origins; '*' is not allowed because the "
                    "API accepts credentials"
                )
            try:
                parts = urlsplit(origin)
                port_ok = parts.port is None or parts.port > 0
            except ValueError:
                port_ok = False
            if (
                parts.scheme not in ("http", "https")
                or not parts.hostname
                or not port_ok
                or parts.username is not None
                or parts.password is not None
                or parts.path
                or parts.query
                or parts.fragment
                or origin != origin.lower()
            ):
                raise ValueError(
                    f"CORS_ORIGINS entry {origin!r} is not an origin: use lowercase "
                    "scheme://host[:port] with no path, query or trailing slash"
                )
        return origins

    @property
    def serve_api_docs(self) -> bool:
        """Whether /docs, /redoc and /openapi.json are served (off in production by default)."""
        if self.api_docs_enabled is not None:
            return self.api_docs_enabled
        return self.app_env != "production"


settings = Settings()
