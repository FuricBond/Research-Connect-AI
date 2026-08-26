"""
Tests for ml.embeddings.text_builder — semantic text construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from ml.embeddings.text_builder import (
    build_opportunity_text,
    build_research_work_text,
    build_text_from_dict,
    _MAX_CHARS,
    _truncate,
)


# ── helpers ────────────────────────────────────────────────────────────────────


@dataclass
class FakeWork:
    title: str | None = None
    abstract: str | None = None
    work_type: str | None = None
    publication_year: int | None = None
    language: str | None = None
    id: str = "work-abc"


@dataclass
class FakeOpp:
    title: str | None = None
    opportunity_type: str | None = None
    summary: str | None = None
    description: str | None = None
    publisher: str | None = None
    organizer: str | None = None
    location: str | None = None
    series_name: str | None = None
    id: str = "opp-xyz"


# ── _truncate ─────────────────────────────────────────────────────────────────


class TestTruncate:
    def test_short_text_unchanged(self):
        assert _truncate("hello world") == "hello world"

    def test_truncates_at_word_boundary(self):
        text = ("word " * 2000).strip()  # >8192 chars
        result = _truncate(text)
        assert len(result) <= _MAX_CHARS
        assert not result.endswith("wor")  # not mid-word

    def test_exactly_at_limit(self):
        text = "a" * _MAX_CHARS
        assert _truncate(text) == text

    def test_one_over_limit(self):
        text = "a" * (_MAX_CHARS + 1)
        result = _truncate(text)
        assert len(result) <= _MAX_CHARS


# ── build_research_work_text ──────────────────────────────────────────────────


class TestBuildResearchWorkText:
    def test_minimal_work_title_only(self):
        work = FakeWork(title="Deep Learning Survey")
        text = build_research_work_text(work)
        assert "Deep Learning Survey" in text

    def test_raises_if_no_title(self):
        work = FakeWork(title=None)
        with pytest.raises(ValueError, match="no title"):
            build_research_work_text(work)

    def test_raises_if_blank_title(self):
        work = FakeWork(title="   ")
        with pytest.raises(ValueError, match="no title"):
            build_research_work_text(work)

    def test_includes_abstract(self):
        work = FakeWork(title="Graph Neural Networks", abstract="We study GNNs …")
        text = build_research_work_text(work)
        assert "Graph Neural Networks" in text
        assert "We study GNNs" in text

    def test_includes_work_type(self):
        work = FakeWork(title="Some Title", work_type="preprint")
        text = build_research_work_text(work)
        assert "preprint" in text

    def test_includes_publication_year(self):
        work = FakeWork(title="Some Title", publication_year=2023)
        text = build_research_work_text(work)
        assert "2023" in text

    def test_english_language_not_included(self):
        work = FakeWork(title="English Paper", language="en")
        text = build_research_work_text(work)
        assert " en" not in text  # English suppressed

    def test_non_english_language_included(self):
        work = FakeWork(title="German Paper", language="de")
        text = build_research_work_text(work)
        assert "de" in text

    def test_deterministic(self):
        work = FakeWork(title="Test", abstract="Body", publication_year=2022)
        assert build_research_work_text(work) == build_research_work_text(work)

    def test_long_abstract_truncated(self):
        long_abstract = "word " * 3000
        work = FakeWork(title="Test", abstract=long_abstract)
        text = build_research_work_text(work)
        assert len(text) <= _MAX_CHARS


# ── build_opportunity_text ────────────────────────────────────────────────────


class TestBuildOpportunityText:
    def test_minimal_opportunity_title_only(self):
        opp = FakeOpp(title="ICML 2025")
        text = build_opportunity_text(opp)
        assert "ICML 2025" in text

    def test_raises_if_no_title(self):
        opp = FakeOpp(title=None)
        with pytest.raises(ValueError, match="no title"):
            build_opportunity_text(opp)

    def test_includes_type(self):
        opp = FakeOpp(title="NeurIPS", opportunity_type="CONFERENCE")
        text = build_opportunity_text(opp)
        assert "CONFERENCE" in text

    def test_includes_summary(self):
        opp = FakeOpp(title="ICML", summary="Top ML venue")
        text = build_opportunity_text(opp)
        assert "Top ML venue" in text

    def test_prefers_summary_over_description_when_same(self):
        opp = FakeOpp(title="Test", summary="Same text", description="Same text")
        text = build_opportunity_text(opp)
        # Should appear once, not duplicated
        assert text.count("Same text") == 1

    def test_includes_publisher(self):
        opp = FakeOpp(title="Test", publisher="ACM")
        text = build_opportunity_text(opp)
        assert "ACM" in text

    def test_includes_location(self):
        opp = FakeOpp(title="CVPR 2025", location="Seattle, WA")
        text = build_opportunity_text(opp)
        assert "Seattle" in text

    def test_deterministic(self):
        opp = FakeOpp(title="ICLR", summary="Learning representations", publisher="ICLR Foundation")
        assert build_opportunity_text(opp) == build_opportunity_text(opp)

    def test_long_description_truncated(self):
        opp = FakeOpp(title="CFP", description="long text " * 2000)
        text = build_opportunity_text(opp)
        assert len(text) <= _MAX_CHARS


# ── build_text_from_dict ──────────────────────────────────────────────────────


class TestBuildTextFromDict:
    def test_research_work_from_dict(self):
        data = {"title": "Attention is All You Need", "abstract": "Transformer model."}
        text = build_text_from_dict("research_work", data)
        assert "Attention is All You Need" in text

    def test_opportunity_from_dict(self):
        data = {"title": "ICML 2025", "opportunity_type": "CONFERENCE"}
        text = build_text_from_dict("opportunity", data)
        assert "ICML 2025" in text

    def test_unknown_entity_raises(self):
        with pytest.raises(ValueError, match="Unknown entity_type"):
            build_text_from_dict("grant", {})
