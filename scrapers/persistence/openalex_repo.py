"""
Persistence repository for OpenAlex research knowledge entities.

Responsibilities:
  1. Find-or-create the "OpenAlex" Source record (provenance).
  2. Record IngestionRun audit entries (reuses existing IngestionRunModel).
  3. For each entity type (works, researchers, research_sources, institutions):
     - Use ``openalex_id`` as the identity key (NOT title matching).
     - Insert new records (LifecycleAction.NEW).
     - Update modified records (LifecycleAction.UPDATED).
     - Refresh ``last_seen_at`` on unchanged records (LifecycleAction.UNCHANGED).
  4. Manage junction tables (research_work_authors, research_work_institutions).
  5. Provide idempotent batch upsert: running the same query twice
     produces UNCHANGED records on the second run.
  6. Persist page by page for bulk loads: one SAVEPOINT per work, so a bad
     record is skipped on its own, and one commit per page.

Change detection for research entities:
  Unlike opportunities (which have a rich change-detection module), research
  entities use a simpler field-by-field comparison on a small set of tracked
  fields.  This avoids over-engineering for entities that change rarely.

Concurrency note:
  This repository is NOT thread-safe.  Each pipeline run should use its own
  Session and repository instance.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scrapers.models import LifecycleAction
from scrapers.openalex.models import (
    AuthorshipEntry,
    NormalizedInstitution,
    NormalizedResearchSource,
    NormalizedResearcher,
    NormalizedWork,
)

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────────


@dataclass
class OpenAlexPersistenceResult:
    """Metrics collected during a single OpenAlex batch ingestion run."""
    works_inserted: int = 0
    works_updated: int = 0
    works_unchanged: int = 0
    works_invalid: int = 0
    works_errors: int = 0

    researchers_inserted: int = 0
    researchers_updated: int = 0
    researchers_unchanged: int = 0

    sources_inserted: int = 0
    sources_updated: int = 0
    sources_unchanged: int = 0

    institutions_inserted: int = 0
    institutions_updated: int = 0
    institutions_unchanged: int = 0

    errors: int = 0
    source_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None

    @property
    def total_inserted(self) -> int:
        return (
            self.works_inserted
            + self.researchers_inserted
            + self.sources_inserted
            + self.institutions_inserted
        )


# ── Tracked fields per entity ─────────────────────────────────────────────────

_WORK_TRACKED = [
    "title", "abstract", "publication_year", "publication_date",
    "work_type", "language", "cited_by_count", "is_oa", "oa_status",
    "landing_page_url",
]
_RESEARCHER_TRACKED = ["display_name", "orcid", "works_count", "cited_by_count"]
_SOURCE_TRACKED = [
    "display_name", "source_type", "issn_l", "is_oa", "is_in_doaj",
    "host_organization", "works_count", "cited_by_count", "homepage_url",
]
_INSTITUTION_TRACKED = [
    "display_name", "ror", "country_code", "institution_type",
    "homepage_url", "works_count", "cited_by_count",
]


def _has_changed(existing: Any, normalised: Any, tracked_fields: list[str]) -> bool:
    """Return True if any tracked field differs between DB row and normalised model."""
    for field_name in tracked_fields:
        db_val = getattr(existing, field_name, None)
        new_val = getattr(normalised, field_name, None)
        if db_val != new_val:
            # Don't overwrite existing non-null with None
            if new_val is None and db_val is not None:
                continue
            return True
    return False


# ── Repository ────────────────────────────────────────────────────────────────


class OpenAlexRepository:
    """
    Persists normalised OpenAlex research entities to the database.

    Designed to be instantiated once per pipeline run with a single Session.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

        # In-memory caches to avoid redundant DB lookups within a single run.
        # Maps openalex_id (compact) → database UUID
        self._researcher_cache: dict[str, uuid.UUID] = {}
        self._source_cache: dict[str, uuid.UUID] = {}
        self._institution_cache: dict[str, uuid.UUID] = {}
        # Cache entries for rows inserted by the work currently being saved. If that
        # work's savepoint is rolled back the rows are gone, so these entries must go
        # too, or the next work by the same author would link to a missing row.
        self._uncommitted_cache_keys: list[tuple[dict[str, uuid.UUID], str]] = []

    def _remember_new(self, cache: dict[str, uuid.UUID], openalex_id: str, db_id: uuid.UUID) -> None:
        cache[openalex_id] = db_id
        self._uncommitted_cache_keys.append((cache, openalex_id))

    def _forget_uncommitted_cache_keys(self) -> None:
        for cache, openalex_id in self._uncommitted_cache_keys:
            cache.pop(openalex_id, None)
        self._uncommitted_cache_keys.clear()

    def _clear_caches(self) -> None:
        self._researcher_cache.clear()
        self._source_cache.clear()
        self._institution_cache.clear()
        self._uncommitted_cache_keys.clear()

    # ── Source & IngestionRun (reuse existing models) ─────────────────────────

    def get_or_create_openalex_source(self) -> uuid.UUID:
        """
        Find or create the "OpenAlex" entry in the ``sources`` table.

        This is the provenance record that links all research knowledge
        entities to OpenAlex as their origin.
        """
        from app.models.source import SourceModel

        stmt = select(SourceModel).where(SourceModel.name == "OpenAlex")
        source = self._session.execute(stmt).scalar_one_or_none()

        if source is None:
            source = SourceModel(
                id=uuid.uuid4(),
                name="OpenAlex",
                source_type="API",
                base_url="https://api.openalex.org",
                is_active=True,
                reliability_score=1.00,
                consecutive_failure_count=0,
                total_scrape_count=0,
            )
            self._session.add(source)
            self._session.flush()
            logger.info("Created new Source record: name='OpenAlex' id=%s", source.id)
        else:
            logger.debug("Found existing Source record: name='OpenAlex' id=%s", source.id)

        return source.id

    def start_ingestion_run(
        self,
        source_id: uuid.UUID,
        search_query: str | None = None,
    ) -> uuid.UUID:
        """Create a new IngestionRun record in RUNNING status."""
        from app.models.ingestion_run import IngestionRunModel

        run = IngestionRunModel(
            id=uuid.uuid4(),
            source_id=source_id,
            status="RUNNING",
            topic=search_query,
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
        result: OpenAlexPersistenceResult,
        pages_fetched: int = 0,
        records_parsed: int = 0,
        records_valid: int = 0,
        records_invalid: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Update IngestionRun and Source health metrics on completion."""
        from app.models.ingestion_run import IngestionRunModel
        from app.models.source import SourceModel

        now = datetime.now(tz=timezone.utc)

        run_stmt = select(IngestionRunModel).where(IngestionRunModel.id == run_id)
        run = self._session.execute(run_stmt).scalar_one_or_none()
        if run:
            run.status = status
            run.pages_fetched = pages_fetched
            run.records_parsed = records_parsed
            run.records_valid = records_valid
            run.records_invalid = records_invalid
            run.records_inserted = result.works_inserted
            run.records_updated = result.works_updated
            run.records_unchanged = result.works_unchanged
            run.duplicates_detected = 0
            run.potential_duplicates_detected = 0
            run.records_expired = 0
            run.error_message = error_message
            run.metrics_detail = {
                "researchers_inserted": result.researchers_inserted,
                "researchers_updated": result.researchers_updated,
                "researchers_unchanged": result.researchers_unchanged,
                "sources_inserted": result.sources_inserted,
                "sources_updated": result.sources_updated,
                "sources_unchanged": result.sources_unchanged,
                "institutions_inserted": result.institutions_inserted,
                "institutions_updated": result.institutions_updated,
                "institutions_unchanged": result.institutions_unchanged,
                "total_errors": result.errors,
            }
            run.completed_at = now
            self._session.flush()

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

    # ── Institution upsert ────────────────────────────────────────────────────

    def upsert_institution(
        self,
        institution: NormalizedInstitution,
        now: datetime,
    ) -> tuple[LifecycleAction, uuid.UUID]:
        """
        Upsert an institution.  Returns (action, db_uuid).

        Caches the result by openalex_id so repeated calls within one run
        are cheap.
        """
        from app.models.research_knowledge import InstitutionModel

        if institution.openalex_id in self._institution_cache:
            db_id = self._institution_cache[institution.openalex_id]
            # Still refresh last_seen_at
            stmt = select(InstitutionModel).where(InstitutionModel.id == db_id)
            existing = self._session.execute(stmt).scalar_one_or_none()
            if existing:
                existing.last_seen_at = now
                self._session.flush()
            return LifecycleAction.UNCHANGED, db_id

        stmt = select(InstitutionModel).where(
            InstitutionModel.openalex_id == institution.openalex_id
        )
        existing = self._session.execute(stmt).scalar_one_or_none()

        if existing is None:
            new_inst = InstitutionModel(
                id=uuid.uuid4(),
                openalex_id=institution.openalex_id,
                display_name=institution.display_name,
                ror=institution.ror,
                country_code=institution.country_code,
                institution_type=institution.institution_type,
                homepage_url=institution.homepage_url,
                works_count=institution.works_count,
                cited_by_count=institution.cited_by_count,
                raw_metadata=institution.raw_metadata,
                last_seen_at=now,
            )
            self._session.add(new_inst)
            self._session.flush()
            self._remember_new(self._institution_cache, institution.openalex_id, new_inst.id)
            logger.debug("Inserted institution: %r (%s)", institution.display_name, institution.openalex_id)
            return LifecycleAction.NEW, new_inst.id
        else:
            existing.last_seen_at = now
            if _has_changed(existing, institution, _INSTITUTION_TRACKED):
                for f in _INSTITUTION_TRACKED:
                    new_val = getattr(institution, f, None)
                    if new_val is not None or getattr(existing, f, None) is None:
                        setattr(existing, f, new_val)
                self._session.flush()
                self._institution_cache[institution.openalex_id] = existing.id
                return LifecycleAction.UPDATED, existing.id
            self._session.flush()
            self._institution_cache[institution.openalex_id] = existing.id
            return LifecycleAction.UNCHANGED, existing.id

    # ── Researcher upsert ─────────────────────────────────────────────────────

    def upsert_researcher(
        self,
        researcher: NormalizedResearcher,
        now: datetime,
    ) -> tuple[LifecycleAction, uuid.UUID]:
        """Upsert a researcher.  Returns (action, db_uuid)."""
        from app.models.research_knowledge import ResearcherModel

        if researcher.openalex_id in self._researcher_cache:
            db_id = self._researcher_cache[researcher.openalex_id]
            stmt = select(ResearcherModel).where(ResearcherModel.id == db_id)
            existing = self._session.execute(stmt).scalar_one_or_none()
            if existing:
                existing.last_seen_at = now
                self._session.flush()
            return LifecycleAction.UNCHANGED, db_id

        stmt = select(ResearcherModel).where(
            ResearcherModel.openalex_id == researcher.openalex_id
        )
        existing = self._session.execute(stmt).scalar_one_or_none()

        if existing is None:
            new_r = ResearcherModel(
                id=uuid.uuid4(),
                openalex_id=researcher.openalex_id,
                display_name=researcher.display_name,
                orcid=researcher.orcid,
                works_count=researcher.works_count,
                cited_by_count=researcher.cited_by_count,
                raw_metadata=researcher.raw_metadata,
                last_seen_at=now,
            )
            self._session.add(new_r)
            self._session.flush()
            self._remember_new(self._researcher_cache, researcher.openalex_id, new_r.id)
            logger.debug("Inserted researcher: %r (%s)", researcher.display_name, researcher.openalex_id)
            return LifecycleAction.NEW, new_r.id
        else:
            existing.last_seen_at = now
            if _has_changed(existing, researcher, _RESEARCHER_TRACKED):
                for f in _RESEARCHER_TRACKED:
                    new_val = getattr(researcher, f, None)
                    if new_val is not None or getattr(existing, f, None) is None:
                        setattr(existing, f, new_val)
                self._session.flush()
                self._researcher_cache[researcher.openalex_id] = existing.id
                return LifecycleAction.UPDATED, existing.id
            self._session.flush()
            self._researcher_cache[researcher.openalex_id] = existing.id
            return LifecycleAction.UNCHANGED, existing.id

    # ── ResearchSource upsert ─────────────────────────────────────────────────

    def upsert_research_source(
        self,
        source: NormalizedResearchSource,
        now: datetime,
    ) -> tuple[LifecycleAction, uuid.UUID]:
        """Upsert a research source/venue.  Returns (action, db_uuid)."""
        from app.models.research_knowledge import ResearchSourceModel

        if source.openalex_id in self._source_cache:
            db_id = self._source_cache[source.openalex_id]
            stmt = select(ResearchSourceModel).where(ResearchSourceModel.id == db_id)
            existing = self._session.execute(stmt).scalar_one_or_none()
            if existing:
                existing.last_seen_at = now
                self._session.flush()
            return LifecycleAction.UNCHANGED, db_id

        stmt = select(ResearchSourceModel).where(
            ResearchSourceModel.openalex_id == source.openalex_id
        )
        existing = self._session.execute(stmt).scalar_one_or_none()

        if existing is None:
            new_s = ResearchSourceModel(
                id=uuid.uuid4(),
                openalex_id=source.openalex_id,
                display_name=source.display_name,
                source_type=source.source_type,
                issn_l=source.issn_l,
                issn=source.issn,
                is_oa=source.is_oa,
                is_in_doaj=source.is_in_doaj,
                host_organization=source.host_organization,
                works_count=source.works_count,
                cited_by_count=source.cited_by_count,
                homepage_url=source.homepage_url,
                raw_metadata=source.raw_metadata,
                last_seen_at=now,
            )
            self._session.add(new_s)
            self._session.flush()
            self._remember_new(self._source_cache, source.openalex_id, new_s.id)
            logger.debug("Inserted research_source: %r (%s)", source.display_name, source.openalex_id)
            return LifecycleAction.NEW, new_s.id
        else:
            existing.last_seen_at = now
            if _has_changed(existing, source, _SOURCE_TRACKED):
                for f in _SOURCE_TRACKED:
                    new_val = getattr(source, f, None)
                    if new_val is not None or getattr(existing, f, None) is None:
                        setattr(existing, f, new_val)
                # JSONB list field (issn) handled separately
                if source.issn is not None:
                    existing.issn = source.issn
                self._session.flush()
                self._source_cache[source.openalex_id] = existing.id
                return LifecycleAction.UPDATED, existing.id
            self._session.flush()
            self._source_cache[source.openalex_id] = existing.id
            return LifecycleAction.UNCHANGED, existing.id

    # ── Work upsert ───────────────────────────────────────────────────────────

    def upsert_work(
        self,
        work: NormalizedWork,
        ingestion_source_id: uuid.UUID,
        now: datetime,
    ) -> LifecycleAction:
        """
        Upsert a research work, including its related entities.

        Flow:
          1. Upsert primary source if present.
          2. Upsert each authoring researcher.
          3. Upsert each institution in each authorship.
          4. Upsert the work itself.
          5. Reconcile junction tables (work→authors, work→institutions).

        Returns:
            LifecycleAction for the work itself (NEW/UPDATED/UNCHANGED).
        """
        from app.models.research_knowledge import (
            ResearchWorkAuthorModel,
            ResearchWorkInstitutionModel,
            ResearchWorkModel,
        )

        # 1. Primary source
        primary_source_id: uuid.UUID | None = None
        if work.primary_source is not None:
            try:
                _, primary_source_id = self.upsert_research_source(
                    work.primary_source, now
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to upsert primary_source for work %s: %s", work.openalex_id, exc)

        # 2 & 3. Researchers and institutions from authorships
        author_links: list[tuple[uuid.UUID, str | None, bool]] = []  # (researcher_id, position, is_corresponding)
        institution_ids: set[uuid.UUID] = set()

        linked_researchers: set[uuid.UUID] = set()
        for authorship in work.authorships:
            try:
                _, researcher_id = self.upsert_researcher(authorship.researcher, now)
                # OpenAlex occasionally lists one (merged) author twice on a work; the
                # junction key is (work, researcher), so keep the first position only.
                if researcher_id not in linked_researchers:
                    linked_researchers.add(researcher_id)
                    author_links.append(
                        (researcher_id, authorship.author_position, authorship.is_corresponding)
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Skipping researcher upsert: %s", exc)

            for inst in authorship.institutions:
                try:
                    _, inst_id = self.upsert_institution(inst, now)
                    institution_ids.add(inst_id)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Skipping institution upsert: %s", exc)

        # 4. Work itself
        stmt = select(ResearchWorkModel).where(
            ResearchWorkModel.openalex_id == work.openalex_id
        )
        existing = self._session.execute(stmt).scalar_one_or_none()

        if existing is None:
            new_work = ResearchWorkModel(
                id=uuid.uuid4(),
                openalex_id=work.openalex_id,
                doi=work.doi,
                title=work.title,
                abstract=work.abstract,
                publication_year=work.publication_year,
                publication_date=work.publication_date,
                work_type=work.work_type,
                language=work.language,
                cited_by_count=work.cited_by_count,
                is_oa=work.is_oa,
                oa_status=work.oa_status,
                landing_page_url=work.landing_page_url,
                primary_source_id=primary_source_id,
                ingestion_source_id=ingestion_source_id,
                raw_metadata=work.raw_metadata,
                last_seen_at=now,
            )
            self._session.add(new_work)
            self._session.flush()
            work_db_id = new_work.id
            action = LifecycleAction.NEW
            logger.debug("Inserted work: %r (%s)", work.title[:60], work.openalex_id)
        else:
            existing.last_seen_at = now
            if _has_changed(existing, work, _WORK_TRACKED):
                for f in _WORK_TRACKED:
                    new_val = getattr(work, f, None)
                    if new_val is not None or getattr(existing, f, None) is None:
                        setattr(existing, f, new_val)
                if primary_source_id:
                    existing.primary_source_id = primary_source_id
                self._session.flush()
                action = LifecycleAction.UPDATED
            else:
                self._session.flush()
                action = LifecycleAction.UNCHANGED
            work_db_id = existing.id

        # 5a. Reconcile work→author junction (only for new works to keep upsert idempotent)
        if action == LifecycleAction.NEW:
            for researcher_id, position, is_corresponding in author_links:
                link = ResearchWorkAuthorModel(
                    work_id=work_db_id,
                    researcher_id=researcher_id,
                    author_position=position,
                    is_corresponding=is_corresponding,
                )
                self._session.add(link)

        # 5b. Reconcile work→institution junction (only for new works)
        if action == LifecycleAction.NEW:
            for inst_id in institution_ids:
                link = ResearchWorkInstitutionModel(
                    work_id=work_db_id,
                    institution_id=inst_id,
                )
                self._session.add(link)

        if action == LifecycleAction.NEW and (author_links or institution_ids):
            self._session.flush()

        return action

    # ── Page-by-page persistence ──────────────────────────────────────────────

    def start_run(self, search_query: str | None = None) -> OpenAlexPersistenceResult:
        """Create the provenance source and a RUNNING ingestion run, and commit them."""
        result = OpenAlexPersistenceResult()
        result.source_id = self.get_or_create_openalex_source()
        result.run_id = self.start_ingestion_run(result.source_id, search_query)
        self._session.commit()
        return result

    def save_page(
        self,
        works: list[NormalizedWork],
        result: OpenAlexPersistenceResult,
        now: datetime | None = None,
    ) -> None:
        """
        Persist one page of works into ``result``'s run and commit it.

        Each work is written inside its own SAVEPOINT, so a work that fails (a
        constraint, or a value its column cannot hold) is rolled back alone and counted
        in ``result.errors`` while the rest of the page is kept. Committing per page
        bounds what a crash or an interrupted load can lose to the page in flight.

        Raises:
            Exception: when the page itself cannot be committed; nothing from the page
                is kept or counted, and the caches are reset.
        """
        now = now or datetime.now(tz=timezone.utc)
        # Counted locally and merged only once the page is committed, so the run's
        # totals never include works that were rolled back with an uncommitted page.
        tally = {LifecycleAction.NEW: 0, LifecycleAction.UPDATED: 0, LifecycleAction.UNCHANGED: 0}
        failed = 0
        for work in works:
            self._uncommitted_cache_keys.clear()
            savepoint = self._session.begin_nested()
            try:
                action = self.upsert_work(work, result.source_id, now)
                savepoint.commit()
            except Exception as exc:  # noqa: BLE001
                try:
                    savepoint.rollback()
                except Exception:  # noqa: BLE001
                    # The connection itself is gone (the database stopped): report that,
                    # not the secondary "can't reconnect until rolled back" error.
                    raise exc from None
                self._forget_uncommitted_cache_keys()
                failed += 1
                if isinstance(exc, IntegrityError):
                    diag = getattr(getattr(exc, "orig", None), "diag", None)
                    logger.warning(
                        "DB constraint violation for work %r (%s) — skipping it.",
                        work.openalex_id,
                        getattr(diag, "constraint_name", None) or str(exc.orig).splitlines()[0],
                    )
                else:
                    logger.error("Unexpected error persisting work %r: %s", work.openalex_id, exc)
                continue
            self._uncommitted_cache_keys.clear()
            if action in tally:
                tally[action] += 1

        try:
            self._session.commit()
        except Exception:
            self._session.rollback()
            self._clear_caches()
            raise
        result.works_inserted += tally[LifecycleAction.NEW]
        result.works_updated += tally[LifecycleAction.UPDATED]
        result.works_unchanged += tally[LifecycleAction.UNCHANGED]
        result.errors += failed

    def discard_page(self) -> None:
        """Roll back an interrupted page and forget the ids it cached."""
        self._session.rollback()
        self._clear_caches()

    def finish_run(
        self,
        result: OpenAlexPersistenceResult,
        status: str | None = None,
        pages_fetched: int = 0,
        records_parsed: int = 0,
        records_valid: int = 0,
        records_invalid: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Record the run's final counts (COMPLETED only without errors) and commit."""
        if status is None:
            status = "COMPLETED" if result.errors == 0 and error_message is None else "FAILED"
        self.finish_ingestion_run(
            run_id=result.run_id,
            source_id=result.source_id,
            status=status,
            result=result,
            pages_fetched=pages_fetched,
            records_parsed=records_parsed,
            records_valid=records_valid,
            records_invalid=records_invalid,
            error_message=error_message,
        )
        self._session.commit()

    # ── Batch save ────────────────────────────────────────────────────────────

    def save_batch(
        self,
        works: list[NormalizedWork],
        search_query: str | None = None,
        pages_fetched: int = 0,
        records_parsed: int = 0,
        records_invalid: int = 0,
    ) -> OpenAlexPersistenceResult:
        """
        Persist a batch of normalised works (and their embedded entities) as one run.

        Idempotent: running the same batch twice produces UNCHANGED on the
        second run. A work that fails is skipped without discarding the others
        (see ``save_page``).

        Returns:
            OpenAlexPersistenceResult with per-entity-type counts.
        """
        try:
            result = self.start_run(search_query)
        except Exception as exc:  # noqa: BLE001
            self._session.rollback()
            logger.error("Batch persistence failed: %s", exc)
            result = OpenAlexPersistenceResult()
            result.errors += 1
            return result

        counts = {
            "pages_fetched": pages_fetched,
            "records_parsed": records_parsed,
            "records_valid": len(works),
            "records_invalid": records_invalid,
        }
        try:
            self.save_page(works, result)
            self.finish_run(result, **counts)
        except Exception as exc:  # noqa: BLE001
            self._session.rollback()
            logger.error("Batch persistence failed: %s", exc)
            result.errors += 1
            try:
                self.finish_run(result, status="FAILED", error_message=str(exc), **counts)
            except Exception:  # noqa: BLE001
                self._session.rollback()

        logger.info(
            "OpenAlex persistence: works(new=%d upd=%d unc=%d) errors=%d",
            result.works_inserted,
            result.works_updated,
            result.works_unchanged,
            result.errors,
        )
        return result
