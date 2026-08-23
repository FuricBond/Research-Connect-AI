from datetime import date, datetime
from decimal import Decimal
import uuid

from pydantic import BaseModel, ConfigDict


class OpportunityFee(BaseModel):
    """Fee/APC information for an opportunity."""
    has_fee: bool = False
    amount: float | None = None
    currency: str | None = None
    fee_type: str | None = None


class OpportunityBase(BaseModel):
    """Shared fields for opportunity read responses."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    opportunity_type: str
    slug: str | None = None

    # Organizational
    publisher: str | None = None
    organizer: str | None = None
    series_name: str | None = None
    edition: str | None = None

    # Content
    summary: str | None = None
    description: str | None = None

    # Access & Location
    website_url: str | None = None
    submission_url: str | None = None
    delivery_mode: str
    location: str | None = None

    # Dates
    submission_deadline: datetime | None = None
    notification_date: datetime | None = None
    camera_ready_deadline: datetime | None = None
    event_start_date: date | None = None
    event_end_date: date | None = None

    # Quality, Trust & Risk
    indexing: list[str] | None = None
    apc_or_fee: dict | None = None
    is_predatory_flag: bool
    risk_score: Decimal | None = None
    risk_reasons: list[str] | None = None

    # Status & Lifecycle
    status: str
    source_id: uuid.UUID | None = None
    last_verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class OpportunityRead(OpportunityBase):
    """Full opportunity response schema."""
    pass


class OpportunityListItem(BaseModel):
    """Lighter schema for list responses — omits large text fields."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    opportunity_type: str
    publisher: str | None = None
    organizer: str | None = None
    summary: str | None = None
    delivery_mode: str
    location: str | None = None
    submission_deadline: datetime | None = None
    event_start_date: date | None = None
    event_end_date: date | None = None
    indexing: list[str] | None = None
    website_url: str | None = None
    submission_url: str | None = None
    is_predatory_flag: bool
    risk_score: Decimal | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class OpportunityListResponse(BaseModel):
    """Paginated list response envelope for opportunities."""
    items: list[OpportunityListItem]
    page: int
    page_size: int
    total: int
