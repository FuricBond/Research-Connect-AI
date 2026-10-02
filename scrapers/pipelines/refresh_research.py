"""
Research refresh — newly published and rising OpenAlex works, kept current on a schedule.

Entry points:
    run_refresh(...)    called by the scheduled ``research_refresh`` job (app.scheduler.jobs),
                        which already holds the research load lock
    python -m scrapers.pipelines.refresh_research [options]
                        the same refresh by hand, under the same lock

One refresh, for each configured OpenAlex subfield in order, runs two passes, each one
``collect_openalex.run_pipeline`` call that selects works with filters only (a keyword
search costs ten times as much):

    newest   works published in the last ``new_window_days``, newest first,
             ``new_pages`` pages; skipped at the corpus cap
    rising   works published in the last ``rising_window_days``, most cited first,
             ``rising_pages`` pages; at the corpus cap it only updates works it already has

Both lanes ask for works with an abstract and 200 per page, and label their ingestion run
``research_refresh:{run_tag}:{lane}:{subfield}``. A page count of 0 switches a lane off.

Outcomes:
    - A pass that ends without a stopped reason is completed.
    - A spent daily budget ends the whole refresh: that pass and every pass still to come
      count as failed (retrying cannot help until the budget resets at midnight UTC).
    - Any other early stop (a request failure) fails that pass only; the next one runs.
    - A stop request (``should_stop``) ends the refresh at a page boundary and is not a
      failure. Every saved page is kept either way.

After the passes, unless a stop was requested, untagged works get topics and works with no
embedding (or one from another model) get embeddings, through the process-wide embedding
service, so new works are searchable by meaning in the same run.

The summary holds counts and fixed reason codes only, never exception text, so neither a
request URL nor the API key in it can reach the job details, the logs or the database.

Run the CLI from backend/, like the other loaders, so the settings read backend/.env:
    cd backend
    PYTHONPATH=.. python -m scrapers.pipelines.refresh_research --subfields 1702

CLI options (defaults from the application settings):
    --subfields IDS          Comma-separated OpenAlex subfield ids, e.g. 1702,1707
    --new-pages N            Pages per newest pass (0 switches the lane off)
    --rising-pages N         Pages per rising pass (0 switches the lane off)
    --new-window-days N      How many days back the newest lane looks
    --rising-window-days N   How many days back the rising lane looks
    --max-works N            Corpus cap: no new works once research_works holds this many

Exit codes: 0 when every pass that ran completed, 1 when a pass failed or the refresh could
not start, 3 when another research load or the scheduled job holds the research load lock.

Everything heavy is imported inside the functions: importing this module configures no
logging, changes no import path and touches neither the network nor the database.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta, timezone
import logging
import uuid

logger = logging.getLogger("scrapers.research_refresh")

LANE_NEWEST = "newest"
LANE_RISING = "rising"

# The only values stopped_reason takes: fixed codes, never exception text.
STOP_REQUESTED = "stop requested"
BUDGET_EXHAUSTED = "budget exhausted"
REQUEST_FAILED = "request failed"

PER_PAGE = 200  # the OpenAlex maximum: fewer requests for the same works
EMBEDDING_BATCH_SIZE = 32
EXIT_LOCK_BUSY = 3

# Counters summed over the passes, straight from collect_openalex.run_pipeline.
_PASS_COUNTERS = (
    "pages_fetched",
    "parsed",
    "valid",
    "invalid",
    "inserted",
    "updated",
    "unchanged",
    "errors",
    "skipped_new",
)


def _corpus_size() -> int:
    """How many research works the database holds."""
    from sqlalchemy import func, select

    from app.db.session import SessionLocal
    from app.models.research_knowledge import ResearchWorkModel

    with SessionLocal() as session:
        return int(session.execute(select(func.count()).select_from(ResearchWorkModel)).scalar_one())


def _planned_passes(subfields: Sequence[str], new_pages: int, rising_pages: int) -> list[tuple[str, str]]:
    """(lane, subfield) in run order; a lane with 0 pages is never planned."""
    passes: list[tuple[str, str]] = []
    for subfield in subfields:
        if new_pages > 0:
            passes.append((LANE_NEWEST, subfield))
        if rising_pages > 0:
            passes.append((LANE_RISING, subfield))
    return passes


def run_refresh(
    *,
    subfields: Sequence[str],
    new_pages: int,
    rising_pages: int,
    new_window_days: int,
    rising_window_days: int,
    max_works: int,
    api_key: str | None = None,
    email: str | None = None,
    should_stop: Callable[[], bool] | None = None,
    run_tag: str | None = None,
    today: date | None = None,
) -> dict:
    """
    Run one research refresh and return its summary (see the module docstring).

    Raises only when the refresh cannot start, before any request is made: for example
    when the database is unreachable. It does not take the research load lock; the
    scheduler, or ``main``, already holds it.
    """
    from scrapers.pipelines import collect_openalex

    today = today or datetime.now(timezone.utc).date()
    run_tag = run_tag or uuid.uuid4().hex
    subfields = tuple(subfields)
    stopping = should_stop or (lambda: False)

    stats: dict = {
        "subfields": list(subfields),
        "passes_completed": 0,
        "passes_failed": 0,
        **{counter: 0 for counter in _PASS_COUNTERS},
        "budget_exhausted": False,
        "stopped_reason": None,
        "corpus_size": None,
        "inserts_allowed": None,
        "topics_processed": 0,
        "embedded": 0,
        "run_ids": [],
        "run_tag": run_tag,
    }

    lanes = {
        LANE_NEWEST: dict(
            from_date=today - timedelta(days=new_window_days),
            sort="publication_date:desc",
            max_pages=new_pages,
        ),
        LANE_RISING: dict(
            from_date=today - timedelta(days=rising_window_days),
            sort="cited_by_count:desc",
            max_pages=rising_pages,
        ),
    }

    logger.info(
        "Research refresh %s: subfields=%s newest=%d page(s)/%d d rising=%d page(s)/%d d cap=%d",
        run_tag,
        ",".join(subfields),
        new_pages,
        new_window_days,
        rising_pages,
        rising_window_days,
        max_works,
    )

    planned = _planned_passes(subfields, new_pages, rising_pages)
    started = False  # True once a pass has reached OpenAlex; before that, failures raise
    for index, (lane, subfield) in enumerate(planned):
        if stopping():
            stats["stopped_reason"] = STOP_REQUESTED
            break

        # Before each pass: inserts stop once the corpus reaches the cap. Before the first
        # request, a database that cannot be counted is a setup failure and raises.
        try:
            stats["corpus_size"] = _corpus_size()
        except Exception as exc:  # noqa: BLE001
            if not started:
                raise
            logger.error("Research refresh %s: could not count the corpus (%s)", run_tag, type(exc).__name__)
            stats["passes_failed"] += 1
            stats["stopped_reason"] = REQUEST_FAILED
            continue
        stats["inserts_allowed"] = stats["corpus_size"] < max_works
        if lane == LANE_NEWEST and not stats["inserts_allowed"]:
            logger.info(
                "Research refresh %s: corpus at the cap (%d of %d); skipping newest for %s",
                run_tag,
                stats["corpus_size"],
                max_works,
                subfield,
            )
            continue

        options = lanes[lane]
        try:
            result = collect_openalex.run_pipeline(
                subfield=subfield,
                has_abstract=True,
                per_page=PER_PAGE,
                max_pages=options["max_pages"],
                sort=options["sort"],
                from_date=options["from_date"],
                to_date=today,
                api_key=api_key,
                email=email,
                should_stop=stopping,
                run_label=f"research_refresh:{run_tag}:{lane}:{subfield}",
                update_only=lane == LANE_RISING and not stats["inserts_allowed"],
            )
        except Exception as exc:  # noqa: BLE001
            # run_pipeline raises only when it cannot start (database, run record).
            if not started:
                raise
            logger.error("Research refresh %s: %s pass for %s could not start (%s)", run_tag, lane, subfield, type(exc).__name__)
            stats["passes_failed"] += 1
            stats["stopped_reason"] = REQUEST_FAILED
            continue
        started = True

        for counter in _PASS_COUNTERS:
            stats[counter] += int(result.get(counter) or 0)
        if result.get("run_id"):
            stats["run_ids"].append(result["run_id"])

        reason = result.get("stopped_reason")
        if reason is None:
            stats["passes_completed"] += 1
        elif reason == collect_openalex.STOP_REQUESTED:
            stats["stopped_reason"] = STOP_REQUESTED
            break
        elif result.get("budget_exhausted"):
            remaining = [
                p
                for p in planned[index + 1 :]
                if p[0] == LANE_RISING or stats["inserts_allowed"]
            ]
            stats["passes_failed"] += 1 + len(remaining)
            stats["budget_exhausted"] = True
            stats["stopped_reason"] = BUDGET_EXHAUSTED
            logger.warning(
                "Research refresh %s: the OpenAlex daily budget is spent; %d pass(es) not run",
                run_tag,
                len(remaining),
            )
            break
        else:
            stats["passes_failed"] += 1
            stats["stopped_reason"] = REQUEST_FAILED
            logger.warning("Research refresh %s: %s pass for %s stopped early", run_tag, lane, subfield)

    if stats["stopped_reason"] != STOP_REQUESTED and stopping():
        stats["stopped_reason"] = STOP_REQUESTED
    if stats["stopped_reason"] != STOP_REQUESTED:
        _tag_and_embed(stats, run_tag, stopping)

    logger.info(
        "Research refresh %s finished: passes completed=%d failed=%d inserted=%d updated=%d "
        "topics=%d embedded=%d stopped=%s",
        run_tag,
        stats["passes_completed"],
        stats["passes_failed"],
        stats["inserted"],
        stats["updated"],
        stats["topics_processed"],
        stats["embedded"],
        stats["stopped_reason"] or "no",
    )
    return stats


def _tag_and_embed(stats: dict, run_tag: str, stopping: Callable[[], bool]) -> None:
    """Topics for untagged works, then embeddings for pending ones; failures are counted."""
    from ml.embeddings import generate_embeddings
    from ml.embeddings.service import get_embedding_service
    from ml.topic_analysis.process_topics import run_topic_processing

    try:
        topic_stats = run_topic_processing()
        stats["topics_processed"] = int(topic_stats.get("entities_processed") or 0)
        stats["errors"] += int(topic_stats.get("errors") or 0)
    except Exception as exc:  # noqa: BLE001
        stats["errors"] += 1
        logger.error("Research refresh %s: topic processing failed (%s)", run_tag, type(exc).__name__)

    if stopping():
        stats["stopped_reason"] = STOP_REQUESTED
        return

    try:
        svc = get_embedding_service()
        embed_stats = generate_embeddings.run_pipeline(
            entity="research_work",
            model_name=svc.model_name,
            batch_size=EMBEDDING_BATCH_SIZE,
            limit=None,
            dry_run=False,
            force=False,
            device=svc.device,
            pending_only=True,
            embedding_service=svc,
        )
        stats["embedded"] = int(embed_stats.embedded)
        stats["errors"] += int(embed_stats.failed)
    except Exception as exc:  # noqa: BLE001
        stats["errors"] += 1
        logger.error("Research refresh %s: embedding failed (%s)", run_tag, type(exc).__name__)


# ── CLI ───────────────────────────────────────────────────────────────────────


def _acquire_research_lock():
    from scrapers.pipelines.load_lock import acquire_research_lock

    return acquire_research_lock()


def _ensure_import_paths() -> None:
    """Let ``python -m`` from the repository root import the backend's ``app`` package."""
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for path in (root, root / "backend"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def main(argv: list[str] | None = None) -> int:
    _ensure_import_paths()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    from app.core.config import parse_subfield_ids, settings

    def subfield_ids(text: str) -> tuple[str, ...]:
        try:
            ids = parse_subfield_ids(text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from exc
        if not ids:
            raise argparse.ArgumentTypeError("give at least one subfield id, e.g. 1702")
        return ids

    parser = argparse.ArgumentParser(
        prog="python -m scrapers.pipelines.refresh_research",
        description="ResearchConnect AI — refresh newly published and rising OpenAlex works",
    )
    parser.add_argument("--subfields", type=subfield_ids, default=settings.research_refresh_subfield_ids,
                        help="Comma-separated OpenAlex subfield ids (default: RESEARCH_REFRESH_SUBFIELDS)")
    parser.add_argument("--new-pages", type=int, default=settings.research_refresh_new_pages,
                        help="Pages per newest pass; 0 switches the lane off")
    parser.add_argument("--rising-pages", type=int, default=settings.research_refresh_rising_pages,
                        help="Pages per rising pass; 0 switches the lane off")
    parser.add_argument("--new-window-days", type=int, default=settings.research_refresh_new_window_days,
                        help="How many days back the newest lane looks")
    parser.add_argument("--rising-window-days", type=int, default=settings.research_refresh_rising_window_days,
                        help="How many days back the rising lane looks")
    parser.add_argument("--max-works", type=int, default=settings.research_refresh_max_works,
                        help="Corpus cap: no new works once research_works holds this many")
    args = parser.parse_args(argv)

    try:
        lock = _acquire_research_lock()
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not take the research load lock (%s)", type(exc).__name__)
        return 1
    if lock is None:
        logger.error(
            "Another research load or the scheduled research_refresh job is running; "
            "try again when it has finished."
        )
        return EXIT_LOCK_BUSY

    try:
        stats = run_refresh(
            subfields=args.subfields,
            new_pages=args.new_pages,
            rising_pages=args.rising_pages,
            new_window_days=args.new_window_days,
            rising_window_days=args.rising_window_days,
            max_works=args.max_works,
            api_key=settings.openalex_api_key or None,
            email=settings.openalex_email or None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Research refresh could not start (%s)", type(exc).__name__)
        return 1
    finally:
        lock.release()

    print("\n--- Research Refresh Summary ---")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    return 0 if stats["passes_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
