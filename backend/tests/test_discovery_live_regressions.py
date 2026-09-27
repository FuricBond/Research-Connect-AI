"""
Regressions found by exercising the live stack (PostgreSQL + pgvector) rather than mocks.

1. pgvector returns a stored embedding as a numpy float32 array. The query-vector validator
   accepted only Python int/float, so Opportunity Matcher and Similar Research both failed
   with 500 for every real paper.
2. The Similar Research route passed require_embedding=, which the service did not accept.
   The route tests used plain mocks that accept any keyword, so the TypeError never showed;
   the route tests below patch with autospec, which enforces the real signatures.
3. Opening a researcher page runs several governance reads at once; each could recompute
   and insert the same drift evaluation, and the second insert failed the unique
   constraint. Recomputes now take the per-profile advisory lock the scheduler uses.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import uuid

from fastapi.testclient import TestClient
import numpy as np
from pgvector.sqlalchemy import Vector
import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models.opportunity import OpportunityModel
from app.models.research_knowledge import ResearchWorkModel
from app.repositories.lexical_repository import LexicalRepository, LexicalSearchResult
from app.repositories.vector_repository import VectorRepository, VectorValidationError, validate_query_vector
from app.scheduler.locks import profile_lock_key
from app.services.personalization_governance_service import PersonalizationGovernanceService
from app.services.research_opportunity_matching_service import ResearchOpportunityMatchingService
from app.services.similar_research_service import MissingEmbeddingError, SimilarResearchService

DIM = 384


def pgvector_embedding(value: float = 0.25) -> np.ndarray:
    """An embedding exactly as pgvector hands it back from a query: a float32 ndarray."""
    return Vector(DIM).result_processor(None, None)("[" + ",".join([str(value)] * DIM) + "]")


# ── 1. Query-vector validation ────────────────────────────────────────────────


def test_pgvector_returns_float32_arrays():
    embedding = pgvector_embedding()
    assert isinstance(embedding, np.ndarray) and embedding.dtype == np.float32


def test_validator_accepts_a_stored_pgvector_embedding():
    validated = validate_query_vector(pgvector_embedding(), DIM)
    assert len(validated) == DIM
    assert all(type(v) is float for v in validated), "returns plain Python floats"


@pytest.mark.parametrize("bad", [True, np.bool_(True), "0.5", None, complex(1, 1)])
def test_validator_still_rejects_non_numeric_elements(bad):
    vector = [0.1] * DIM
    vector[7] = bad
    with pytest.raises(VectorValidationError, match="index 7"):
        validate_query_vector(vector, DIM)


# ── 2. Services with a real stored embedding ──────────────────────────────────


@pytest.fixture
def repos() -> tuple[MagicMock, MagicMock]:
    vec, lex = MagicMock(spec=VectorRepository), MagicMock(spec=LexicalRepository)
    vec.search_opportunities.return_value = []
    vec.search_research_works.return_value = []
    lex.search_opportunities.return_value = []
    lex.search_research_works.return_value = []
    return vec, lex


def _session_with(work: ResearchWorkModel) -> MagicMock:
    session = MagicMock(spec=Session)
    session.get.return_value = work
    return session


def test_opportunity_matcher_uses_a_stored_pgvector_embedding(repos):
    vec, lex = repos
    work = ResearchWorkModel(id=uuid.uuid4(), title="Dense retrieval", embedding=pgvector_embedding(), work_type="article")
    service = ResearchOpportunityMatchingService(vec_repo=vec, lex_repo=lex)

    service.match_opportunities(_session_with(work), work.id, require_embedding=True)

    vec.search_opportunities.assert_called_once()
    query = vec.search_opportunities.call_args.kwargs["query_embedding"]
    assert len(query) == DIM and all(type(v) is float for v in query)


def test_similar_research_uses_a_stored_pgvector_embedding(repos):
    vec, lex = repos
    work = ResearchWorkModel(id=uuid.uuid4(), title="Dense retrieval", embedding=pgvector_embedding())
    service = SimilarResearchService(vec_repo=vec, lex_repo=lex)

    service.get_similar_research(_session_with(work), work.id)

    vec.search_research_works.assert_called_once()


def test_similar_research_without_embedding_degrades_to_other_channels_when_allowed(repos):
    vec, lex = repos
    work = ResearchWorkModel(id=uuid.uuid4(), title="Query understanding", embedding=None)
    other = ResearchWorkModel(id=uuid.uuid4(), title="Query understanding at scale")
    lex.search_research_works.return_value = [
        LexicalSearchResult(entity_id=other.id, lexical_score=0.8, rank=1, entity_type="research_work", entity=other)
    ]
    service = SimilarResearchService(vec_repo=vec, lex_repo=lex)

    results = service.get_similar_research(_session_with(work), work.id, require_embedding=False)

    vec.search_research_works.assert_not_called()
    lex.search_research_works.assert_called_once()
    assert [r.candidate_work_id for r in results] == [other.id]


def test_similar_research_without_embedding_still_raises_by_default(repos):
    vec, lex = repos
    work = ResearchWorkModel(id=uuid.uuid4(), title="No embedding", embedding=None)
    with pytest.raises(MissingEmbeddingError):
        SimilarResearchService(vec_repo=vec, lex_repo=lex).get_similar_research(_session_with(work), work.id)


# ── 3. Route → service contracts, checked against the real signatures ────────


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_similar_research_route_calls_the_service_with_arguments_it_accepts(client):
    with patch(
        "app.api.v1.discovery.similar_research_service.get_similar_research", autospec=True, return_value=[]
    ) as service:
        response = client.get(f"/api/v1/discovery/research/{uuid.uuid4()}/similar?explain=true")
    assert response.status_code == 200, response.text
    service.assert_called_once()


def test_opportunity_matcher_route_calls_the_service_with_arguments_it_accepts(client):
    with patch(
        "app.api.v1.discovery.research_opportunity_matching_service.match_opportunities",
        autospec=True,
        return_value=[],
    ) as service:
        response = client.get(f"/api/v1/discovery/research/{uuid.uuid4()}/opportunities?explain=true")
    assert response.status_code == 200, response.text
    service.assert_called_once()


# ── 4. Governance recomputes are serialized per profile ──────────────────────


class _Stop(Exception):
    pass


def _first_statement(dialect_name: str, profile_id: uuid.UUID) -> str | None:
    db = MagicMock(spec=Session)
    db.get_bind.return_value.dialect.name = dialect_name
    db.execute.side_effect = [MagicMock(), _Stop(), _Stop(), _Stop()]
    with patch.object(PersonalizationGovernanceService, "get_latest_drift_evaluation", side_effect=_Stop):
        try:
            PersonalizationGovernanceService.recompute_governance(db, profile_id)
        except _Stop:
            pass
        except Exception:
            pass
    if not db.execute.call_args_list:
        return None
    stmt = db.execute.call_args_list[0].args[0]
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_governance_recompute_takes_the_profile_lock_on_postgresql():
    profile_id = uuid.uuid4()
    first = _first_statement("postgresql", profile_id)
    assert first is not None and "pg_advisory_xact_lock" in first
    assert str(profile_lock_key(profile_id)) in first


def test_governance_recompute_takes_no_lock_elsewhere():
    first = _first_statement("sqlite", uuid.uuid4())
    assert first is None or "pg_advisory_xact_lock" not in first
