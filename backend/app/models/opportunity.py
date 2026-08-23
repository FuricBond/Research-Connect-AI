from sqlalchemy import Date, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class OpportunityModel(Base):
    __tablename__ = "opportunities"

    id: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    opportunity_type: Mapped[str] = mapped_column(Text)
    deadline: Mapped[str | None] = mapped_column(Date, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
