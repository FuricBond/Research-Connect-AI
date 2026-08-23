import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.opportunity import OpportunityModel
from app.schemas.opportunity import (
    OpportunityListItem,
    OpportunityListResponse,
    OpportunityRead,
)


class OpportunitySort(str, Enum):
    newest = "newest"
    deadline = "deadline"
    title = "title"


class OpportunityType(str, Enum):
    CONFERENCE = "CONFERENCE"
    JOURNAL = "JOURNAL"
    WORKSHOP = "WORKSHOP"
    CALL_FOR_PAPERS = "CALL_FOR_PAPERS"
    SPECIAL_ISSUE = "SPECIAL_ISSUE"


class OpportunityStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"
    DRAFT = "DRAFT"
    UNVERIFIED = "UNVERIFIED"


class DeliveryMode(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    HYBRID = "HYBRID"


def list_opportunities(
    db: Session,
    *,
    search: str | None = None,
    opportunity_type: str | None = None,
    status: str | None = None,
    delivery_mode: str | None = None,
    source_id: uuid.UUID | None = None,
    upcoming: bool = False,
    sort: OpportunitySort = OpportunitySort.newest,
    page: int = 1,
    page_size: int = 20,
) -> OpportunityListResponse:
    """Return a paginated, filtered, sorted list of opportunities."""
    stmt = select(OpportunityModel)

    # --- Filters ---
    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(OpportunityModel.title).like(term),
                func.lower(OpportunityModel.summary).like(term),
                func.lower(OpportunityModel.description).like(term),
            )
        )

    if opportunity_type:
        stmt = stmt.where(OpportunityModel.opportunity_type == opportunity_type.upper())

    if status:
        stmt = stmt.where(OpportunityModel.status == status.upper())
    else:
        # Default: don't show archived/draft unless explicitly requested
        stmt = stmt.where(OpportunityModel.status.in_(["ACTIVE", "UNVERIFIED"]))

    if delivery_mode:
        stmt = stmt.where(OpportunityModel.delivery_mode == delivery_mode.upper())

    if source_id:
        stmt = stmt.where(OpportunityModel.source_id == source_id)

    if upcoming:
        now = datetime.now(tz=timezone.utc)
        stmt = stmt.where(
            OpportunityModel.submission_deadline >= now,
        )

    # --- Total count (before pagination) ---
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total: int = db.execute(count_stmt).scalar_one()

    # --- Sorting ---
    if sort == OpportunitySort.deadline:
        # Put NULL deadlines last
        stmt = stmt.order_by(
            OpportunityModel.submission_deadline.asc().nulls_last(),
            OpportunityModel.created_at.desc(),
        )
    elif sort == OpportunitySort.title:
        stmt = stmt.order_by(OpportunityModel.title.asc())
    else:  # newest
        stmt = stmt.order_by(OpportunityModel.created_at.desc())

    # --- Pagination ---
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    rows = db.execute(stmt).scalars().all()

    items = [OpportunityListItem.model_validate(row) for row in rows]

    return OpportunityListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )


def get_opportunity_by_id(
    db: Session,
    opportunity_id: uuid.UUID,
) -> OpportunityRead | None:
    """Fetch a single opportunity by UUID. Returns None if not found."""
    stmt = select(OpportunityModel).where(OpportunityModel.id == opportunity_id)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        return None
    return OpportunityRead.model_validate(row)
