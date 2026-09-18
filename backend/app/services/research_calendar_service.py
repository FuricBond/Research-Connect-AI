from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, overload
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.calendar import (
    CalendarEventStatus,
    CalendarEventType,
    ResearchCalendarEventModel,
    ResearchCalendarModel,
)
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.research_submission import ResearchSubmissionModel
from app.ranking.deadline.extractors import DeadlineEvidenceExtractor
from app.ranking.deadline.models import (
    ConflictState,
    DeadlinePrecision,
    DeadlineType,
    NormalizationStatus,
    TimezoneIndicator,
)
from app.ranking.deadline.resolvers import DeadlineConflictResolver
from app.schemas.calendar import (
    CalendarCreate,
    CalendarEventCreate,
    CalendarEventRead,
    CalendarEventUpdate,
    CalendarRead,
    CalendarUpdate,
    OpportunityProjectResponse,
    ResearcherCalendarViewResponse,
)

logger = logging.getLogger(__name__)

MILESTONE_TO_EVENT_TYPE: dict[DeadlineType, CalendarEventType] = {
    DeadlineType.SUBMISSION: CalendarEventType.OPPORTUNITY_SUBMISSION,
    DeadlineType.ABSTRACT: CalendarEventType.ABSTRACT_DEADLINE,
    DeadlineType.NOTIFICATION: CalendarEventType.NOTIFICATION,
    DeadlineType.CAMERA_READY: CalendarEventType.CAMERA_READY,
    DeadlineType.REGISTRATION: CalendarEventType.REGISTRATION,
    DeadlineType.EVENT_START: CalendarEventType.EVENT_START,
    DeadlineType.EVENT_END: CalendarEventType.EVENT_END,
    DeadlineType.UNKNOWN: CalendarEventType.RESEARCH_MILESTONE,
}


def _escape_ical_text(text: str | None) -> str:
    """Escape text characters according to RFC 5545 section 3.3.11."""
    if not text:
        return ""
    # Order matters: backslash first, then comma, semicolon, newline
    res = text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    res = res.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return res


def _fold_ical_line(line: str, max_length: int = 75) -> str:
    """Fold lines exceeding max_length octets according to RFC 5545 section 3.1."""
    encoded = line.encode("utf-8")
    if len(encoded) <= max_length:
        return line

    chunks: list[str] = []
    pos = 0
    first = True
    while pos < len(encoded):
        chunk_size = max_length if first else (max_length - 1)
        part = encoded[pos : pos + chunk_size]
        # Safeguard against breaking a multi-byte UTF-8 sequence
        while True:
            try:
                decoded = part.decode("utf-8")
                break
            except UnicodeDecodeError:
                part = part[:-1]
        chunks.append(decoded)
        pos += len(part)
        first = False

    return "\r\n ".join(chunks)


@overload
def _as_utc(dt: None) -> None: ...


@overload
def _as_utc(dt: datetime) -> datetime: ...


