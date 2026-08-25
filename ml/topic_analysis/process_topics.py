"""
Batch topic processing and taxonomy assignment pipeline.

Usage:
    # 1. Dry run on research works (shows assignments without DB writes)
    python -m ml.topic_analysis.process_topics --dry-run --limit 20

    # 2. Live processing on research works
    python -m ml.topic_analysis.process_topics --limit 100

    # 3. Process single research work by ID
    python -m ml.topic_analysis.process_topics --work-id "<UUID>" --dry-run

    # 4. Process opportunities
    python -m ml.topic_analysis.process_topics --opportunities --dry-run --limit 20
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

# Ensure project root and backend directory are on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ROOT = _PROJECT_ROOT / "backend"
for _p in (_PROJECT_ROOT, _BACKEND_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ml.topic_analysis.assignment import TopicAssigner
from ml.topic_analysis.taxonomy import TaxonomyService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ml.topic_analysis.pipeline")


def run_topic_processing(
    limit: int | None = None,
    work_id: str | None = None,
    opportunity_id: str | None = None,
    process_opportunities: bool = False,
    reprocess: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Execute batch topic assignment for research works or opportunities.

    Returns:
        Structured statistics dictionary.
    """
    stats: dict[str, Any] = {
        "mode": "opportunities" if process_opportunities else "research_works",
        "dry_run": dry_run,
        "entities_processed": 0,
        "topics_assigned": 0,
        "primary_topics_set": 0,
        "errors": 0,
    }

    from app.db.session import SessionLocal
    from app.models.opportunity import OpportunityModel, OpportunityTopicModel
    from app.models.research_knowledge import (
        ResearchWorkModel,
        ResearchWorkTopicModel,
    )
    from app.models.topic import TopicModel

    taxonomy_service = TaxonomyService()
    assigner = TopicAssigner(taxonomy_service=taxonomy_service)

    with SessionLocal() as session:
        # Step 1: Ensure seed taxonomy is synchronized in database
        if not dry_run:
            taxonomy_service.sync_to_db(session)

        # Cache DB topic slugs to UUIDs
        topic_slug_to_id: dict[str, uuid.UUID] = {}
        for t in session.execute(select(TopicModel)).scalars().all():
            topic_slug_to_id[t.slug] = t.id

        # Mode A: Process Opportunities
        if process_opportunities:
            stmt = select(OpportunityModel)
            if opportunity_id:
                try:
                    stmt = stmt.where(OpportunityModel.id == uuid.UUID(opportunity_id))
                except ValueError:
                    logger.error("Invalid opportunity UUID: %s", opportunity_id)
                    stats["errors"] += 1
                    return stats
            elif not reprocess:
                # Only process opportunities without topic associations
                stmt = stmt.outerjoin(OpportunityTopicModel).where(OpportunityTopicModel.opportunity_id == None)

            if limit:
                stmt = stmt.limit(limit)

            opportunities = session.execute(stmt).scalars().all()
            logger.info("Found %d opportunity record(s) to process.", len(opportunities))

            for opp in opportunities:
                try:
                    result = assigner.assign_opportunity(opp)
                    stats["entities_processed"] += 1

                    if dry_run:
                        logger.info("[DRY RUN] Opp [%s]: %s", opp.id, opp.title[:55])
                        for at in result.assigned_topics:
                            logger.info(
                                "  -> %s (%s) conf=%.2f primary=%s method=%s",
                                at.topic_name,
                                at.topic_slug,
                                at.confidence_score,
                                at.is_primary,
                                at.assignment_method,
                            )
                        continue

                    # Persistence: remove old associations if reprocessing
                    if reprocess:
                        del_stmt = delete(OpportunityTopicModel).where(
                            OpportunityTopicModel.opportunity_id == opp.id
                        )
                        session.execute(del_stmt)

                    # Insert new associations
                    for at in result.assigned_topics:
                        db_topic_id = topic_slug_to_id.get(at.topic_slug)
                        if not db_topic_id:
                            continue
                        assoc = OpportunityTopicModel(
                            opportunity_id=opp.id,
                            topic_id=db_topic_id,
                            confidence_score=at.confidence_score,
                            is_primary=at.is_primary,
                        )
                        session.add(assoc)
                        stats["topics_assigned"] += 1
                        if at.is_primary:
                            stats["primary_topics_set"] += 1

                    session.commit()

                except Exception as exc:
                    session.rollback()
                    logger.error("Error processing opportunity %s: %s", getattr(opp, "id", None), exc)
                    stats["errors"] += 1

        # Mode B: Process Research Works
        else:
            stmt = select(ResearchWorkModel)
            if work_id:
                try:
                    stmt = stmt.where(ResearchWorkModel.id == uuid.UUID(work_id))
                except ValueError:
                    logger.error("Invalid work UUID: %s", work_id)
                    stats["errors"] += 1
                    return stats
            elif not reprocess:
                # Only process works without topic associations
                stmt = stmt.outerjoin(ResearchWorkTopicModel).where(ResearchWorkTopicModel.work_id == None)

            if limit:
                stmt = stmt.limit(limit)

            works = session.execute(stmt).scalars().all()
            logger.info("Found %d research work record(s) to process.", len(works))

            for work in works:
                try:
                    result = assigner.assign_research_work(work)
                    stats["entities_processed"] += 1

                    if dry_run:
                        logger.info("[DRY RUN] Work [%s]: %s", work.id, work.title[:55])
                        for at in result.assigned_topics:
                            logger.info(
                                "  -> %s (%s) conf=%.2f primary=%s method=%s",
                                at.topic_name,
                                at.topic_slug,
                                at.confidence_score,
                                at.is_primary,
                                at.assignment_method,
                            )
                        continue

                    # Persistence: remove old associations if reprocessing
                    if reprocess:
                        del_stmt = delete(ResearchWorkTopicModel).where(
                            ResearchWorkTopicModel.work_id == work.id
                        )
                        session.execute(del_stmt)

                    # Insert new associations
                    for at in result.assigned_topics:
                        db_topic_id = topic_slug_to_id.get(at.topic_slug)
                        if not db_topic_id:
                            continue
                        assoc = ResearchWorkTopicModel(
                            id=uuid.uuid4(),
                            work_id=work.id,
                            topic_id=db_topic_id,
                            confidence_score=at.confidence_score,
                            is_primary=at.is_primary,
                            assignment_method=at.assignment_method,
                            source=at.source,
                        )
                        session.add(assoc)
                        stats["topics_assigned"] += 1
                        if at.is_primary:
                            stats["primary_topics_set"] += 1

                    session.commit()

                except Exception as exc:
                    session.rollback()
                    logger.error("Error processing research work %s: %s", getattr(work, "id", None), exc)
                    stats["errors"] += 1

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ResearchConnect AI — Research Topic & Taxonomy Intelligence Pipeline"
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of entities to process")
    parser.add_argument("--work-id", dest="work_id", default=None, help="Process single research work by UUID")
    parser.add_argument("--opportunity-id", dest="opportunity_id", default=None, help="Process single opportunity by UUID")
    parser.add_argument("--opportunities", action="store_true", help="Process opportunities instead of research works")
    parser.add_argument("--reprocess", action="store_true", help="Reprocess entities that already have topics assigned")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate topic assignments without writing to database")

    args = parser.parse_args()

    stats = run_topic_processing(
        limit=args.limit,
        work_id=args.work_id,
        opportunity_id=args.opportunity_id,
        process_opportunities=args.opportunities,
        reprocess=args.reprocess,
        dry_run=args.dry_run,
    )

    print("\n--- Topic Intelligence Execution Summary ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
