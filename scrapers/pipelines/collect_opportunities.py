"""
Opportunity collection pipeline.

Entry point:
    python -m scrapers.pipelines.collect_opportunities [options]

Options:
    --topic TEXT        WikiCFP search topic (default: "artificial intelligence")
    --pages INT         Number of list pages to fetch (default: 1)
    --dry-run           Parse and validate but do NOT write to the database
    --sweep-expired     Also sweep and mark past active opportunities in DB as EXPIRED

Pipeline stages:
    1. Fetch HTML pages from WikiCFP (with 5s crawl-delay between pages)
    2. Parse each page into RawOpportunity records
    3. Normalize each record (dates, types, URLs, whitespace)
    4. Validate each record (invalid records logged and dropped)
    5. Deduplicate (Tier 1/2 confirmed duplicates skipped; Tier 3 potential duplicates flagged)
    6. Persist to PostgreSQL (NEW, UPDATED, UNCHANGED, EXPIRED) + record IngestionRun metrics
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure the project root is on sys.path when running as __main__
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scrapers.deduplication.detector import DuplicateDetector
from scrapers.expiration.manager import is_opportunity_expired
from scrapers.models import DuplicateClassification, LifecycleAction
from scrapers.normalizers.opportunity_normalizer import normalize_opportunity
from scrapers.sources.wikicfp import WikiCFPSource
from scrapers.validators.opportunity_validator import validate_opportunity

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scrapers.pipeline")


def run_pipeline(
    topic: str = "artificial intelligence",
    max_pages: int = 1,
    dry_run: bool = False,
    sweep_expired: bool = False,
) -> dict:
    """
    Run the full opportunity ingestion pipeline.

    Returns:
        dict containing structured metrics.
    """
    stats = {
        "source": "WikiCFP",
        "topic": topic,
        "pages_fetched": 0,
        "parsed": 0,
        "valid": 0,
        "invalid": 0,
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "duplicates": 0,
        "potential_duplicates": 0,
        "expired": 0,
        "errors": 0,
        "run_id": None,
    }

    logger.info("=== ResearchConnect AI — Opportunity Scraper Pipeline ===")
    logger.info("Source: WikiCFP | Topic: %r | Pages: %d | Dry-run: %s", topic, max_pages, dry_run)

    detector = DuplicateDetector()

    # ── Step 1 & 2: Fetch + Parse ─────────────────────────────────────────────
    source = WikiCFPSource()
    try:
        pages = source.fetch_pages(topic=topic, max_pages=max_pages)
        stats["pages_fetched"] = len(pages)
        logger.info("Fetched %d page(s).", len(pages))

        all_raw = []
        for html, page_url in pages:
            raw_records = source.parse(html, page_url)
            all_raw.extend(raw_records)
            logger.info("Parsed %d records from %s", len(raw_records), page_url)

    finally:
        source.close()

    stats["parsed"] = len(all_raw)
    logger.info("Total parsed: %d records.", len(all_raw))

    if not all_raw:
        logger.warning("No records parsed — pipeline complete with no data.")
        return stats

    # ── Step 3 & 4: Normalize + Validate ─────────────────────────────────────
    valid_records = []
    for raw in all_raw:
        normalized = normalize_opportunity(raw)
        is_valid, errors = validate_opportunity(normalized)
        if not is_valid:
            logger.warning(
                "Rejected %r (%s): %s",
                normalized.title,
                normalized.raw_source_id,
                "; ".join(errors),
            )
            stats["invalid"] += 1
            continue
        stats["valid"] += 1
        valid_records.append(normalized)

    logger.info("Validation: %d valid, %d invalid.", stats["valid"], stats["invalid"])

    # ── Step 5: Deduplicate ───────────────────────────────────────────────────
    to_persist = []
    for opp in valid_records:
        dup_result = detector.check(opp)
        if dup_result.classification == DuplicateClassification.CONFIRMED_DUPLICATE:
            logger.debug(
                "Confirmed duplicate (tier %d): %r — %s",
                dup_result.tier,
                opp.title,
                dup_result.reason,
            )
            stats["duplicates"] += 1
        else:
            if dup_result.classification == DuplicateClassification.POTENTIAL_DUPLICATE:
                logger.info(
                    "Potential duplicate flagged: %r — %s",
                    opp.title,
                    dup_result.reason,
                )
                stats["potential_duplicates"] += 1

            detector.register(opp)
            to_persist.append(opp)

    logger.info(
        "Deduplication: %d to process, %d confirmed duplicates, %d potential duplicates.",
        len(to_persist),
        stats["duplicates"],
        stats["potential_duplicates"],
    )

    # Check expiration on parsed records
    for opp in to_persist:
        if is_opportunity_expired(opp):
            stats["expired"] += 1

    if dry_run:
        logger.info("[DRY RUN] Skipping database persistence. %d records would be persisted.", len(to_persist))
        return stats

    # ── Step 6: Persist ───────────────────────────────────────────────────────
    from app.db.session import SessionLocal
    from scrapers.expiration.manager import expire_past_opportunities
    from scrapers.persistence.opportunity_repo import OpportunityRepository

    with SessionLocal() as session:
        repo = OpportunityRepository(session)
        persistence_result = repo.save_batch(
            source_name="WikiCFP",
            source_base_url="http://www.wikicfp.com",
            opportunities=to_persist,
            topic=topic,
            pages_fetched=stats["pages_fetched"],
            records_parsed=stats["parsed"],
            records_invalid=stats["invalid"],
        )

        if sweep_expired:
            swept_count = expire_past_opportunities(session)
            logger.info("Swept %d past opportunities in DB as EXPIRED", swept_count)
            stats["expired"] += swept_count

    stats["inserted"] = persistence_result.inserted
    stats["updated"] = persistence_result.updated
    stats["unchanged"] = persistence_result.unchanged
    stats["duplicates"] += persistence_result.skipped_duplicate
    stats["potential_duplicates"] += persistence_result.potential_duplicates
    stats["errors"] = persistence_result.errors
    stats["run_id"] = str(persistence_result.run_id) if persistence_result.run_id else None

    logger.info(
        "=== Ingestion Complete: inserted=%d updated=%d unchanged=%d duplicates=%d potential_dups=%d expired=%d errors=%d ===",
        stats["inserted"],
        stats["updated"],
        stats["unchanged"],
        stats["duplicates"],
        stats["potential_duplicates"],
        stats["expired"],
        stats["errors"],
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ResearchConnect AI — WikiCFP opportunity scraper & ingestion pipeline"
    )
    parser.add_argument(
        "--topic",
        default="artificial intelligence",
        help="WikiCFP search topic (default: 'artificial intelligence')",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="Number of list pages to fetch (default: 1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate but do NOT write to the database",
    )
    parser.add_argument(
        "--sweep-expired",
        action="store_true",
        help="Perform a sweep over existing DB records to transition expired opportunities",
    )
    args = parser.parse_args()

    stats = run_pipeline(
        topic=args.topic,
        max_pages=args.pages,
        dry_run=args.dry_run,
        sweep_expired=args.sweep_expired,
    )

    print("\n--- Pipeline Execution Summary ---")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
