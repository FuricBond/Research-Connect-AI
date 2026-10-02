"""
Tests for ml.embeddings.generate_embeddings pipeline.

These tests mock the database and the embedding service so that they run
quickly without PostgreSQL or a real model.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ml.embeddings.generate_embeddings import (
    PipelineStats,
    _build_opportunity_text_safe,
    _build_research_work_text_safe,
    run_pipeline,
)
from ml.embeddings.hash_utils import compute_content_hash


# ── Helpers ────────────────────────────────────────────────────────────────────


@dataclass
class FakeWork:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    title: str | None = "Attention is All You Need"
    abstract: str | None = "Transformer architecture."
    work_type: str | None = "article"
    publication_year: int | None = 2017
    language: str | None = "en"
    embedding: list[float] | None = None
    content_hash: str | None = None
    embedding_model: str | None = None
    embedded_at: datetime | None = None


@dataclass
class FakeOpp:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    title: str | None = "NeurIPS 2025"
    opportunity_type: str | None = "CONFERENCE"
    summary: str | None = "Top AI conference."
    description: str | None = None
    publisher: str | None = None
    organizer: str | None = None
    location: str | None = "Vancouver"
    series_name: str | None = None
    embedding: list[float] | None = None
    content_hash: str | None = None
    embedding_model: str | None = None
    embedded_at: datetime | None = None


# ── PipelineStats ─────────────────────────────────────────────────────────────


class TestPipelineStats:
    def test_report_contains_counts(self):
        stats = PipelineStats(total=10, skipped=3, embedded=6, failed=1)
        report = stats.report()
        assert "10" in report
        assert "6" in report
        assert "3" in report
        assert "1" in report

    def test_errors_truncated_at_10(self):
        stats = PipelineStats(errors=[f"err {i}" for i in range(20)])
        report = stats.report()
        assert "10 more" in report


# ── safe text builders ─────────────────────────────────────────────────────────


class TestSafeTextBuilders:
    def test_research_work_with_title(self):
        work = FakeWork(title="Valid Title")
        text = _build_research_work_text_safe(work)
        assert text is not None
        assert "Valid Title" in text

    def test_research_work_no_title_returns_none(self):
        work = FakeWork(title=None)
        assert _build_research_work_text_safe(work) is None

    def test_opportunity_with_title(self):
        opp = FakeOpp(title="ICML")
        text = _build_opportunity_text_safe(opp)
        assert text is not None
        assert "ICML" in text

    def test_opportunity_no_title_returns_none(self):
        opp = FakeOpp(title=None)
        assert _build_opportunity_text_safe(opp) is None


# ── run_pipeline (mocked DB + model) ──────────────────────────────────────────


def _make_fake_session(records: list[Any]) -> MagicMock:
    """Build a mock context-manager session that yields *records* from .query()."""
    query_mock = MagicMock()
    query_mock.all.return_value = records
    query_mock.limit.return_value = query_mock
    query_mock.options.return_value = query_mock

    session_mock = MagicMock()
    session_mock.query.return_value = query_mock
    session_mock.commit = MagicMock()

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session_mock)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def _make_fake_service(dim: int = 384) -> MagicMock:
    mock = MagicMock(spec=["encode_batch"])

    def fake_encode_batch(texts, **_kw):
        n = len(texts)
        vecs = np.ones((n, dim), dtype=np.float32) * 0.1
        return vecs

    mock.encode_batch.side_effect = fake_encode_batch
    return mock


def _run_pipeline_mocked(records: list[Any], *, dry_run: bool = False, force: bool = False) -> PipelineStats:
    """
    Helper: call run_pipeline with database and model fully mocked.

    Patches at the module level so unittest.mock can intercept correctly:
      ml.embeddings.generate_embeddings.SessionLocal
      ml.embeddings.generate_embeddings.EmbeddingService
    """
    ctx = _make_fake_session(records)
    svc = _make_fake_service()

    # Patch at the module level where run_pipeline looks them up
    with (
        patch("ml.embeddings.generate_embeddings.SessionLocal", return_value=ctx),
        patch("ml.embeddings.generate_embeddings.EmbeddingService", return_value=svc),
    ):
        # Also patch the ORM model import inside run_pipeline so it uses FakeWork
        with patch(
            "app.models.research_knowledge.ResearchWorkModel",
            FakeWork,
            create=True,
        ):
            pass  # not needed — query is already mocked

        return run_pipeline(
            entity="research_work",
            model_name="all-MiniLM-L6-v2",
            batch_size=8,
            limit=None,
            dry_run=dry_run,
            force=force,
            device="cpu",
        )


class TestRunPipelineResearchWork:
    MODEL = "all-MiniLM-L6-v2"

    def test_new_record_gets_embedded(self):
        records = [FakeWork()]
        stats = _run_pipeline_mocked(records, dry_run=False, force=False)
        assert stats.embedded == 1
        assert stats.failed == 0

    def test_dry_run_does_not_commit(self):
        records = [FakeWork()]
        ctx = _make_fake_session(records)
        session = ctx.__enter__.return_value
        svc = _make_fake_service()

        with (
            patch("ml.embeddings.generate_embeddings.SessionLocal", return_value=ctx),
            patch("ml.embeddings.generate_embeddings.EmbeddingService", return_value=svc),
        ):
            run_pipeline(
                entity="research_work",
                model_name=self.MODEL,
                batch_size=8,
                limit=None,
                dry_run=True,
                force=False,
                device="cpu",
            )
        session.commit.assert_not_called()

    def test_skips_up_to_date_record(self):
        """A record whose hash matches should be skipped."""
        from ml.embeddings.text_builder import build_research_work_text
        work = FakeWork()
        text = build_research_work_text(work)
        work.content_hash = compute_content_hash(text)
        work.embedding_model = self.MODEL

        stats = _run_pipeline_mocked([work], dry_run=False, force=False)
        assert stats.skipped == 1
        assert stats.embedded == 0

    def test_force_reembeds_up_to_date_record(self):
        """--force should bypass hash check."""
        from ml.embeddings.text_builder import build_research_work_text
        work = FakeWork()
        text = build_research_work_text(work)
        work.content_hash = compute_content_hash(text)
        work.embedding_model = self.MODEL

        stats = _run_pipeline_mocked([work], dry_run=False, force=True)
        assert stats.skipped == 0
        assert stats.embedded == 1

    def test_record_without_title_is_counted_as_failed(self):
        work = FakeWork(title=None)
        stats = _run_pipeline_mocked([work], dry_run=False, force=False)
        assert stats.failed == 1
        assert stats.embedded == 0

    def test_multiple_records_processed(self):
        records = [FakeWork(title=f"Paper {i}") for i in range(10)]
        stats = _run_pipeline_mocked(records, dry_run=False, force=False)
        assert stats.embedded == 10
        assert stats.failed == 0

    def test_commits_after_every_batch(self):
        """A crash late in a large run must not lose the batches already embedded."""
        records = [FakeWork(title=f"Paper {i}") for i in range(20)]
        ctx = _make_fake_session(records)
        session = ctx.__enter__.return_value
        with (
            patch("ml.embeddings.generate_embeddings.SessionLocal", return_value=ctx),
            patch("ml.embeddings.generate_embeddings.EmbeddingService", return_value=_make_fake_service()),
        ):
            stats = run_pipeline(
                entity="research_work",
                model_name=self.MODEL,
                batch_size=8,
                limit=None,
                dry_run=False,
                force=False,
                device="cpu",
            )
        assert stats.embedded == 20
        assert session.commit.call_count == 3  # batches of 8, 8 and 4

    def test_research_work_query_leaves_raw_payload_unloaded(self):
        """The raw API payload is not needed for the text and is deferred to save memory."""
        ctx = _make_fake_session([FakeWork()])
        session = ctx.__enter__.return_value
        with (
            patch("ml.embeddings.generate_embeddings.SessionLocal", return_value=ctx),
            patch("ml.embeddings.generate_embeddings.EmbeddingService", return_value=_make_fake_service()),
        ):
            run_pipeline(
                entity="research_work",
                model_name=self.MODEL,
                batch_size=8,
                limit=None,
                dry_run=True,
                force=False,
                device="cpu",
            )
        (option,), _ = session.query.return_value.options.call_args
        deferred = [str(strategy.path) for strategy in option.context]
        assert any("ResearchWorkModel.raw_metadata" in path for path in deferred)


class TestMainOutput:
    def test_report_prints_on_a_legacy_windows_code_page(self, monkeypatch):
        """Redirected output on Windows is cp1252; the summary must not crash after saving."""
        import io
        import sys

        from ml.embeddings.generate_embeddings import main

        buffer = io.BytesIO()
        monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(buffer, encoding="cp1252"))
        with patch(
            "ml.embeddings.generate_embeddings.run_pipeline",
            return_value=PipelineStats(total=1, embedded=1),
        ):
            assert main(["--entity", "research_work"]) == 0
        sys.stdout.flush()
        assert b"embedded (new)  : 1" in buffer.getvalue()


# ── Research refresh: pending-only selection and a shared service ──────────────


def _run_with(ctx, *, svc=None, embedding_service=None, **kwargs) -> PipelineStats:
    params = dict(
        entity="research_work",
        model_name="all-MiniLM-L6-v2",
        batch_size=8,
        limit=None,
        dry_run=False,
        force=False,
        device="cpu",
    )
    params.update(kwargs)
    with (
        patch("ml.embeddings.generate_embeddings.SessionLocal", return_value=ctx),
        patch(
            "ml.embeddings.generate_embeddings.EmbeddingService",
            return_value=svc if svc is not None else _make_fake_service(),
        ) as service_class,
    ):
        stats = run_pipeline(embedding_service=embedding_service, **params)
    return stats, service_class


def _query(ctx) -> MagicMock:
    query = ctx.__enter__.return_value.query.return_value
    query.filter.return_value = query
    return query


class TestPendingOnly:
    def test_pending_only_selects_missing_or_other_model_embeddings(self):
        from sqlalchemy.dialects import postgresql

        ctx = _make_fake_session([FakeWork()])
        query = _query(ctx)

        stats, _ = _run_with(ctx, pending_only=True)

        query.filter.assert_called_once()
        (criterion,), _ = query.filter.call_args
        sql = str(criterion.compile(dialect=postgresql.dialect()))
        assert "embedding IS NULL" in sql
        assert "embedding_model IS DISTINCT FROM" in sql
        assert " OR " in sql
        assert stats.embedded == 1

    def test_pending_only_filters_before_the_limit(self):
        ctx = _make_fake_session([FakeWork()])
        query = _query(ctx)

        _run_with(ctx, pending_only=True, limit=5)

        calls = [name for name, _, _ in query.mock_calls if name in ("filter", "limit")]
        assert calls == ["filter", "limit"]

    def test_no_filter_without_pending_only(self):
        ctx = _make_fake_session([FakeWork()])
        query = _query(ctx)
        _run_with(ctx)
        query.filter.assert_not_called()

    def test_force_ignores_pending_only(self):
        ctx = _make_fake_session([FakeWork()])
        query = _query(ctx)
        stats, _ = _run_with(ctx, pending_only=True, force=True)
        query.filter.assert_not_called()
        assert stats.embedded == 1

    def test_the_cli_flag_reaches_the_pipeline(self):
        from ml.embeddings.generate_embeddings import main

        with patch(
            "ml.embeddings.generate_embeddings.run_pipeline",
            return_value=PipelineStats(total=0),
        ) as run:
            assert main(["--entity", "research_work", "--pending-only"]) == 0
        assert run.call_args.kwargs["pending_only"] is True


class TestInjectedEmbeddingService:
    def _service(self, model_name: str = "all-MiniLM-L6-v2") -> MagicMock:
        svc = _make_fake_service()
        svc.model_name = model_name
        return svc

    def test_an_injected_service_is_used_and_no_service_is_constructed(self):
        injected = self._service()
        stats, service_class = _run_with(_make_fake_session([FakeWork()]), embedding_service=injected)

        service_class.assert_not_called()
        injected.encode_batch.assert_called_once()
        assert stats.embedded == 1

    def test_a_service_for_another_model_is_refused(self):
        with pytest.raises(ValueError, match="other-model"):
            _run_with(_make_fake_session([FakeWork()]), embedding_service=self._service("other-model"))

    def test_the_existing_tests_run_on_the_fake_service(self):
        """The module-level EmbeddingService is what the pipeline uses, so patching it works."""
        from ml.embeddings.service import EmbeddingService

        with patch.object(
            EmbeddingService, "_load_model", side_effect=AssertionError("the real model was loaded")
        ):
            stats = _run_pipeline_mocked([FakeWork()])
        assert stats.embedded == 1
