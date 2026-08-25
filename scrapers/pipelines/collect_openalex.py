"""
OpenAlex research knowledge ingestion pipeline.

Entry point:
    python -m scrapers.pipelines.collect_openalex [options]

Options:
    --search TEXT       Search query (default: "artificial intelligence")
    --pages INT         Number of pages to fetch (default: 1)
    --per-page INT      Works per page (default: 25, max: 200)
    --dry-run           Parse and validate but do NOT write to the database
    --year INT          Filter by publication year (optional)
    --type TEXT         Filter by work type, e.g. "article", "preprint" (optional)

Pipeline stages:
    1. Fetch raw work dicts from OpenAlex API (via OpenAlexSource)
    2. Normalise each work (normalizer.normalize_work)
    3. Validate each work (validator.validate_work)
    4. [dry-run] Report and exit without DB write
    5. [live]    Persist to PostgreSQL via OpenAlexRepository
    6. Record IngestionRun metrics

Dry-run does NOT require PostgreSQL.

Example:
    python -m scrapers.pipelines.collect_openalex \\
        --search "machine learning" \\
        --pages 2 \\
        --per-page 25 \\
        --dry-run
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

from scrapers.openalex.normalizer import normalize_work
from scrapers.openalex.validator import validate_work
from scrapers.sources.openalex import OpenAlexSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scrapers.openalex.pipeline")


def run_pipeline(
    search: str = "artificial intelligence",
    max_pages: int = 1,
    per_page: int = 25,
    dry_run: bool = False,
    year: int | None = None,
    work_type: str | None = None,
) -> dict:
    """
    Run the full OpenAlex research knowledge ingestion pipeline.

    Returns:
        dict containing structured metrics.
    """
    stats: dict = {
        "source": "OpenAlex",
        "search": search,
        "pages_fetched": 0,
        "parsed": 0,
        "valid": 0,
        "invalid": 0,
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "errors": 0,
        "run_id": None,
    }

    logger.info("=== ResearchConnect AI — OpenAlex Research Knowledge Pipeline ===")
    logger.info(
        "Search: %r | Pages: %d | Per-page: %d | Dry-run: %s | Year: %s | Type: %s",
        search,
        max_pages,
        per_page,
        dry_run,
        year or "any",
        work_type or "any",
    )

    # ── Step 1: Fetch ─────────────────────────────────────────────────────────
    source = OpenAlexSource()
    try:
        pages = source.fetch_works_pages(
            search=search,
            per_page=per_page,
            max_pages=max_pages,
            year=year,
            work_type=work_type,
        )
        stats["pages_fetched"] = len(pages)
        logger.info("Fetched %d page(s) from OpenAlex.", len(pages))

        all_raw: list[dict] = []
        for page_works in pages:
            all_raw.extend(page_works)
            logger.info("Parsed %d works from page.", len(page_works))
    finally:
        source.close()

    stats["parsed"] = len(all_raw)
    logger.info("Total raw works fetched: %d", len(all_raw))

    if not all_raw:
        logger.warning("No works returned — pipeline complete with no data.")
        return stats

    # ── Steps 2 & 3: Normalise + Validate ────────────────────────────────────
    valid_works = []
    for raw in all_raw:
        openalex_id = raw.get("id", "<unknown>")
        try:
            work = normalize_work(raw)
        except (ValueError, Exception) as exc:
            logger.warning("Normalisation failed for %r: %s", openalex_id, exc)
            stats["invalid"] += 1
            continue

        is_valid, errors = validate_work(work)
        if not is_valid:
            logger.warning(
                "Validation failed for %r (%s): %s",
                work.title[:60],
                work.openalex_id,
                "; ".join(errors),
            )
            stats["invalid"] += 1
            continue

        stats["valid"] += 1
        valid_works.append(work)

    logger.info(
        "Normalisation/Validation: %d valid, %d invalid.",
        stats["valid"],
        stats["invalid"],
    )

    # ── Step 4: Dry-run exit ──────────────────────────────────────────────────
    if dry_run:
        logger.info(
            "[DRY RUN] Skipping persistence. %d works would be persisted.",
            len(valid_works),
        )
        if valid_works:
            logger.info("Sample works:")
            for w in valid_works[:3]:
                logger.info(
                    "  [%s] %s (year=%s, type=%s, cited=%d, oa=%s)",
                    w.openalex_id,
                    w.title[:70],
                    w.publication_year,
                    w.work_type,
                    w.cited_by_count,
                    w.oa_status or "N/A",
                )
        return stats

    # ── Step 5: Persist ───────────────────────────────────────────────────────
    from app.db.session import SessionLocal
    from scrapers.persistence.openalex_repo import OpenAlexRepository

    with SessionLocal() as session:
        repo = OpenAlexRepository(session)
        persistence_result = repo.save_batch(
            works=valid_works,
            search_query=search,
            pages_fetched=stats["pages_fetched"],
            records_parsed=stats["parsed"],
            records_invalid=stats["invalid"],
        )

    stats["inserted"] = persistence_result.works_inserted
    stats["updated"] = persistence_result.works_updated
    stats["unchanged"] = persistence_result.works_unchanged
    stats["errors"] = persistence_result.errors
    stats["run_id"] = str(persistence_result.run_id) if persistence_result.run_id else None

    logger.info(
        "=== Ingestion Complete: inserted=%d updated=%d unchanged=%d errors=%d ===",
        stats["inserted"],
        stats["updated"],
        stats["unchanged"],
        stats["errors"],
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ResearchConnect AI — OpenAlex research knowledge ingestion pipeline"
    )
    parser.add_argument(
        "--search",
        default="artificial intelligence",
        help="OpenAlex full-text search query (default: 'artificial intelligence')",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="Number of pages to fetch (default: 1)",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=25,
        dest="per_page",
        help="Works per page, max 200 (default: 25)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate but do NOT write to the database",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Filter by publication year (optional)",
    )
    parser.add_argument(
        "--type",
        dest="work_type",
        default=None,
        help="Filter by work type, e.g. 'article', 'preprint' (optional)",
    )
    args = parser.parse_args()

    stats = run_pipeline(
        search=args.search,
        max_pages=args.pages,
        per_page=args.per_page,
        dry_run=args.dry_run,
        year=args.year,
        work_type=args.work_type,
    )

    print("\n--- OpenAlex Pipeline Execution Summary ---")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
