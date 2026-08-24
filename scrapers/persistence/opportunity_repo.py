"""
Persistence service and repository for scraped opportunities.

Responsibilities:
1. Find or create Source records and track source health metrics.
2. Record IngestionRun audit entities with detailed pipeline metrics.
3. For each NormalizedOpportunity:
   - Detect changes against existing database records.
   - Insert new records (`LifecycleAction.NEW`).
   - Update modified records (`LifecycleAction.UPDATED`).
   - Refresh `last_seen_at` on unchanged records (`LifecycleAction.UNCHANGED`).
   - Apply deterministic expiration checks (`LifecycleAction.EXPIRED`).
4. Maintain source provenance and database constraints.
5. Provide safe error recovery and transaction management.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scrapers.change_detection.detector import detect_changes
from scrapers.expiration.manager import apply_expiration_status, is_opportunity_expired
from scrapers.models import LifecycleAction, NormalizedOpportunity

logger = logging.getLogger(__name__)


@dataclass
class PersistenceResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_duplicate: int = 0
    potential_duplicates: int = 0
    expired: int = 0
    errors: int = 0
    source_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None


class OpportunityRepository:
    """
    Persists normalized opportunities to the database with lifecycle tracking,
    change detection, freshness timestamping, and source health metrics.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Source Health & Ingestion Runs ────────────────────────────────────────

    def get_or_create_source(self, name: str, base_url: str | None = None) -> uuid.UUID:
        """
        Find or create a Source record by name.
        """
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
                consecutive_failure_count=0,
                total_scrape_count=0,
            )
            self._session.add(source)
            self._session.flush()
            logger.info("Created new Source record: name=%r id=%s", name, source.id)
        else:
            logger.debug("Found existing Source record: name=%r id=%s", name, source.id)

        return source.id

    def start_ingestion_run(self, source_id: uuid.UUID, topic: str | None = None) -> uuid.UUID:
        """
        Create a new IngestionRun record in RUNNING status.
        """
        from app.models.ingestion_run import IngestionRunModel

        run = IngestionRunModel(
            id=uuid.uuid4(),
            source_id=source_id,
            status="RUNNING",
            topic=topic,
            started_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(run)
        self._session.flush()
        return run.id

    def finish_ingestion_run(
        self,
        run_id: uuid.UUID,
        source_id: uuid.UUID,
        status: str,
        result: PersistenceResult,
        pages_fetched: int = 0,
        records_parsed: int = 0,
        records_valid: int = 0,
        records_invalid: int = 0,
        error_message: str | None = None,
    ) -> None:
        """
        Update IngestionRun and Source health metrics upon pipeline completion.
        """
        from app.models.ingestion_run import IngestionRunModel
        from app.models.source import SourceModel

        now = datetime.now(tz=timezone.utc)

        # 1. Update Ingestion Run
        run_stmt = select(IngestionRunModel).where(IngestionRunModel.id == run_id)
        run = self._session.execute(run_stmt).scalar_one_or_none()
        if run:
            run.status = status
            run.pages_fetched = pages_fetched
            run.records_parsed = records_parsed
            run.records_valid = records_valid
            run.records_invalid = records_invalid
            run.records_inserted = result.inserted
            run.records_updated = result.updated
            run.records_unchanged = result.unchanged
            run.duplicates_detected = result.skipped_duplicate
            run.potential_duplicates_detected = result.potential_duplicates
            run.records_expired = result.expired
            run.error_message = error_message
            run.completed_at = now
            self._session.flush()

        # 2. Update Source Health
        source_stmt = select(SourceModel).where(SourceModel.id == source_id)
        source = self._session.execute(source_stmt).scalar_one_or_none()
        if source:
            source.last_scraped_at = now
            source.total_scrape_count += 1
            if status == "COMPLETED" and result.errors == 0:
                source.last_successful_scrape_at = now
                source.consecutive_failure_count = 0
            else:
                source.last_failed_scrape_at = now
                source.consecutive_failure_count += 1
            self._session.flush()

    # ── Batch Persistence ─────────────────────────────────────────────────────

    def save_batch(
        self,
        source_name: str,
        source_base_url: str | None,
        opportunities: list[NormalizedOpportunity],
        topic: str | None = None,
        pages_fetched: int = 0,
        records_parsed: int = 0,
        records_invalid: int = 0,
    ) -> PersistenceResult:
        """
        Persist a batch of normalized opportunities.
        """
        result = PersistenceResult()
        now = datetime.now(tz=timezone.utc)

        try:
            result.source_id = self.get_or_create_source(source_name, source_base_url)
            result.run_id = self.start_ingestion_run(result.source_id, topic=topic)

            for opp in opportunities:
                try:
                    action = self._upsert_opportunity(opp, result.source_id, now)
                    if action == LifecycleAction.NEW:
                        result.inserted += 1
                    elif action == LifecycleAction.UPDATED:
                        result.updated += 1
                    elif action == LifecycleAction.UNCHANGED:
                        result.unchanged += 1
                    elif action == LifecycleAction.DUPLICATE:
                        result.skipped_duplicate += 1
                    elif action == LifecycleAction.POTENTIAL_DUPLICATE:
                        result.potential_duplicates += 1
                    elif action == LifecycleAction.EXPIRED:
                        result.expired += 1

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
                    logger.error("Unexpected error persisting %r: %s", opp.title, exc)
                    result.errors += 1

            status = "COMPLETED" if result.errors == 0 else "FAILED"
            self.finish_ingestion_run(
                run_id=result.run_id,
                source_id=result.source_id,
                status=status,
                result=result,
                pages_fetched=pages_fetched,
                records_parsed=records_parsed,
                records_valid=len(opportunities),
                records_invalid=records_invalid,
            )
            self._session.commit()

        except Exception as exc:  # noqa: BLE001
            self._session.rollback()
            logger.error("Batch persistence failed: %s", exc)
            result.errors += 1
            if result.source_id and result.run_id:
                try:
                    self.finish_ingestion_run(
                        run_id=result.run_id,
                        source_id=result.source_id,
                        status="FAILED",
                        result=result,
                        pages_fetched=pages_fetched,
                        records_parsed=records_parsed,
                        records_valid=len(opportunities),
                        records_invalid=records_invalid,
                        error_message=str(exc),
                    )
                    self._session.commit()
                except Exception:
                    self._session.rollback()

        logger.info(
            "Persistence result: inserted=%d updated=%d unchanged=%d duplicate=%d potential_dup=%d expired=%d errors=%d",
            result.inserted,
            result.updated,
            result.unchanged,
            result.skipped_duplicate,
            result.potential_duplicates,
            result.expired,
            result.errors,
        )
        return result

    # ── Single Opportunity Upsert & Change Detection ──────────────────────────

    def _upsert_opportunity(
        self,
        opp: NormalizedOpportunity,
        source_id: uuid.UUID,
        now: datetime,
    ) -> LifecycleAction:
        """
        Insert or update a single opportunity with change detection and freshness tracking.
        """
        from app.models.opportunity import OpportunityModel

        stmt = select(OpportunityModel).where(
            OpportunityModel.source_id == source_id,
            OpportunityModel.raw_source_id == opp.raw_source_id,
        )
        existing = self._session.execute(stmt).scalar_one_or_none()

        # Check expiration upfront
        is_expired = is_opportunity_expired(opp, now)
        target_status = "EXPIRED" if is_expired else opp.status

        if existing is None:
            # INSERT (NEW)
            new_opp = OpportunityModel(
                id=uuid.uuid4(),
                title=opp.title,
                opportunity_type=opp.opportunity_type,
                slug=None,
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
                indexing=opp.indexing or [],
                apc_or_fee=opp.apc_or_fee,
                status=target_status,
                source_id=source_id,
                raw_source_id=opp.raw_source_id,
                is_predatory_flag=opp.is_predatory_flag,
                last_seen_at=now,
                last_verified_at=now,
            )
            self._session.add(new_opp)
            self._session.flush()
            logger.debug("Inserted new opportunity: %r (id=%s)", opp.title, opp.raw_source_id)
            return LifecycleAction.EXPIRED if is_expired else LifecycleAction.NEW

        else:
            # UPDATE / UNCHANGED Change Detection
            change_result = detect_changes(existing, opp)

            # Always refresh freshness timestamp
            existing.last_seen_at = now

            # If status changed due to expiration, mark that
            if is_expired and existing.status in {"ACTIVE", "UNVERIFIED"}:
                existing.status = "EXPIRED"
                change_result.has_changed = True

            if change_result.has_changed:
                for change in change_result.changes:
                    setattr(existing, change.field_name, change.new_value)
                existing.updated_at = now
                existing.last_verified_at = now
                self._session.flush()
                logger.debug(
                    "Updated opportunity %r: %d fields changed",
                    opp.title,
                    len(change_result.changes),
                )
                return LifecycleAction.UPDATED
            else:
                self._session.flush()
                logger.debug("Unchanged opportunity: %r", opp.title)
                return LifecycleAction.UNCHANGED
