"""
Phase 2.3B — Semantic Embedding Generation Pipeline.

CLI entry point for batch-embedding ``ResearchWorkModel`` and
``OpportunityModel`` records using a SentenceTransformer model.

Usage
-----
    # Embed all research works (skip up-to-date records)
    python -m ml.embeddings.generate_embeddings --entity research_work

    # Embed all opportunities
    python -m ml.embeddings.generate_embeddings --entity opportunity

    # Dry-run: print what would be embedded without writing to DB
    python -m ml.embeddings.generate_embeddings --entity research_work --dry-run

    # Force re-embed everything (ignore existing hashes)
    python -m ml.embeddings.generate_embeddings --entity research_work --force

    # Limit rows and batch size
    python -m ml.embeddings.generate_embeddings \\
        --entity research_work \\
        --batch-size 16 \\
        --limit 100

Options
-------
--entity        research_work | opportunity  (required)
--model         HuggingFace model name (default: all-MiniLM-L6-v2)
--batch-size    Records per encoding batch (default: 32)
--limit         Maximum number of records to process (default: all)
--dry-run       Print stats without writing to the database
--force         Re-embed even if content hash matches
--device        PyTorch device: cpu | cuda | mps (default: cpu)
"""
from __future__ import annotations

import argparse
import logging
import sys
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Logging setup — configured before any project imports so early warnings show
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("embeddings.pipeline")

# ---------------------------------------------------------------------------
# Backend imports — must be available at test time for patching to work.
# Add backend/ to sys.path if needed (project-root invocation).
# ---------------------------------------------------------------------------
_backend_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

try:
    from app.db.session import SessionLocal  # noqa: E402
except ImportError:
    SessionLocal = None  # type: ignore[assignment,misc]

from ml.embeddings.service import EmbeddingService  # noqa: E402


@dataclass
class PipelineStats:
    """Counters accumulated during a pipeline run."""

    total: int = 0
    skipped: int = 0  # hash matched, no change needed
    embedded: int = 0  # newly embedded or re-embedded
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = [
            "── Embedding Pipeline Result ──────────────────────",
            f"  total processed : {self.total}",
            f"  embedded (new)  : {self.embedded}",
            f"  skipped (same)  : {self.skipped}",
            f"  failed          : {self.failed}",
        ]
        if self.errors:
            lines.append("  errors:")
            for err in self.errors[:10]:
                lines.append(f"    • {err}")
            if len(self.errors) > 10:
                lines.append(f"    … and {len(self.errors) - 10} more")
        lines.append("────────────────────────────────────────────────────")
        return "\n".join(lines)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m ml.embeddings.generate_embeddings",
        description="Phase 2.3B: Batch-generate semantic embeddings for research entities.",
    )
    parser.add_argument(
        "--entity",
        required=True,
        choices=["research_work", "opportunity"],
        help="Entity type to embed.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="HuggingFace model name (default: from EMBEDDING_MODEL env / all-MiniLM-L6-v2).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Number of records per encoding batch (default: 32).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of records to process.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be embedded without writing to the database.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed even if content hash matches.",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="PyTorch device: cpu | cuda | mps (default: cpu).",
    )
    return parser.parse_args(argv)


def _build_research_work_text_safe(work: Any) -> str | None:
    """Return semantic text for a work, or None on failure."""
    from ml.embeddings.text_builder import build_research_work_text

    try:
        return build_research_work_text(work)
    except ValueError as exc:
        logger.debug("Skipping work %s: %s", getattr(work, "id", "?"), exc)
        return None


def _build_opportunity_text_safe(opp: Any) -> str | None:
    """Return semantic text for an opportunity, or None on failure."""
    from ml.embeddings.text_builder import build_opportunity_text

    try:
        return build_opportunity_text(opp)
    except ValueError as exc:
        logger.debug("Skipping opportunity %s: %s", getattr(opp, "id", "?"), exc)
        return None


