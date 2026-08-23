from datetime import datetime
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
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
    last_scraped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    opportunities: Mapped[list["OpportunityModel"]] = relationship(
        back_populates="source",
    )
