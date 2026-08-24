from datetime import datetime
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.ingestion_run import IngestionRunModel
    from app.models.opportunity import OpportunityModel


class SourceModel(Base, TimestampMixin):
    """Origin data source / feed configuration and health metrics."""

    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('SCRAPER', 'RSS', 'API', 'MANUAL')",
            name="chk_sources_source_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(
        String(50),
        default="SCRAPER",
        nullable=False,
    )
    base_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    reliability_score: Mapped[float] = mapped_column(
        Numeric(3, 2),
        default=1.00,
        nullable=False,
    )

    # Operational Health & Metrics
    last_scraped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_successful_scrape_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_failed_scrape_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    consecutive_failure_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    total_scrape_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Relationships
    opportunities: Mapped[list["OpportunityModel"]] = relationship(
        back_populates="source",
    )
    ingestion_runs: Mapped[list["IngestionRunModel"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )
