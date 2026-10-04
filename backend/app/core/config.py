from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Phase 6.4 — the local-development connection string. Production refuses these
# credentials (app.core.security.validate_security_settings), so a deployment that forgets
# DATABASE_URL fails at startup instead of silently using them.
DEVELOPMENT_DATABASE_URL = (
    "postgresql+psycopg://researchconnect:researchconnect@localhost:5432/researchconnect"
)


def parse_subfield_ids(text: str) -> tuple[str, ...]:
    """
    Research refresh: split a comma-separated list of OpenAlex subfield ids, e.g.
    "1702,1707". Blanks around entries and empty entries are dropped, and repeats are kept
    once in their first position. Every id must be ASCII digits, because each one is placed
    verbatim into an OpenAlex filter clause.
    """
    ids: list[str] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if not (part.isascii() and part.isdigit()):
            raise ValueError(f"OpenAlex subfield id {part!r} must be digits only, e.g. 1702")
        if part not in ids:
            ids.append(part)
    return tuple(ids)


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
    # Each job that makes outbound requests has its own switch, so enabling local
    # maintenance never starts third-party traffic. WikiCFP ingestion:
    scheduler_opportunity_refresh_enabled: bool = False
    scheduler_opportunity_refresh_topic: str = "artificial intelligence"
    scheduler_opportunity_refresh_max_pages: int = Field(default=1, ge=1, le=20)
    # Research refresh: newly published OpenAlex works, tagged and embedded. What it
    # fetches is configured under OpenAlex below.
    scheduler_research_refresh_enabled: bool = False
    # Seconds between the starts of consecutive runs of each job.
    scheduler_opportunity_refresh_interval_seconds: int = Field(default=86_400, ge=60)
    # 8 h by default; 28,800-36,000 for every 8-10 h. Use 120 only for testing.
    scheduler_research_refresh_interval_seconds: int = Field(default=28_800, ge=60)
    scheduler_adaptive_refresh_interval_seconds: int = Field(default=21_600, ge=60)
    scheduler_governance_refresh_interval_seconds: int = Field(default=43_200, ge=60)
    scheduler_reminder_interval_seconds: int = Field(default=300, ge=60)
    scheduler_deadline_expiry_interval_seconds: int = Field(default=3_600, ge=60)
    # Phase 5.16: seconds between email_dispatch passes (only scheduled with EMAIL_PROVIDER=smtp).
    scheduler_email_interval_seconds: int = Field(default=60, ge=60)

    # Phase 5.16 — Email delivery (docs/architecture/phase5-16-email-delivery.md).
    # "mock" keeps every email in memory (the default; tests and CI). "smtp" sends real email
    # through the server below and adds the email_dispatch scheduler job.
    email_provider: Literal["mock", "smtp"] = "mock"
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65_535)
    smtp_username: str = ""
    # Never logged or returned by the API.
    smtp_password: SecretStr = SecretStr("")
    # starttls (port 587), ssl (port 465) or none (a local relay only).
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_seconds: int = Field(default=10, ge=1, le=60)
    email_from_address: str = ""
    email_from_name: str = "ResearchConnect AI"
    # Who may receive real email: comma-separated addresses and @domains, or "*" for everyone.
    # Empty means nobody, so a database of seeded users is never mailed by accident.
    email_recipient_allowlist: str = ""
    # Base URL of the web app, for the links inside emails.
    app_public_url: str = "http://localhost:3000"

    # Phase 2.2A — OpenAlex API configuration
    openalex_api_base_url: str = "https://api.openalex.org"
    openalex_email: str = ""  # Optional: enables polite pool access
    # Optional free account key: ten times the keyless daily budget. Sent as ?api_key= and
    # never logged. It has to be a setting because backend/.env refuses unknown keys and
    # nothing copies backend/.env into the process environment.
    openalex_api_key: str = ""

    # Research refresh — what the scheduled OpenAlex job fetches
    # Comma-separated OpenAlex subfield ids (1702 = Artificial Intelligence). A string, not
    # a list: pydantic-settings JSON-decodes list fields from the environment and .env, so
    # "1702,1707" would fail at import. Read the parsed ids from research_refresh_subfield_ids.
    research_refresh_subfields: str = "1702"
    # Pages per run of each lane: newly published works, and recent works gaining
    # citations. 0 switches a lane off.
    research_refresh_new_pages: int = Field(default=1, ge=0, le=10)
    research_refresh_rising_pages: int = Field(default=1, ge=0, le=10)
    # How far back, in days of publication date, each lane looks.
    research_refresh_new_window_days: int = Field(default=14, ge=1, le=365)
    research_refresh_rising_window_days: int = Field(default=365, ge=1, le=3_650)
    # Corpus cap: once research_works holds this many rows the job stops inserting new
    # works but keeps refreshing the ones it has.
    research_refresh_max_works: int = Field(default=100_000, ge=1)

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

    @field_validator("research_refresh_subfields")
    @classmethod
    def _subfield_ids(cls, value: str) -> str:
        """Normalize to "1702,1707"; an empty list would make the job fetch nothing."""
        ids = parse_subfield_ids(value)
        if not ids:
            raise ValueError("RESEARCH_REFRESH_SUBFIELDS must list at least one subfield id")
        return ",".join(ids)

    @model_validator(mode="after")
    def _smtp_complete(self) -> "Settings":
        """EMAIL_PROVIDER=smtp without a server or a sender would fail on every email."""
        if self.email_provider == "smtp":
            missing = [
                name
                for name, value in (
                    ("SMTP_HOST", self.smtp_host),
                    ("EMAIL_FROM_ADDRESS", self.email_from_address),
                )
                if not value.strip()
            ]
            if missing:
                raise ValueError(f"EMAIL_PROVIDER=smtp needs {', '.join(missing)}")
        return self

    @property
    def research_refresh_subfield_ids(self) -> tuple[str, ...]:
        """The configured OpenAlex subfield ids, in order and without repeats."""
        return parse_subfield_ids(self.research_refresh_subfields)

    @property
    def serve_api_docs(self) -> bool:
        """Whether /docs, /redoc and /openapi.json are served (off in production by default)."""
        if self.api_docs_enabled is not None:
            return self.api_docs_enabled
        return self.app_env != "production"


settings = Settings()
