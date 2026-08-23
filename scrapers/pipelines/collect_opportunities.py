"""
Opportunity collection pipeline.

Entry point:
    python -m scrapers.pipelines.collect_opportunities [options]

Options:
    --topic TEXT        WikiCFP search topic (default: "artificial intelligence")
    --pages INT         Number of list pages to fetch (default: 1)
    --dry-run           Parse and validate but do NOT write to the database

This script must NOT be imported by or run from FastAPI.
It is a standalone development/operation command.

Pipeline stages:
    1. Fetch HTML pages from WikiCFP (with 5s crawl-delay between pages)
    2. Parse each page into RawOpportunity records
    3. Normalize each record
    4. Validate each record (invalid records are logged and dropped)
    5. Deduplicate (application-level, in-memory)
    6. Persist to PostgreSQL (unless --dry-run)

Logging:
    Logs: source, pages fetched, records parsed, rejected, inserted, updated,
          duplicates detected, errors.
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
) -> dict:
    """
    Run the full opportunity ingestion pipeline.

    Returns:
        dict with keys: fetched, parsed, rejected, inserted, updated, duplicates, errors
    """
    stats = {
        "source": "WikiCFP",
        "topic": topic,
        "pages_fetched": 0,
        "parsed": 0,
        "rejected": 0,
        "inserted": 0,
        "updated": 0,
        "duplicates": 0,
        "errors": 0,
    }

    logger.info("=== ResearchConnect AI — Opportunity Scraper ===")
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
            stats["rejected"] += 1
            continue
        valid_records.append(normalized)

    logger.info(
        "Validation: %d valid, %d rejected.",
        len(valid_records),
        stats["rejected"],
    )

    # ── Step 5: Deduplicate ───────────────────────────────────────────────────
    deduplicated = []
    for opp in valid_records:
        result = detector.check(opp)
        if result.is_duplicate:
            logger.debug(
                "Duplicate detected (tier %d): %r — %s",
                result.tier,
                opp.title,
                result.reason,
            )
            stats["duplicates"] += 1
        else:
            detector.register(opp)
            deduplicated.append(opp)

    logger.info(
        "Deduplication: %d unique, %d duplicates.", len(deduplicated), stats["duplicates"]
    )

    if dry_run:
        logger.info("[DRY RUN] Skipping database write. %d records would be persisted.", len(deduplicated))
        stats["inserted"] = 0
        stats["updated"] = 0
        return stats

    # ── Step 6: Persist ───────────────────────────────────────────────────────
    # Import here so that the pipeline can be imported/tested without a live DB
    from app.db.session import SessionLocal
    from scrapers.persistence.opportunity_repo import OpportunityRepository

    with SessionLocal() as session:
        repo = OpportunityRepository(session)
        persistence_result = repo.save_batch(
            source_name="WikiCFP",
            source_base_url="http://www.wikicfp.com",
            opportunities=deduplicated,
        )

    stats["inserted"] = persistence_result.inserted
    stats["updated"] = persistence_result.updated
    stats["duplicates"] += persistence_result.skipped_duplicate
    stats["errors"] = persistence_result.errors

    logger.info(
        "=== Pipeline complete: inserted=%d updated=%d duplicates=%d errors=%d ===",
        stats["inserted"],
        stats["updated"],
        stats["duplicates"],
        stats["errors"],
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ResearchConnect AI — WikiCFP opportunity scraper"
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
    args = parser.parse_args()

    stats = run_pipeline(
        topic=args.topic,
        max_pages=args.pages,
        dry_run=args.dry_run,
    )

    print("\n--- Pipeline Summary ---")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
