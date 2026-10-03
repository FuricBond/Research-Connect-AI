"""
Phase 5.14 — Personal reading list.

A signed-in user saves research works to read, tracks each one as TO_READ, READING or DONE, and
keeps private notes. Items belong to the user who saved them: nobody else can read, change or
export them, and notes never leave the platform in a BibTeX export.

Saving a paper here is a private bookkeeping action, not a preference signal, so it is never
recorded as a personalization interaction.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.research_knowledge import ResearchWorkModel


class ReadingStatus(str, Enum):
    """Where a saved paper stands in the reader's own queue."""

    TO_READ = "TO_READ"
    READING = "READING"
    DONE = "DONE"


class ReadingListItemModel(Base, TimestampMixin):
    """One research work on one user's reading list (Phase 5.14)."""

    __tablename__ = "reading_list_items"
    __table_args__ = (
        UniqueConstraint("user_id", "work_id", name="uq_reading_list_items_user_work"),
        CheckConstraint(
            "status IN ('TO_READ', 'READING', 'DONE')",
            name="chk_reading_list_items_status",
        ),
        Index("idx_reading_list_user_status", "user_id", "status"),
        Index("idx_reading_list_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_works.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=ReadingStatus.TO_READ.value,
        server_default=ReadingStatus.TO_READ.value,
        nullable=False,
    )
    # Private to the owner; never included in an export.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    status_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # First time the item entered READING; kept if it later goes back to TO_READ.
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # When it entered DONE; cleared when it leaves DONE.
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    work: Mapped["ResearchWorkModel"] = relationship()
