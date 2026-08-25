"""
Persistence and enrichment repository for Crossref research knowledge entities.

Core Architecture:
  1. DOI Identity Matching:
     - Crossref uses canonical DOI as the primary key for matching existing research_works.
     - If a matching work is found (e.g. ingested earlier via OpenAlex), it is ENRICHED non-destructively.
     - If no matching work exists, a new research_works record is created with Crossref provenance.
  2. Research Source Matching:
     - Matched primarily on ISSN (issn_l or elements of the issn list) or exact container title.
  3. Researcher Matching:
     - Matched strictly on ORCID to prevent false name-based scholarly collisions.
  4. Non-destructive Metadata Precedence:
     - Crossref authoritatively enriches publisher, volume, issue, page, article_number,
       exact publication dates, and license URLs without wiping existing OpenAlex abstracts/topics.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scrapers.crossref.models import (
    NormalizedCrossrefAuthor,
    NormalizedCrossrefSource,
    NormalizedCrossrefWork,
)
from scrapers.models import LifecycleAction

logger = logging.getLogger(__name__)


@dataclass
class CrossrefPersistenceResult:
    """Metrics collected during a Crossref ingestion / enrichment run."""
    works_inserted: int = 0
    works_enriched: int = 0
    works_unchanged: int = 0
    works_invalid: int = 0
    works_errors: int = 0

    sources_inserted: int = 0
    sources_enriched: int = 0
    sources_unchanged: int = 0

    researchers_inserted: int = 0
    researchers_matched: int = 0
    researchers_unchanged: int = 0

    potential_matches: int = 0
    errors: int = 0
    source_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None

    @property
    def total_processed(self) -> int:
        return self.works_inserted + self.works_enriched + self.works_unchanged + self.works_invalid


class CrossrefRepository:
    """
    Database persistence and enrichment manager for Crossref metadata.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._researcher_orcid_cache: dict[str, uuid.UUID] = {}
        self._source_cache: dict[str, uuid.UUID] = {}

    def get_or_create_crossref_source(self) -> uuid.UUID:
        """Find or create the 'Crossref' entry in the sources provenance table."""
        from app.models.source import SourceModel

        stmt = select(SourceModel).where(SourceModel.name == "Crossref")
        source = self._session.execute(stmt).scalar_one_or_none()

        if source is None:
            source = SourceModel(
                id=uuid.uuid4(),
                name="Crossref",
                source_type="API",
                base_url="https://api.crossref.org",
                is_active=True,
                reliability_score=1.00,
                consecutive_failure_count=0,
                total_scrape_count=0,
            )
            self._session.add(source)
            self._session.flush()
            logger.info("Created Source record for Crossref: %s", source.id)
        return source.id

    def start_ingestion_run(
        self,
        source_id: uuid.UUID,
        query: str | None = None,
    ) -> uuid.UUID:
        """Initialize a new IngestionRun record for tracking Crossref ingestion."""
        from app.models.ingestion_run import IngestionRunModel

        run = IngestionRunModel(
            id=uuid.uuid4(),
            source_id=source_id,
            status="RUNNING",
            topic=query,
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
        result: CrossrefPersistenceResult,
        pages_fetched: int = 0,
        records_parsed: int = 0,
        records_valid: int = 0,
        records_invalid: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Update IngestionRun and Source health metrics upon completion."""
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
            run.records_updated = result.works_enriched
            run.records_unchanged = result.works_unchanged
            run.duplicates_detected = result.works_enriched  # matched existing records
            run.potential_duplicates_detected = result.potential_matches
            run.records_expired = 0
            run.error_message = error_message
            run.metrics_detail = {
                "works_inserted": result.works_inserted,
                "works_enriched": result.works_enriched,
                "works_unchanged": result.works_unchanged,
                "sources_inserted": result.sources_inserted,
                "sources_enriched": result.sources_enriched,
                "researchers_inserted": result.researchers_inserted,
                "researchers_matched": result.researchers_matched,
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

    # ── Source / Venue Matching ───────────────────────────────────────────────

    def upsert_or_match_source(
        self,
        src: NormalizedCrossrefSource,
        now: datetime,
    ) -> tuple[LifecycleAction, uuid.UUID]:
        """
        Match existing research_sources by ISSN or title; insert if not found.
        """
        from app.models.research_knowledge import ResearchSourceModel

        # Check cache
        cache_key = src.issn_l or (src.issn[0] if src.issn else None) or src.title
        if cache_key and cache_key in self._source_cache:
            db_id = self._source_cache[cache_key]
            return LifecycleAction.UNCHANGED, db_id

        existing = None
        # 1. Match by ISSN if present
        if src.issn:
            for val in src.issn:
                stmt = select(ResearchSourceModel).where(
                    or_(
                        ResearchSourceModel.issn_l == val,
                        ResearchSourceModel.issn.contains([val]),
                    )
                )
                existing = self._session.execute(stmt).scalar_one_or_none()
                if existing:
                    break

        # 2. Match by exact title if not found by ISSN
        if existing is None and src.title:
            stmt = select(ResearchSourceModel).where(
                ResearchSourceModel.display_name == src.title
            )
            existing = self._session.execute(stmt).scalar_one_or_none()

        if existing is None:
            new_source = ResearchSourceModel(
                id=uuid.uuid4(),
                openalex_id=None,
                display_name=src.title,
                source_type=src.source_type,
                issn_l=src.issn_l,
                issn=src.issn,
                host_organization=src.publisher,
                is_oa=False,
                is_in_doaj=False,
                works_count=0,
                cited_by_count=0,
                last_seen_at=now,
            )
            self._session.add(new_source)
            self._session.flush()
            if cache_key:
                self._source_cache[cache_key] = new_source.id
            return LifecycleAction.NEW, new_source.id

        # Enrich existing source non-destructively
        existing.last_seen_at = now
        changed = False
        if not existing.host_organization and src.publisher:
            existing.host_organization = src.publisher
            changed = True
        if not existing.issn_l and src.issn_l:
            existing.issn_l = src.issn_l
            changed = True
        if src.issn:
            existing_issns = existing.issn or []
            combined = list(set(existing_issns + src.issn))
            if combined != existing_issns:
                existing.issn = combined
                changed = True

        self._session.flush()
        if cache_key:
            self._source_cache[cache_key] = existing.id

        return (LifecycleAction.UPDATED if changed else LifecycleAction.UNCHANGED), existing.id

    # ── Researcher Matching ───────────────────────────────────────────────────

    def upsert_or_match_researcher(
        self,
        author: NormalizedCrossrefAuthor,
        now: datetime,
    ) -> tuple[LifecycleAction, uuid.UUID]:
        """
        Match researcher by ORCID strictly. Never fuzzy-merge on name alone.
        """
        from app.models.research_knowledge import ResearcherModel

        if author.orcid and author.orcid in self._researcher_orcid_cache:
            return LifecycleAction.UNCHANGED, self._researcher_orcid_cache[author.orcid]

        existing = None
        if author.orcid:
            stmt = select(ResearcherModel).where(ResearcherModel.orcid == author.orcid)
            existing = self._session.execute(stmt).scalar_one_or_none()

        if existing is None:
            new_r = ResearcherModel(
                id=uuid.uuid4(),
                openalex_id=None,
                display_name=author.full_name,
                orcid=author.orcid,
                works_count=0,
                cited_by_count=0,
                last_seen_at=now,
            )
            self._session.add(new_r)
            self._session.flush()
            if author.orcid:
                self._researcher_orcid_cache[author.orcid] = new_r.id
            return LifecycleAction.NEW, new_r.id

        existing.last_seen_at = now
        self._session.flush()
        if author.orcid:
            self._researcher_orcid_cache[author.orcid] = existing.id
        return LifecycleAction.UNCHANGED, existing.id

    # ── Work Matching & Persistence ───────────────────────────────────────────

    def upsert_or_enrich_work(
        self,
        work: NormalizedCrossrefWork,
        ingestion_source_id: uuid.UUID,
        now: datetime,
    ) -> LifecycleAction:
        """
        Match existing research_works by DOI; enrich if found, insert if new.
        """
        from app.models.research_knowledge import (
            ResearchWorkAuthorModel,
            ResearchWorkModel,
        )

        # 1. Match primary venue/source if present
        primary_source_id: uuid.UUID | None = None
        if work.source:
            try:
                _, primary_source_id = self.upsert_or_match_source(work.source, now)
            except Exception as exc:
                logger.warning("Failed to match/upsert source for DOI %s: %s", work.doi, exc)

        # 2. Match authors
        author_links: list[tuple[uuid.UUID, str | None, bool]] = []
        for author in work.authors:
            try:
                _, r_id = self.upsert_or_match_researcher(author, now)
                author_links.append((r_id, author.sequence, False))
            except Exception as exc:
                logger.debug("Failed researcher processing: %s", exc)

        # 3. Match work by canonical DOI
        stmt = select(ResearchWorkModel).where(ResearchWorkModel.doi == work.doi)
        existing = self._session.execute(stmt).scalar_one_or_none()

        if existing is None:
            # Insert new work
            new_work = ResearchWorkModel(
                id=uuid.uuid4(),
                openalex_id=None,
                doi=work.doi,
                title=work.title,
                abstract=work.abstract,
                publication_year=work.publication_year,
                publication_date=work.publication_date,
                work_type=work.work_type,
                cited_by_count=work.cited_by_count,
                is_oa=work.is_oa,
                oa_status="gold" if work.is_oa else None,
                landing_page_url=work.url,
                volume=work.volume,
                issue=work.issue,
                page=work.page,
                article_number=work.article_number,
                license_url=work.license_url,
                primary_source_id=primary_source_id,
                ingestion_source_id=ingestion_source_id,
                raw_metadata=work.raw_metadata,
                last_seen_at=now,
            )
            self._session.add(new_work)
            self._session.flush()

            # Add author links for new work
            for researcher_id, position, is_corr in author_links:
                link = ResearchWorkAuthorModel(
                    work_id=new_work.id,
                    researcher_id=researcher_id,
                    author_position=position,
                    is_corresponding=is_corr,
                )
                self._session.add(link)
            self._session.flush()

            logger.debug("Inserted new work from Crossref: DOI %s", work.doi)
            return LifecycleAction.NEW

        # Existing record found -> NON-DESTRUCTIVE ENRICHMENT
        existing.last_seen_at = now
        changed = False

        # Enrich missing abstract if existing has none
        if not existing.abstract and work.abstract:
            existing.abstract = work.abstract
            changed = True

        # Enrich missing publication date / year
        if not existing.publication_date and work.publication_date:
            existing.publication_date = work.publication_date
            changed = True
        if not existing.publication_year and work.publication_year:
            existing.publication_year = work.publication_year
            changed = True

        # Enrich citation metadata
        if not existing.volume and work.volume:
            existing.volume = work.volume
            changed = True
        if not existing.issue and work.issue:
            existing.issue = work.issue
            changed = True
        if not existing.page and work.page:
            existing.page = work.page
            changed = True
        if not existing.article_number and work.article_number:
            existing.article_number = work.article_number
            changed = True
        if not existing.license_url and work.license_url:
            existing.license_url = work.license_url
            changed = True

        # Enrich open access if Crossref confirms it
        if not existing.is_oa and work.is_oa:
            existing.is_oa = True
            changed = True

        # Enrich primary venue if existing has none
        if not existing.primary_source_id and primary_source_id:
            existing.primary_source_id = primary_source_id
            changed = True

        # Enrich landing page URL if missing
        if not existing.landing_page_url and work.url:
            existing.landing_page_url = work.url
            changed = True

        # Merge Crossref raw metadata safely
        if work.raw_metadata and "crossref" in work.raw_metadata:
            existing_meta = dict(existing.raw_metadata or {})
            existing_meta["crossref"] = work.raw_metadata["crossref"]
            existing_meta["last_enriched_at"] = now.isoformat()
            existing.raw_metadata = existing_meta
            changed = True

        self._session.flush()
        logger.debug("Enriched existing work DOI %s (changed=%s)", work.doi, changed)
        return LifecycleAction.UPDATED if changed else LifecycleAction.UNCHANGED

    # ── Batch Ingestion ───────────────────────────────────────────────────────

    def save_batch(
        self,
        works: list[NormalizedCrossrefWork],
        query: str | None = None,
        pages_fetched: int = 0,
        records_parsed: int = 0,
        records_invalid: int = 0,
    ) -> CrossrefPersistenceResult:
        """
        Persist/enrich a batch of normalized Crossref works.
        """
        result = CrossrefPersistenceResult()
        now = datetime.now(tz=timezone.utc)

        try:
            result.source_id = self.get_or_create_crossref_source()
            result.run_id = self.start_ingestion_run(result.source_id, query)

            for work in works:
                try:
                    action = self.upsert_or_enrich_work(work, result.source_id, now)
                    if action == LifecycleAction.NEW:
                        result.works_inserted += 1
                    elif action == LifecycleAction.UPDATED:
                        result.works_enriched += 1
                    elif action == LifecycleAction.UNCHANGED:
                        result.works_unchanged += 1
                except IntegrityError:
                    self._session.rollback()
                    logger.warning("Integrity error on DOI %s — rolling back item.", work.doi)
                    result.errors += 1
                except Exception as exc:
                    self._session.rollback()
                    logger.error("Unexpected error persisting DOI %s: %s", work.doi, exc)
                    result.errors += 1

            status = "COMPLETED" if result.errors == 0 else "FAILED"
            self.finish_ingestion_run(
                run_id=result.run_id,
                source_id=result.source_id,
                status=status,
                result=result,
                pages_fetched=pages_fetched,
                records_parsed=records_parsed,
                records_valid=len(works),
                records_invalid=records_invalid,
            )
            self._session.commit()

        except Exception as exc:
            self._session.rollback()
            logger.error("Crossref batch persistence failed: %s", exc)
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
                        records_valid=len(works),
                        records_invalid=records_invalid,
                        error_message=str(exc),
                    )
                    self._session.commit()
                except Exception:
                    self._session.rollback()

        logger.info(
            "Crossref persistence summary: inserted=%d enriched=%d unchanged=%d errors=%d",
            result.works_inserted,
            result.works_enriched,
            result.works_unchanged,
            result.errors,
        )
        return result
