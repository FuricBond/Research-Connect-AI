from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import Boolean, CheckConstraint, String, false, true
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.opportunity import OpportunityModel
    from app.models.research_profile import ResearchProfileModel
    from app.models.saved_opportunity import SavedOpportunityModel


class UserModel(Base, TimestampMixin):
    """User account model supporting students, faculty, and administrators."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('STUDENT', 'FACULTY', 'ADMIN')",
            name="chk_users_role",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(50),
        default="STUDENT",
        server_default="STUDENT",
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
        nullable=False,
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )

    # Relationships
    research_profile: Mapped[Optional["ResearchProfileModel"]] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    saved_opportunities: Mapped[list["SavedOpportunityModel"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
