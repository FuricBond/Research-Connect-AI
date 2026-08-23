from datetime import datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.opportunity import OpportunityTopicModel


class TopicModel(Base):
    """Academic taxonomy topic or research domain (hierarchical)."""

    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        index=True,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Hierarchical self-referencing relationship
    parent: Mapped[Optional["TopicModel"]] = relationship(
        "TopicModel",
        remote_side="TopicModel.id",
        back_populates="children",
    )
    children: Mapped[list["TopicModel"]] = relationship(
        "TopicModel",
        back_populates="parent",
    )

    # Junction relationship
    opportunity_associations: Mapped[list["OpportunityTopicModel"]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
    )
