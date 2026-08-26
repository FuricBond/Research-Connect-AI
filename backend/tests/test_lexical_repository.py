"""
Unit and Integration tests for LexicalRepository in app.repositories.lexical_repository.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
import uuid
import pytest

from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.opportunity import OpportunityModel
from app.models.research_knowledge import ResearchWorkModel
from app.repositories.lexical_repository import (
    DEFAULT_FTS_CONFIG,
    LexicalRepository,
    LexicalSearchResult,
    build_opportunity_tsvector,
    build_research_work_tsvector,
)


@pytest.fixture
def lex_repo() -> LexicalRepository:
    return LexicalRepository(default_limit=20, max_limit=100, fts_config="english")


# ── A. UNIT TESTS ─────────────────────────────────────────────────────────────


class TestLexicalQueryValidation:
    """Tests for empty and whitespace query handling."""

    def test_empty_string_returns_empty_list(self, lex_repo):
        mock_session = MagicMock(spec=Session)
        assert lex_repo.search_research_works(mock_session, "") == []
        assert lex_repo.search_opportunities(mock_session, "") == []
        mock_session.execute.assert_not_called()

    def test_whitespace_string_returns_empty_list(self, lex_repo):
        mock_session = MagicMock(spec=Session)
        assert lex_repo.search_research_works(mock_session, "   \t\n  ") == []
        assert lex_repo.search_opportunities(mock_session, "   ") == []
        mock_session.execute.assert_not_called()

    def test_none_query_returns_empty_list(self, lex_repo):
        mock_session = MagicMock(spec=Session)
        assert lex_repo.search_research_works(mock_session, None) == []  # type: ignore
        assert lex_repo.search_opportunities(mock_session, None) == []  # type: ignore


class TestLexicalSQLCompilation:
    """Tests verifying SQL compilation and AST generation for PostgreSQL FTS."""

    def test_research_works_sql_structure(self):
        tsvector = build_research_work_tsvector("english")
        tsquery = func.websearch_to_tsquery("english", "reinforcement learning")
        score_expr = func.ts_rank_cd(tsvector, tsquery)

        stmt = (
            select(ResearchWorkModel, score_expr.label("lexical_score"))
            .where(tsvector.op("@@")(tsquery))
            .order_by(score_expr.desc())
            .limit(20)
        )

        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        assert "to_tsvector(" in compiled
        assert "setweight(" in compiled
        assert "websearch_to_tsquery(" in compiled
        assert "ts_rank_cd(" in compiled
        assert "@@" in compiled
        assert "ORDER BY ts_rank_cd(" in compiled
        assert "DESC" in compiled

    def test_opportunities_sql_structure(self):
        tsvector = build_opportunity_tsvector("english")
        tsquery = func.websearch_to_tsquery("english", "computer vision")
        score_expr = func.ts_rank_cd(tsvector, tsquery)

        stmt = (
            select(OpportunityModel, score_expr.label("lexical_score"))
            .where(tsvector.op("@@")(tsquery))
            .order_by(score_expr.desc())
            .limit(20)
        )

        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        assert "to_tsvector(" in compiled
        assert "setweight(" in compiled
        assert "websearch_to_tsquery(" in compiled
        assert "ts_rank_cd(" in compiled
        assert "@@" in compiled

    def test_research_works_filter_clauses(self):
        exclude_id = uuid.uuid4()
        source_id = uuid.uuid4()
        tsvector = build_research_work_tsvector("english")
        tsquery = func.websearch_to_tsquery("english", "graph networks")
        score_expr = func.ts_rank_cd(tsvector, tsquery)

        stmt = (
            select(ResearchWorkModel, score_expr.label("lexical_score"))
            .where(tsvector.op("@@")(tsquery))
            .where(ResearchWorkModel.id != exclude_id)
            .where(ResearchWorkModel.publication_year == 2023)
            .where(ResearchWorkModel.work_type == "preprint")
            .where(ResearchWorkModel.language == "en")
            .where(ResearchWorkModel.primary_source_id == source_id)
            .where(ResearchWorkModel.is_oa == True)
            .where(ResearchWorkModel.cited_by_count >= 5)
        )

        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        assert "research_works.id !=" in compiled
        assert "research_works.publication_year =" in compiled
        assert "research_works.work_type =" in compiled
        assert "research_works.language =" in compiled
        assert "research_works.primary_source_id =" in compiled
        assert "research_works.is_oa =" in compiled
        assert "research_works.cited_by_count >=" in compiled

    def test_opportunities_filter_clauses(self):
        exclude_id = uuid.uuid4()
        source_id = uuid.uuid4()
        deadline_cutoff = datetime(2025, 1, 1, tzinfo=timezone.utc)
        tsvector = build_opportunity_tsvector("english")
        tsquery = func.websearch_to_tsquery("english", "robotics")
        score_expr = func.ts_rank_cd(tsvector, tsquery)

        stmt = (
            select(OpportunityModel, score_expr.label("lexical_score"))
            .where(tsvector.op("@@")(tsquery))
            .where(OpportunityModel.id != exclude_id)
            .where(OpportunityModel.opportunity_type == "JOURNAL")
            .where(OpportunityModel.status.in_(["ACTIVE"]))
            .where(OpportunityModel.delivery_mode == "ONLINE")
            .where(OpportunityModel.source_id == source_id)
            .where(OpportunityModel.submission_deadline >= deadline_cutoff)
        )

        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        assert "opportunities.id !=" in compiled
        assert "opportunities.opportunity_type =" in compiled
        assert "opportunities.status IN" in compiled
        assert "opportunities.delivery_mode =" in compiled
        assert "opportunities.source_id =" in compiled
        assert "opportunities.submission_deadline >=" in compiled


class TestLexicalRepositoryMockExecution:
    """Tests for LexicalRepository with a mocked SQLAlchemy Session."""

    def test_search_research_works_success(self, lex_repo):
        mock_session = MagicMock(spec=Session)

        work_1 = ResearchWorkModel(
            id=uuid.uuid4(),
            title="Deep Residual Learning for Image Recognition",
        )
        work_2 = ResearchWorkModel(
            id=uuid.uuid4(),
            title="ImageNet Classification with Deep CNNs",
        )

        mock_rows = [(work_1, 0.45), (work_2, 0.22)]
        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        results = lex_repo.search_research_works(mock_session, "image recognition", limit=10)

        assert len(results) == 2
        assert results[0].entity_id == work_1.id
        assert results[0].lexical_score == 0.45
        assert results[0].rank == 1
        assert results[0].entity_type == "research_work"
        assert results[0].entity == work_1

        assert results[1].entity_id == work_2.id
        assert results[1].lexical_score == 0.22
        assert results[1].rank == 2

    def test_search_opportunities_success(self, lex_repo):
        mock_session = MagicMock(spec=Session)

        opp_1 = OpportunityModel(
            id=uuid.uuid4(),
            title="ECCV 2026",
            opportunity_type="CONFERENCE",
        )

        mock_rows = [(opp_1, 0.65)]
        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        results = lex_repo.search_opportunities(mock_session, "ECCV", limit=5)

        assert len(results) == 1
        assert results[0].entity_id == opp_1.id
        assert results[0].lexical_score == 0.65
        assert results[0].rank == 1
        assert results[0].entity_type == "opportunity"
        assert results[0].entity == opp_1


# ── B. POSTGRESQL INTEGRATION TESTS ───────────────────────────────────────────


def _is_postgres_available() -> bool:
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            res = conn.execute(select(1)).scalar_one_or_none()
            return res == 1
    except Exception:
        return False


postgres_integration = pytest.mark.skipif(
    not _is_postgres_available(),
    reason="PostgreSQL is not reachable in current environment.",
)


@postgres_integration
class TestPostgreSQLLexicalIntegration:
    def test_live_lexical_search_research_works(self, lex_repo):
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            results = lex_repo.search_research_works(session, "machine learning", limit=5)
            assert isinstance(results, list)
            for r in results:
                assert isinstance(r.entity_id, uuid.UUID)
                assert isinstance(r.lexical_score, float)
                assert r.rank >= 1
                assert r.entity_type == "research_work"

    def test_live_lexical_search_opportunities(self, lex_repo):
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            results = lex_repo.search_opportunities(session, "conference", limit=5)
            assert isinstance(results, list)
            for r in results:
                assert isinstance(r.entity_id, uuid.UUID)
                assert isinstance(r.lexical_score, float)
                assert r.rank >= 1
                assert r.entity_type == "opportunity"
