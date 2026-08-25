"""
Crossref research knowledge ingestion & enrichment pipeline.

Entry point:
    python -m scrapers.pipelines.collect_crossref [options]

Options:
    --doi TEXT          Lookup and enrich a single DOI (e.g. "10.7717/peerj.4375")
    --query TEXT        Search query for Crossref works (e.g. "machine learning")
    --pages INT         Number of pages to fetch (default: 1)
    --per-page INT      Items per page, max 100 (default: 25)
    --year INT          Filter by publication year (optional)
    --type TEXT         Filter by Crossref type, e.g. "journal-article" (optional)
    --dry-run           Parse and validate but do NOT write to the database

Examples:
    # Enrich single work in dry-run mode
    python -m scrapers.pipelines.collect_crossref --doi "10.7717/peerj.4375" --dry-run

    # Search & ingest multiple works
    python -m scrapers.pipelines.collect_crossref --query "natural language processing" --pages 2 --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

# Ensure project root and backend directory are on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ROOT = _PROJECT_ROOT / "backend"
for _path in (_PROJECT_ROOT, _BACKEND_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scrapers.crossref.doi_utils import canonicalize_doi
from scrapers.crossref.models import NormalizedCrossrefWork
from scrapers.crossref.normalizer import normalize_crossref_work
from scrapers.crossref.validator import validate_crossref_work
from scrapers.sources.crossref import CrossrefSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scrapers.crossref.pipeline")


def run_pipeline(
    doi: str | None = None,
    query: str | None = None,
    max_pages: int = 1,
    per_page: int = 25,
    year: int | None = None,
    work_type: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Execute the Crossref ingestion and enrichment pipeline.

    Returns:
        Structured statistics dictionary.
    """
    stats: dict[str, Any] = {
        "source": "Crossref",
        "doi": doi,
        "query": query,
        "pages_fetched": 0,
        "parsed": 0,
        "valid": 0,
        "invalid": 0,
        "inserted": 0,
        "enriched": 0,
        "unchanged": 0,
        "errors": 0,
        "run_id": None,
    }

    logger.info("=== ResearchConnect AI — Crossref Research Knowledge Pipeline ===")
    logger.info(
        "DOI: %s | Query: %r | Pages: %d | Per-page: %d | Dry-run: %s",
        doi or "none",
        query or "none",
        max_pages,
        per_page,
        dry_run,
    )

    all_raw: list[dict[str, Any]] = []
    source = CrossrefSource()

    try:
        # Mode 1: Single DOI lookup
        if doi:
            canonical_doi = canonicalize_doi(doi)
            if not canonical_doi:
                logger.error("Invalid DOI specified: %r", doi)
                stats["invalid"] += 1
                return stats

            logger.info("Fetching single DOI from Crossref: %s", canonical_doi)
            raw_work = source.fetch_work_by_doi(canonical_doi)
            if raw_work:
                all_raw.append(raw_work)
                stats["pages_fetched"] = 1
            else:
                logger.warning("Crossref returned no data for DOI %s", canonical_doi)

        # Mode 2: Query-based batch retrieval
        elif query:
            pages = source.fetch_works_pages(
                query=query,
                per_page=per_page,
                max_pages=max_pages,
                filter_type=work_type,
                year=year,
            )
            stats["pages_fetched"] = len(pages)
            for page in pages:
                all_raw.extend(page)
        else:
            logger.error("Neither --doi nor --query was provided.")
            return stats

    finally:
        source.close()

    stats["parsed"] = len(all_raw)
    logger.info("Fetched %d raw work(s) from Crossref.", len(all_raw))

    if not all_raw:
        logger.warning("No works retrieved — pipeline finishing.")
        return stats

    # ── Normalize & Validate ──────────────────────────────────────────────────
    valid_works: list[NormalizedCrossrefWork] = []
    for raw in all_raw:
        raw_doi = raw.get("DOI", "<unknown>")
        try:
            work = normalize_crossref_work(raw)
        except Exception as exc:
            logger.warning("Normalization failed for DOI %s: %s", raw_doi, exc)
            stats["invalid"] += 1
            continue

        is_valid, errors = validate_crossref_work(work)
        if not is_valid:
            logger.warning("Validation failed for DOI %s: %s", work.doi, "; ".join(errors))
            stats["invalid"] += 1
            continue

        stats["valid"] += 1
        valid_works.append(work)

    logger.info(
        "Normalization & Validation: %d valid, %d invalid.",
        stats["valid"],
        stats["invalid"],
    )

    # ── Dry-run mode ──────────────────────────────────────────────────────────
    if dry_run:
        logger.info(
            "[DRY RUN] Skipping database write. %d valid work(s) prepared.",
            len(valid_works),
        )
        for w in valid_works[:5]:
            logger.info(
                "  [DOI: %s] %s (year=%s, publisher=%s, is_oa=%s)",
                w.doi,
                w.title[:65],
                w.publication_year,
                w.source.publisher if w.source else "N/A",
                w.is_oa,
            )
        return stats

    # ── Live Persistence & Matching ───────────────────────────────────────────
    from app.db.session import SessionLocal
    from scrapers.persistence.crossref_repo import CrossrefRepository

    with SessionLocal() as session:
        repo = CrossrefRepository(session)
        persistence_result = repo.save_batch(
            works=valid_works,
            query=doi or query,
            pages_fetched=stats["pages_fetched"],
            records_parsed=stats["parsed"],
            records_invalid=stats["invalid"],
        )

    stats["inserted"] = persistence_result.works_inserted
    stats["enriched"] = persistence_result.works_enriched
    stats["unchanged"] = persistence_result.works_unchanged
    stats["errors"] = persistence_result.errors
    stats["run_id"] = str(persistence_result.run_id) if persistence_result.run_id else None

    logger.info(
        "=== Crossref Ingestion Complete: inserted=%d enriched=%d unchanged=%d errors=%d ===",
        stats["inserted"],
        stats["enriched"],
        stats["unchanged"],
        stats["errors"],
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ResearchConnect AI — Crossref research knowledge ingestion & enrichment pipeline"
    )
    parser.add_argument("--doi", help="Lookup and enrich a single DOI (e.g. '10.7717/peerj.4375')")
    parser.add_argument("--query", help="Free-text search query (e.g. 'machine learning')")
    parser.add_argument("--pages", type=int, default=1, help="Number of pages to fetch (default: 1)")
    parser.add_argument("--per-page", type=int, default=25, dest="per_page", help="Results per page, max 100 (default: 25)")
    parser.add_argument("--year", type=int, default=None, help="Filter by publication year (optional)")
    parser.add_argument("--type", dest="work_type", default=None, help="Filter by Crossref type (optional)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate without writing to database")

    args = parser.parse_args()

    if not args.doi and not args.query:
        parser.error("Must provide either --doi or --query")

    stats = run_pipeline(
        doi=args.doi,
        query=args.query,
        max_pages=args.pages,
        per_page=args.per_page,
        year=args.year,
        work_type=args.work_type,
        dry_run=args.dry_run,
    )

    print("\n--- Crossref Pipeline Execution Summary ---")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
