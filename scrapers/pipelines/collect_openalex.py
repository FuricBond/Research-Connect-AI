"""
OpenAlex research knowledge ingestion pipeline.

Entry point:
    python -m scrapers.pipelines.collect_openalex [options]

Options:
    --search TEXT       Search query (default: "artificial intelligence" unless --subfield is given)
    --subfield ID       Only works whose primary topic is in this OpenAlex subfield, e.g. 1702
    --has-abstract      Only works that have an abstract
    --from-year INT     Only works published in or after this year
    --to-year INT       Only works published in or before this year
    --year INT          Filter by a single publication year (optional)
    --type TEXT         Filter by work type, e.g. "article", "preprint" (optional)
    --sort TEXT         Result order, e.g. "cited_by_count:desc" (optional)
    --pages INT         Number of pages to fetch (default: 1)
    --per-page INT      Works per page (default: 25, max: 200)
    --cursor TEXT       Resume a previous load from the cursor it printed
    --dry-run           Parse and validate but do NOT write to the database

Pipeline stages, repeated for every page:
    1. Fetch one page of raw work dicts from the OpenAlex API (via OpenAlexSource)
    2. Normalise each work (normalizer.normalize_work)
    3. Validate each work (validator.validate_work)
    4. [dry-run] Count and move on without DB writes
    5. [live]    Persist the page to PostgreSQL and commit it (OpenAlexRepository.save_page)
The run is recorded as one IngestionRun with the totals.

Bulk loads: pages are saved as they arrive, so memory stays flat and a stopped load keeps
everything saved so far. When the load stops early (the daily OpenAlex budget is spent, or a
request fails), the summary prints the cursor to pass to --cursor to continue. Selecting works
with --subfield instead of --search costs a tenth of the budget per page. Set OPENALEX_API_KEY
(a free OpenAlex account key) for ten times the keyless daily budget.

Dry-run does NOT require PostgreSQL.

Examples:
    python -m scrapers.pipelines.collect_openalex \\
        --search "machine learning" --pages 2 --per-page 25 --dry-run

    python -m scrapers.pipelines.collect_openalex \\
        --subfield 1702 --has-abstract --from-year 2015 \\
        --sort cited_by_count:desc --pages 50 --per-page 200
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path

# Ensure the project root and backend directory are on sys.path when running as __main__
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ROOT = _PROJECT_ROOT / "backend"
for _path in (_PROJECT_ROOT, _BACKEND_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scrapers.openalex.client import OpenAlexBudgetExhaustedError, works_filter
from scrapers.openalex.normalizer import normalize_work
from scrapers.openalex.validator import validate_work
from scrapers.sources.openalex import OpenAlexSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scrapers.openalex.pipeline")

DEFAULT_SEARCH = "artificial intelligence"


def _open_repository():
    """Open a session and repository. Imported lazily: a dry run needs no database."""
    from app.db.session import SessionLocal
    from scrapers.persistence.openalex_repo import OpenAlexRepository

    session = SessionLocal()
    return session, OpenAlexRepository(session)


def _normalise_and_validate(raw_works: list[dict], stats: dict) -> list:
    """Normalise and validate one page, counting valid and invalid works in ``stats``."""
    valid_works = []
    for raw in raw_works:
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
    return valid_works


def run_pipeline(
    search: str | None = None,
    max_pages: int = 1,
    per_page: int = 25,
    dry_run: bool = False,
    year: int | None = None,
    work_type: str | None = None,
    subfield: str | None = None,
    has_abstract: bool = False,
    from_year: int | None = None,
    to_year: int | None = None,
    sort: str | None = None,
    cursor: str = "*",
) -> dict:
    """
    Run the OpenAlex research knowledge ingestion pipeline, one page at a time.

    Returns:
        dict containing structured metrics. ``next_cursor`` is where a further load
        continues (None once every matching work was fetched); ``stopped_reason`` is set
        when the load ended early.
    """
    if search is None and subfield is None:
        search = DEFAULT_SEARCH
    filters = works_filter(
        year=year,
        work_type=work_type,
        from_year=from_year,
        to_year=to_year,
        subfield_id=subfield,
        has_abstract=has_abstract,
    )

    stats: dict = {
        "source": "OpenAlex",
        "search": search,
        "filter": ",".join(filters) or None,
        "pages_fetched": 0,
        "parsed": 0,
        "valid": 0,
        "invalid": 0,
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "errors": 0,
        "run_id": None,
        "next_cursor": None,
        "stopped_reason": None,
    }

    logger.info("=== ResearchConnect AI — OpenAlex Research Knowledge Pipeline ===")
    logger.info(
        "Search: %r | Filter: %s | Sort: %s | Pages: %d | Per-page: %d | Dry-run: %s | Resume: %s",
        search,
        stats["filter"] or "none",
        sort or "default",
        max_pages,
        per_page,
        dry_run,
        "yes" if cursor != "*" else "no",
    )

    session = repo = result = None
    if not dry_run:
        # Fails here, before any API call spends budget, when the database is unreachable.
        session, repo = _open_repository()
        try:
            run_label = search or f"filter:{stats['filter']}"
            result = repo.start_run(run_label[:255])
        except Exception:
            session.close()
            raise
        stats["run_id"] = str(result.run_id)

    source = OpenAlexSource()
    samples: list = []
    resume_cursor: str | None = cursor
    pages_done = 0
    try:
        for page in source.iter_work_pages(
            search=search,
            filters=filters,
            sort=sort,
            per_page=per_page,
            max_pages=max_pages,
            start_cursor=cursor,
        ):
            stats["pages_fetched"] += 1
            stats["parsed"] += len(page.results)
            valid_works = _normalise_and_validate(page.results, stats)

            if dry_run:
                samples.extend(valid_works[: max(0, 3 - len(samples))])
            else:
                repo.save_page(valid_works, result)
                stats["inserted"] = result.works_inserted
                stats["updated"] = result.works_updated
                stats["unchanged"] = result.works_unchanged
                stats["errors"] = result.errors

            # Only a saved page moves the resume point past it.
            resume_cursor = page.next_cursor
            pages_done += 1
            planned = max_pages
            if page.total_count is not None:
                planned = min(max_pages, math.ceil(page.total_count / max(1, per_page)))
            logger.info(
                "Page %d/%d: %d works, %d valid so far | inserted=%d updated=%d unchanged=%d errors=%d",
                stats["pages_fetched"],
                planned,
                len(page.results),
                stats["valid"],
                stats["inserted"],
                stats["updated"],
                stats["unchanged"],
                stats["errors"],
            )
    except OpenAlexBudgetExhaustedError as exc:
        stats["stopped_reason"] = str(exc)
        logger.error("Stopping: %s", exc)
    except KeyboardInterrupt:
        # Ctrl+C: drop the page in flight (it was not committed), keep every saved page.
        stats["stopped_reason"] = "interrupted"
        logger.warning("Interrupted after %d complete page(s).", pages_done)
        if repo is not None:
            repo.discard_page()
    except Exception as exc:  # noqa: BLE001
        stats["stopped_reason"] = f"stopped on an error: {exc}"
        logger.error("Stopping after %d complete page(s): %s", pages_done, exc)
    finally:
        source.close()
        if repo is not None:
            try:
                repo.finish_run(
                    result,
                    pages_fetched=stats["pages_fetched"],
                    records_parsed=stats["parsed"],
                    records_valid=stats["valid"],
                    records_invalid=stats["invalid"],
                    error_message=stats["stopped_reason"],
                )
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                logger.error("Could not record the run's final counts: %s", exc)
            session.close()

    stats["next_cursor"] = resume_cursor
    if stats["stopped_reason"] and resume_cursor:
        logger.warning("Continue this load later with: --cursor %s", resume_cursor)

    if dry_run:
        logger.info(
            "[DRY RUN] Skipping persistence. %d works would be persisted.",
            stats["valid"],
        )
        if samples:
            logger.info("Sample works:")
            for w in samples:
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
        default=None,
        help=f"OpenAlex full-text search query (default: {DEFAULT_SEARCH!r} unless --subfield is given)",
    )
    parser.add_argument(
        "--subfield",
        default=None,
        help="Only works whose primary topic is in this OpenAlex subfield ID, e.g. 1702",
    )
    parser.add_argument(
        "--has-abstract",
        action="store_true",
        dest="has_abstract",
        help="Only works that have an abstract",
    )
    parser.add_argument(
        "--from-year",
        type=int,
        default=None,
        dest="from_year",
        help="Only works published in or after this year",
    )
    parser.add_argument(
        "--to-year",
        type=int,
        default=None,
        dest="to_year",
        help="Only works published in or before this year",
    )
    parser.add_argument(
        "--sort",
        default=None,
        help="Result order, e.g. 'cited_by_count:desc'",
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
        "--cursor",
        default="*",
        help="Resume a previous load from the cursor it printed",
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

    try:
        stats = run_pipeline(
            search=args.search,
            max_pages=args.pages,
            per_page=args.per_page,
            dry_run=args.dry_run,
            year=args.year,
            work_type=args.work_type,
            subfield=args.subfield,
            has_abstract=args.has_abstract,
            from_year=args.from_year,
            to_year=args.to_year,
            sort=args.sort,
            cursor=args.cursor,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Pipeline failed before loading anything: %s", exc)
        sys.exit(1)

    print("\n--- OpenAlex Pipeline Execution Summary ---")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