def _as_utc(dt: datetime | None) -> datetime | None:
    """Ensure datetime is UTC-aware, interpreting naive datetimes as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_dt(dt: datetime | None) -> datetime | None:
    """Convert datetime to naive UTC representation for deterministic SQLite comparisons."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class ResearchCalendarService:
    """
    Core service managing researcher planning calendars, custom events,
    deterministic canonical deadline projections, and standards-compliant iCal exports.
    """

    # ------------------------------------------------------------------------
    # Calendar Management
    # ------------------------------------------------------------------------

    @classmethod
    def get_or_create_default_calendar(
        cls,
        db: Session,
        user_id: uuid.UUID,
        profile_id: uuid.UUID | None = None,
        preferred_timezone: str = "UTC",
    ) -> ResearchCalendarModel:
        """
        Retrieve or initialize the researcher's default planning calendar.
        Idempotent: returns existing default calendar if present.
        """
        stmt = (
            select(ResearchCalendarModel)
            .where(
                ResearchCalendarModel.user_id == user_id,
                ResearchCalendarModel.is_default.is_(True),
            )
            .order_by(ResearchCalendarModel.created_at.asc())
        )
        existing = db.execute(stmt).scalars().first()
        if existing:
            return existing

        # Fallback check if profile_id is not provided
        eff_profile_id = profile_id
        if eff_profile_id is None:
            profile = db.execute(
                select(ResearchProfileModel).where(ResearchProfileModel.user_id == user_id)
            ).scalars().first()
            if profile:
                eff_profile_id = profile.id

        calendar = ResearchCalendarModel(
            user_id=user_id,
            profile_id=eff_profile_id,
            name="Default Research Calendar",
            description="Primary research planning calendar and deadline projection timeline.",
            timezone=preferred_timezone or "UTC",
            is_default=True,
        )
        db.add(calendar)
        db.commit()
        db.refresh(calendar)
        return calendar

    @classmethod
    def create_calendar(
        cls,
        db: Session,
        user_id: uuid.UUID,
        payload: CalendarCreate,
        profile_id: uuid.UUID | None = None,
    ) -> ResearchCalendarModel:
        """Create a new research calendar for the user."""
        if payload.is_default:
            # Unset existing defaults
            existing_defaults = db.execute(
                select(ResearchCalendarModel).where(
                    ResearchCalendarModel.user_id == user_id,
                    ResearchCalendarModel.is_default.is_(True),
                )
            ).scalars().all()
            for cal in existing_defaults:
                cal.is_default = False

        calendar = ResearchCalendarModel(
            user_id=user_id,
            profile_id=profile_id,
            name=payload.name,
            description=payload.description,
            timezone=payload.timezone or "UTC",
            is_default=payload.is_default,
        )
        db.add(calendar)
        db.commit()
        db.refresh(calendar)
        return calendar

    @classmethod
    def get_calendar(
        cls,
        db: Session,
        calendar_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ResearchCalendarModel:
        """Retrieve calendar enforcing strict owner isolation."""
        calendar = db.execute(
            select(ResearchCalendarModel).where(ResearchCalendarModel.id == calendar_id)
        ).scalars().first()
        if not calendar:
            raise ValueError(f"Calendar with ID '{calendar_id}' not found.")
        if calendar.user_id != user_id:
            raise PermissionError("Forbidden: You do not have access to this research calendar.")
        return calendar

    @classmethod
    def update_calendar(
        cls,
        db: Session,
        calendar_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: CalendarUpdate,
    ) -> ResearchCalendarModel:
        """Update calendar metadata and default flag."""
        calendar = cls.get_calendar(db, calendar_id, user_id)

        if payload.is_default is True and not calendar.is_default:
            # Unset existing defaults
            existing_defaults = db.execute(
                select(ResearchCalendarModel).where(
                    ResearchCalendarModel.user_id == user_id,
                    ResearchCalendarModel.is_default.is_(True),
                )
            ).scalars().all()
            for cal in existing_defaults:
                cal.is_default = False
            calendar.is_default = True
        elif payload.is_default is False:
            calendar.is_default = False

        if payload.name is not None:
            calendar.name = payload.name
        if payload.description is not None:
            calendar.description = payload.description
        if payload.timezone is not None:
            calendar.timezone = payload.timezone

        db.commit()
        db.refresh(calendar)
        return calendar

    @classmethod
    def list_calendars(
        cls,
        db: Session,
        user_id: uuid.UUID,
    ) -> list[ResearchCalendarModel]:
        """List all calendars owned by the researcher."""
        stmt = (
            select(ResearchCalendarModel)
            .where(ResearchCalendarModel.user_id == user_id)
            .order_by(
                ResearchCalendarModel.is_default.desc(),
                ResearchCalendarModel.created_at.asc(),
            )
        )
        return list(db.execute(stmt).scalars().all())

    # ------------------------------------------------------------------------
    # Event Management
    # ------------------------------------------------------------------------

    @classmethod
    def create_user_event(
        cls,
        db: Session,
        calendar_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: CalendarEventCreate,
    ) -> ResearchCalendarEventModel:
        """Create a user-defined research planning milestone or custom event."""
        cls.get_calendar(db, calendar_id, user_id)

        event = ResearchCalendarEventModel(
            calendar_id=calendar_id,
            opportunity_id=payload.opportunity_id,
            submission_id=payload.submission_id,
            title=payload.title,
            description=payload.description,
            event_type=payload.event_type.value,
            start_datetime=payload.start_datetime,
            end_datetime=payload.end_datetime,
            date_str=payload.date_str,
            all_day=payload.all_day,
            timezone=payload.timezone,
            is_canonical_projection=False,
            provenance_metadata=payload.provenance_metadata or {},
            status=payload.status.value,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    @classmethod
    def get_event(
        cls,
        db: Session,
        calendar_id: uuid.UUID,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ResearchCalendarEventModel:
        """Retrieve single event validating calendar ownership."""
        cls.get_calendar(db, calendar_id, user_id)
        event = db.execute(
            select(ResearchCalendarEventModel).where(
                ResearchCalendarEventModel.id == event_id,
                ResearchCalendarEventModel.calendar_id == calendar_id,
            )
        ).scalars().first()
        if not event:
            raise ValueError(f"Calendar event with ID '{event_id}' not found.")
        return event

    @classmethod
    def update_event(
        cls,
        db: Session,
        calendar_id: uuid.UUID,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: CalendarEventUpdate,
    ) -> ResearchCalendarEventModel:
        """Update a calendar event."""
        event = cls.get_event(db, calendar_id, event_id, user_id)

        if payload.title is not None:
            event.title = payload.title
        if payload.description is not None:
            event.description = payload.description
        if payload.event_type is not None:
            event.event_type = payload.event_type.value
        if payload.start_datetime is not None:
            event.start_datetime = payload.start_datetime
        if payload.end_datetime is not None:
            event.end_datetime = payload.end_datetime
        if payload.date_str is not None:
            event.date_str = payload.date_str
        if payload.all_day is not None:
            event.all_day = payload.all_day
        if payload.timezone is not None:
            event.timezone = payload.timezone
        if payload.status is not None:
            event.status = payload.status.value
        if payload.provenance_metadata is not None:
            event.provenance_metadata = {
                **event.provenance_metadata,
                **payload.provenance_metadata,
            }

        db.commit()
        db.refresh(event)
        return event

    @classmethod
    def delete_event(
        cls,
        db: Session,
        calendar_id: uuid.UUID,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Delete a calendar event."""
        event = cls.get_event(db, calendar_id, event_id, user_id)
        db.delete(event)
        db.commit()
        return True

    @classmethod
    def list_events(
        cls,
        db: Session,
        calendar_id: uuid.UUID,
        user_id: uuid.UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        event_type: CalendarEventType | None = None,
        opportunity_id: uuid.UUID | None = None,
        submission_id: uuid.UUID | None = None,
    ) -> list[ResearchCalendarEventModel]:
        """
        List calendar events matching criteria, ordered deterministically.
        Supports bounded date-range filtering using indexed timestamp columns.
        """
        cls.get_calendar(db, calendar_id, user_id)

        stmt = select(ResearchCalendarEventModel).where(
            ResearchCalendarEventModel.calendar_id == calendar_id
        )

        if event_type is not None:
            stmt = stmt.where(ResearchCalendarEventModel.event_type == event_type.value)
        if opportunity_id is not None:
            stmt = stmt.where(ResearchCalendarEventModel.opportunity_id == opportunity_id)
        if submission_id is not None:
            stmt = stmt.where(ResearchCalendarEventModel.submission_id == submission_id)

        if start_date is not None:
            stmt = stmt.where(
                (ResearchCalendarEventModel.start_datetime >= start_date)
                | (ResearchCalendarEventModel.start_datetime.is_(None))
            )
        if end_date is not None:
            stmt = stmt.where(
                (ResearchCalendarEventModel.start_datetime <= end_date)
                | (ResearchCalendarEventModel.start_datetime.is_(None))
            )

        # Deterministic ordering
        stmt = stmt.order_by(
            ResearchCalendarEventModel.start_datetime.asc().nulls_last(),
            ResearchCalendarEventModel.title.asc(),
            ResearchCalendarEventModel.id.asc(),
        )

        return list(db.execute(stmt).scalars().all())

    # ------------------------------------------------------------------------
    # Canonical Opportunity Projection & Synchronization
    # ------------------------------------------------------------------------

    @classmethod
    def project_opportunity_to_calendar(
        cls,
        db: Session,
        calendar_id: uuid.UUID,
        user_id: uuid.UUID,
        opportunity_id: uuid.UUID,
        submission_id: uuid.UUID | None = None,
    ) -> OpportunityProjectResponse:
        """
        Project an opportunity's canonical Phase 2.7 milestones into calendar events.

        CRITICAL INVARIANTS:
        1. Does NOT mutate opportunity, ranking, risk, or personalization data.
        2. Strictly preserves milestone isolation (EVENT_START != SUBMISSION).
        3. Equal-authority deadline conflicts remain unresolved and tagged CONFLICT.
        4. Unknown timezones are NEVER converted to UTC silently.
        5. Idempotent: repeated projections update existing events without creating duplicates.
        """
        cls.get_calendar(db, calendar_id, user_id)

        opp = db.execute(
            select(OpportunityModel).where(OpportunityModel.id == opportunity_id)
        ).scalars().first()
        if not opp:
            raise ValueError(f"Opportunity with ID '{opportunity_id}' not found.")

        # Ground against Phase 2.7 canonical deadline intelligence
        evidence_collection = DeadlineEvidenceExtractor.extract_from_opportunity_model(opp)
        canonical_opp = DeadlineConflictResolver.resolve_opportunity(
            evidence_collection,
            opportunity_id=str(opportunity_id),
        )

        # Fetch all existing projected events for this opportunity in this calendar
        existing_stmt = select(ResearchCalendarEventModel).where(
            ResearchCalendarEventModel.calendar_id == calendar_id,
            ResearchCalendarEventModel.opportunity_id == opportunity_id,
            ResearchCalendarEventModel.is_canonical_projection.is_(True),
        )
        existing_events_by_type: dict[str, ResearchCalendarEventModel] = {
            ev.event_type: ev for ev in db.execute(existing_stmt).scalars().all()
        }

        projected_results: list[ResearchCalendarEventModel] = []
        created_count = 0
        updated_count = 0
        unchanged_count = 0

        for m_type, v in canonical_opp.milestone_views.items():
            cal_event_type = MILESTONE_TO_EVENT_TYPE.get(m_type, CalendarEventType.RESEARCH_MILESTONE)

            # Extract temporal properties strictly from Phase 2.7 canonical view
            canonical_deadline = v.canonical_deadline
            start_dt: datetime | None = None
            date_str: str | None = None
            is_all_day = False
            tz_str: str | None = None

            if (
                canonical_deadline is not None
                and canonical_deadline.normalization_status != NormalizationStatus.MISSING
            ):
                start_dt = canonical_deadline.normalized_utc
                if canonical_deadline.local_date:
                    date_str = canonical_deadline.local_date.isoformat()
                is_all_day = (canonical_deadline.precision == DeadlinePrecision.DATE_ONLY)
                # Preserve original timezone; do NOT default to UTC if unspecified
                tz_str = canonical_deadline.timezone_name or canonical_deadline.timezone_offset


            # Milestone display title
            clean_m_name = m_type.value.replace("_", " ").title()
            opp_venue = getattr(opp, "location", None) or getattr(opp, "publisher", None) or "Venue TBA"
            title = f"{opp.title} — {clean_m_name}"
            desc = (
                f"Canonical {clean_m_name} for {opp.title} ({opp_venue}).\n"
                f"Source: {v.selected_source or 'Canonical Opportunity Evidence'}.\n"
                f"Status: {v.conflict_state.value}."
            )

            # Conflict & revision provenance
            provenance: dict[str, Any] = {
                "opportunity_id": str(opportunity_id),
                "opportunity_title": opp.title,
                "opportunity_venue": opp_venue,
                "milestone_type": m_type.value,
                "conflict_state": v.conflict_state.value,
                "confidence": v.confidence,
                "explanation": v.explanation,
                "raw_value": v.selected_observation.raw_value if v.selected_observation else None,
                "authority_tier": (
                    v.selected_observation.authority_tier.value
                    if (v.selected_observation and hasattr(v.selected_observation.authority_tier, "value"))
                    else None
                ),
                "latest_revision": v.latest_revision.to_dict() if v.latest_revision else None,
                "revision_count": len(v.revision_history),
                "unresolved_alternatives_count": len(v.unresolved_alternatives),
            }

            event_status = (
                CalendarEventStatus.CONFLICT.value
                if v.conflict_state == ConflictState.SOURCE_CONFLICT
                else CalendarEventStatus.ACTIVE.value
            )

            existing_ev = existing_events_by_type.get(cal_event_type.value)
            if existing_ev:
                # Compare for changes
                changed = (
                    existing_ev.title != title
                    or existing_ev.description != desc
                    or _normalize_dt(existing_ev.start_datetime) != _normalize_dt(start_dt)
                    or existing_ev.date_str != date_str
                    or existing_ev.all_day != is_all_day
                    or existing_ev.timezone != tz_str
                    or existing_ev.status != event_status
                    or existing_ev.provenance_metadata != provenance
                    or (submission_id is not None and existing_ev.submission_id != submission_id)
                )
                if changed:
                    existing_ev.title = title
                    existing_ev.description = desc
                    existing_ev.start_datetime = start_dt
                    existing_ev.date_str = date_str
                    existing_ev.all_day = is_all_day
                    existing_ev.timezone = tz_str
                    existing_ev.status = event_status
                    existing_ev.provenance_metadata = provenance
                    if submission_id is not None:
                        existing_ev.submission_id = submission_id
                    updated_count += 1
                else:
                    unchanged_count += 1
                projected_results.append(existing_ev)
            else:
                new_ev = ResearchCalendarEventModel(
                    calendar_id=calendar_id,
                    opportunity_id=opportunity_id,
                    submission_id=submission_id,
                    title=title,
                    description=desc,
                    event_type=cal_event_type.value,
                    start_datetime=start_dt,
                    end_datetime=None,
                    date_str=date_str,
                    all_day=is_all_day,
                    timezone=tz_str,
                    is_canonical_projection=True,
                    provenance_metadata=provenance,
                    status=event_status,
                )
                db.add(new_ev)
                created_count += 1
                projected_results.append(new_ev)

        db.commit()
        for ev in projected_results:
            db.refresh(ev)

        return OpportunityProjectResponse(
            opportunity_id=opportunity_id,
            calendar_id=calendar_id,
            projected_events=[cls.build_event_read(ev) for ev in projected_results],
            created_count=created_count,
            updated_count=updated_count,
            unchanged_count=unchanged_count,
        )

    # ------------------------------------------------------------------------
    # Aggregate Researcher Calendar View
    # ------------------------------------------------------------------------

    @classmethod
    def get_researcher_calendar_view(
        cls,
        db: Session,
        researcher_id: uuid.UUID,
        user_id: uuid.UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        event_type: CalendarEventType | None = None,
        opportunity_id: uuid.UUID | None = None,
        submission_id: uuid.UUID | None = None,
    ) -> ResearcherCalendarViewResponse:
        """
        Aggregate researcher's primary calendar and matching planning events.
        """
        calendar = cls.get_or_create_default_calendar(db, user_id=user_id)
        events = cls.list_events(
            db=db,
            calendar_id=calendar.id,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            event_type=event_type,
            opportunity_id=opportunity_id,
            submission_id=submission_id,
        )

        read_events = [cls.build_event_read(ev) for ev in events]

        conflict_count = sum(1 for ev in read_events if ev.status == CalendarEventStatus.CONFLICT.value)
        extension_count = sum(
            1 for ev in read_events if ev.provenance_metadata.get("latest_revision") is not None
        )
        now_utc = datetime.now(timezone.utc)
        upcoming_count = sum(
            1
            for ev in read_events
            if ev.start_datetime is not None and _as_utc(ev.start_datetime) >= now_utc
        )

        return ResearcherCalendarViewResponse(
            calendar=cls.build_calendar_read(calendar, event_count=len(read_events)),
            events=read_events,
            total_events=len(read_events),
            upcoming_deadlines_count=upcoming_count,
            conflict_count=conflict_count,
            extension_count=extension_count,
        )

    # ------------------------------------------------------------------------
    # Standards-Compliant RFC 5545 iCalendar Export
    # ------------------------------------------------------------------------

    @classmethod
    def generate_ical_feed(
        cls,
        db: Session,
        calendar_id: uuid.UUID,
        user_id: uuid.UUID,
        fixed_dtstamp: datetime | None = None,
    ) -> str:
        """
        Generate RFC 5545-compliant iCalendar text (.ics) for a calendar.

        Guarantees:
        1. VCALENDAR and VEVENT structure with stable UID, DTSTART, DTEND/duration.
        2. Preserves date-only semantics (VALUE=DATE) and timezone semantics.
        3. Deterministic output: sorting by (start_datetime, title, id) produces
           byte-identical content for identical calendar states.
        4. Line folding at 75 octets with CRLF standard per RFC 5545 §3.1.
        5. Zero external dependencies (Pure Python stdlib).
        """
        calendar = cls.get_calendar(db, calendar_id, user_id)
        events = cls.list_events(db=db, calendar_id=calendar_id, user_id=user_id)

        lines: list[str] = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//ResearchConnect AI//Research Calendar//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:{_escape_ical_text(calendar.name)}",
            f"X-WR-TIMEZONE:{calendar.timezone or 'UTC'}",
        ]

        # Use fixed_dtstamp if supplied (for deterministic unit testing), else current UTC
        dtstamp_val = fixed_dtstamp or datetime.now(timezone.utc)
        dtstamp_str = dtstamp_val.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        for ev in events:
            # Skip events with neither start_datetime nor date_str (insufficient temporal information)
            if ev.start_datetime is None and not ev.date_str:
                continue

            lines.append("BEGIN:VEVENT")
            lines.append(f"UID:{ev.id}@researchconnect.ai")
            lines.append(f"DTSTAMP:{dtstamp_str}")
            lines.append(f"SUMMARY:{_escape_ical_text(ev.title)}")
            if ev.description:
                lines.append(f"DESCRIPTION:{_escape_ical_text(ev.description)}")
            lines.append(f"CATEGORIES:{ev.event_type}")
            lines.append("STATUS:CONFIRMED")

            # Date/Time formatting
            if ev.all_day and ev.date_str:
                clean_date = ev.date_str.replace("-", "")
                lines.append(f"DTSTART;VALUE=DATE:{clean_date}")
                lines.append(f"DTEND;VALUE=DATE:{clean_date}")
            elif ev.start_datetime is not None:
                utc_start = _as_utc(ev.start_datetime)
                lines.append(f"DTSTART:{utc_start.strftime('%Y%m%dT%H%M%SZ')}")
                if ev.end_datetime is not None:
                    utc_end = _as_utc(ev.end_datetime)
                    lines.append(f"DTEND:{utc_end.strftime('%Y%m%dT%H%M%SZ')}")

            # Provenance headers
            if ev.opportunity_id:
                lines.append(f"X-RC-OPPORTUNITY-ID:{ev.opportunity_id}")
            if ev.submission_id:
                lines.append(f"X-RC-SUBMISSION-ID:{ev.submission_id}")
            if ev.timezone:
                lines.append(f"X-RC-ORIGINAL-TZ:{_escape_ical_text(ev.timezone)}")

            lines.append("END:VEVENT")

        lines.append("END:VCALENDAR")

        # Fold lines according to RFC 5545 section 3.1
        folded_lines = [_fold_ical_line(line) for line in lines]
        return "\r\n".join(folded_lines) + "\r\n"

    # ------------------------------------------------------------------------
    # Schema Builders
    # ------------------------------------------------------------------------

    @classmethod
    def build_calendar_read(
        cls,
        model: ResearchCalendarModel,
        event_count: int = 0,
    ) -> CalendarRead:
        """Serialize ResearchCalendarModel to CalendarRead schema."""
        return CalendarRead(
            id=model.id,
            user_id=model.user_id,
            profile_id=model.profile_id,
            name=model.name,
            description=model.description,
            timezone=model.timezone,
            is_default=model.is_default,
            created_at=model.created_at,
            updated_at=model.updated_at,
            event_count=event_count,
        )

    @classmethod
    def build_event_read(
        cls,
        model: ResearchCalendarEventModel,
    ) -> CalendarEventRead:
        """Serialize ResearchCalendarEventModel to CalendarEventRead schema."""
        return CalendarEventRead(
            id=model.id,
            calendar_id=model.calendar_id,
            opportunity_id=model.opportunity_id,
            submission_id=model.submission_id,
            title=model.title,
            description=model.description,
            event_type=model.event_type,
            start_datetime=model.start_datetime,
            end_datetime=model.end_datetime,
            date_str=model.date_str,
            all_day=model.all_day,
            timezone=model.timezone,
            is_canonical_projection=model.is_canonical_projection,
            provenance_metadata=model.provenance_metadata or {},
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
