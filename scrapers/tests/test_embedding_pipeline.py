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