def run_pipeline(
    entity: str,
    model_name: str,
    batch_size: int,
    limit: int | None,
    dry_run: bool,
    force: bool,
    device: str,
) -> PipelineStats:
    """
    Core pipeline logic.

    Parameters
    ----------
    entity:     ``"research_work"`` or ``"opportunity"``
    model_name: HuggingFace model identifier
    batch_size: Records per encoding batch
    limit:      Maximum records to process (None = all)
    dry_run:    When True, skip DB writes
    force:      When True, re-embed even if hash matches
    device:     PyTorch device string

    Returns
    -------
    PipelineStats
    """
    from ml.embeddings.hash_utils import compute_content_hash, needs_reembedding
    from ml.embeddings.service import EmbeddingService

    stats = PipelineStats()

    # --- database setup -------------------------------------------------------
    if SessionLocal is None:
        raise ImportError(
            "Cannot import SessionLocal from app.db.session. "
            "Ensure the 'backend/' directory is on sys.path."
        )

    # Choose entity-specific items
    if entity == "research_work":
        from app.models.research_knowledge import ResearchWorkModel as ModelClass
        text_fn: Callable[[Any], str | None] = _build_research_work_text_safe
    else:
        from app.models.opportunity import OpportunityModel as ModelClass  # type: ignore[assignment]
        text_fn = _build_opportunity_text_safe

    # --- load model -----------------------------------------------------------
    logger.info(
        "Initialising EmbeddingService model=%r device=%r batch_size=%d",
        model_name,
        device,
        batch_size,
    )
    svc = EmbeddingService(model_name=model_name, device=device, batch_size=batch_size)

    # --- query and process ----------------------------------------------------
    with SessionLocal() as session:
        query = session.query(ModelClass)
        if limit:
            query = query.limit(limit)

        records = query.all()
        logger.info("Fetched %d %s record(s) from database.", len(records), entity)

        # Build (record, text) pairs
        texts_to_embed: list[tuple[Any, str]] = []
        for record in records:
            stats.total += 1
            text = text_fn(record)
            if text is None:
                stats.failed += 1
                stats.errors.append(f"{entity}:{getattr(record, 'id', '?')} — no title")
                continue

            stored_hash: str | None = getattr(record, "content_hash", None)
            stored_model: str | None = getattr(record, "embedding_model", None)

            if not force and not needs_reembedding(text, stored_hash, stored_model, model_name):
                stats.skipped += 1
                continue

            texts_to_embed.append((record, text))

        logger.info(
            "%d to embed, %d skipped (up-to-date), %d failed text construction.",
            len(texts_to_embed),
            stats.skipped,
            stats.failed,
        )

        if dry_run:
            logger.info("[DRY-RUN] Would embed %d record(s). No DB writes.", len(texts_to_embed))
            for rec, txt in texts_to_embed[:5]:
                logger.info(
                    "  [DRY-RUN] id=%s | text[:80]=%r",
                    getattr(rec, "id", "?"),
                    txt[:80],
                )
            stats.embedded = len(texts_to_embed)
            return stats

        # Encode in batches
        now = datetime.now(tz=timezone.utc)
        for batch_start in range(0, len(texts_to_embed), batch_size):
            batch = texts_to_embed[batch_start : batch_start + batch_size]
            batch_texts = [t for _, t in batch]

            try:
                vectors = svc.encode_batch(batch_texts)
            except Exception as exc:  # noqa: BLE001
                for rec, _ in batch:
                    stats.failed += 1
                    stats.errors.append(
                        f"{entity}:{getattr(rec, 'id', '?')} — encode error: {exc}"
                    )
                continue

            for (record, text), vector in zip(batch, vectors):
                try:
                    record.embedding = vector.tolist()
                    record.content_hash = compute_content_hash(text)
                    record.embedding_model = model_name
                    record.embedded_at = now
                    stats.embedded += 1
                except Exception as exc:  # noqa: BLE001
                    stats.failed += 1
                    stats.errors.append(
                        f"{entity}:{getattr(record, 'id', '?')} — update error: {exc}"
                    )

        session.commit()
        logger.info("Committed %d embedding(s) to database.", stats.embedded)

    return stats


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    from ml.embeddings.config import (
        EMBEDDING_BATCH_SIZE,
        EMBEDDING_DEVICE,
        EMBEDDING_MODEL,
    )

    model_name = args.model or EMBEDDING_MODEL
    batch_size = args.batch_size or EMBEDDING_BATCH_SIZE
    device = args.device or EMBEDDING_DEVICE

    logger.info(
        "Starting embedding pipeline: entity=%r model=%r dry_run=%s force=%s",
        args.entity,
        model_name,
        args.dry_run,
        args.force,
    )

    try:
        stats = run_pipeline(
            entity=args.entity,
            model_name=model_name,
            batch_size=batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            force=args.force,
            device=device,
        )
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc, exc_info=True)
        return 1

    print(stats.report())
    return 0 if stats.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
