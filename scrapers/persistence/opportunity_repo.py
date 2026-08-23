"""
Persistence service for scraped opportunities.

Responsibilities:
1. Find or create the Source record (upsert by name).
2. For each NormalizedOpportunity:
   a. Check if the (source_id, raw_source_id) record already exists in DB.
   b. If it does not exist → INSERT.
   c. If it does exist → UPDATE mutable fields and bump updated_at.
3. Update source.last_scraped_at after a successful batch.
4. Preserve source provenance (source_id, raw_source_id).
5. Never put scraping/parsing logic here.

DB constraint safety net:
  The DB has a UNIQUE constraint on (source_id, raw_source_id).
  If a duplicate slips through the application-level detector (e.g. parallel
  runs), the INSERT will raise IntegrityError, which we catch and log.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scrapers.models import NormalizedOpportunity

logger = logging.getLogger(__name__)


@dataclass
class PersistenceResult:
    inserted: int = 0
    updated: int = 0
    skipped_duplicate: int = 0
    errors: int = 0
    source_id: uuid.UUID | None = None


class OpportunityRepository:
    """
    Persists normalized opportunities to the PostgreSQL database.

    Designed to be instantiated once per pipeline run with a SQLAlchemy
    Session, then discarded.

    Usage:
        with SessionLocal() as session:
            repo = OpportunityRepository(session)
            result = repo.save_batch(source_name, source_base_url, opportunities)
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Public API ────────────────────────────────────────────────────────────

    def get_or_create_source(self, name: str, base_url: str | None = None) -> uuid.UUID:
        """
        Find or create a Source record by name.

        Returns the UUID of the Source.
        """
        # Import here to keep scrapers/ decoupled from backend app at module level
        from app.models.source import SourceModel

        stmt = select(SourceModel).where(SourceModel.name == name)
        source = self._session.execute(stmt).scalar_one_or_none()

        if source is None:
            source = SourceModel(
                id=uuid.uuid4(),
                name=name,
                source_type="SCRAPER",
                base_url=base_url,
                is_active=True,
                reliability_score=1.00,
            )
            self._session.add(source)
            self._session.flush()
            logger.info("Created new Source record: name=%r id=%s", name, source.id)
        else:
            logger.debug("Found existing Source record: name=%r id=%s", name, source.id)

        return source.id

    def update_source_scraped_at(self, source_id: uuid.UUID) -> None:
        """Stamp source.last_scraped_at = now (UTC) after a successful run."""
        from app.models.source import SourceModel

        stmt = select(SourceModel).where(SourceModel.id == source_id)
        source = self._session.execute(stmt).scalar_one_or_none()
        if source:
            source.last_scraped_at = datetime.now(tz=timezone.utc)
            self._session.flush()

    def save_batch(
        self,
        source_name: str,
        source_base_url: str | None,
        opportunities: list[NormalizedOpportunity],
    ) -> PersistenceResult:
        """
        Persist a batch of normalized opportunities.

        - Upserts the Source record.
        - Inserts new opportunities, updates existing ones.
        - Commits at the end.
        - Returns a PersistenceResult with counts.
        """
        result = PersistenceResult()

        try:
            result.source_id = self.get_or_create_source(source_name, source_base_url)

            for opp in opportunities:
                try:
                    action = self._upsert_opportunity(opp, result.source_id)
                    if action == "inserted":
                        result.inserted += 1
                    elif action == "updated":
                        result.updated += 1
                    elif action == "duplicate":
                        result.skipped_duplicate += 1
                except IntegrityError:
                    self._session.rollback()
                    logger.warning(
                        "DB constraint violation for %r (id=%r) — skipping as duplicate.",
                        opp.title,
                        opp.raw_source_id,
                    )
                    result.skipped_duplicate += 1
                except Exception as exc:  # noqa: BLE001
                    self._session.rollback()
                    logger.error(
                        "Unexpected error persisting %r: %s", opp.title, exc
                    )
                    result.errors += 1

            self.update_source_scraped_at(result.source_id)
            self._session.commit()

        except Exception as exc:  # noqa: BLE001
            self._session.rollback()
            logger.error("Batch persistence failed: %s", exc)
            result.errors += 1

        logger.info(
            "Persistence result: inserted=%d updated=%d duplicate=%d errors=%d",
            result.inserted,
            result.updated,
            result.skipped_duplicate,
            result.errors,
        )
        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    def _upsert_opportunity(
        self, opp: NormalizedOpportunity, source_id: uuid.UUID
    ) -> str:
        """
        Insert or update a single opportunity.

        Returns:
            "inserted" | "updated" | "duplicate"
        """
        from app.models.opportunity import OpportunityModel

        stmt = select(OpportunityModel).where(
            OpportunityModel.source_id == source_id,
            OpportunityModel.raw_source_id == opp.raw_source_id,
        )
        existing = self._session.execute(stmt).scalar_one_or_none()

        if existing is None:
            # INSERT
            new_opp = OpportunityModel(
                id=uuid.uuid4(),
                title=opp.title,
                opportunity_type=opp.opportunity_type,
                slug=None,  # slug generation deferred (Phase 2)
                publisher=opp.publisher,
                organizer=opp.organizer,
                summary=opp.summary,
                description=opp.description,
                website_url=opp.website_url,
                delivery_mode=opp.delivery_mode,
                location=opp.location,
                submission_deadline=opp.submission_deadline,
                event_start_date=opp.event_start_date,
                event_end_date=opp.event_end_date,
                status=opp.status,
                source_id=source_id,
                raw_source_id=opp.raw_source_id,
                is_predatory_flag=opp.is_predatory_flag,
                last_verified_at=datetime.now(tz=timezone.utc),
            )
            self._session.add(new_opp)
            self._session.flush()
            logger.debug("Inserted: %r (source_id=%s)", opp.title, opp.raw_source_id)
            return "inserted"

        else:
            # UPDATE mutable fields only — preserve original created_at and id
            changed = False

            def _set(attr: str, value) -> None:
                nonlocal changed
                if getattr(existing, attr) != value:
                    setattr(existing, attr, value)
                    changed = True

            _set("title", opp.title)
            _set("opportunity_type", opp.opportunity_type)
            _set("publisher", opp.publisher)
            _set("organizer", opp.organizer)
            _set("summary", opp.summary)
            _set("description", opp.description)
            _set("website_url", opp.website_url)
            _set("delivery_mode", opp.delivery_mode)
            _set("location", opp.location)
            _set("submission_deadline", opp.submission_deadline)
            _set("event_start_date", opp.event_start_date)
            _set("event_end_date", opp.event_end_date)

            if changed:
                existing.last_verified_at = datetime.now(tz=timezone.utc)
                self._session.flush()
                logger.debug("Updated: %r (source_id=%s)", opp.title, opp.raw_source_id)
                return "updated"
            else:
                logger.debug("No changes for: %r", opp.title)
                return "duplicate"
