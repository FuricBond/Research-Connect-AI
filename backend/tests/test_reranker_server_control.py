"""
The server alone decides whether the cross-encoder runs.

`rerank=true` used to force it on a public endpoint: any visitor could make the server load and run
a model. The parameter is still accepted, so existing callers keep working, and changes nothing.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import uuid

from fastapi.testclient import TestClient
import pytest

from app.api.v1 import discovery
from app.core.config import settings
from app.core.rate_limiter import rate_limiter
from app.db.session import get_db
from app.main import app
from app.models.research_knowledge import ResearchWorkModel
from app.services.hybrid_search_service import HybridSearchResult

SEARCH = "/api/v1/discovery/research/search"


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: MagicMock()
    rate_limiter.reset_all() if hasattr(rate_limiter, "reset_all") else rate_limiter._records.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def search():
    now = datetime.now(timezone.utc)
    work_id = uuid.uuid4()
    work = ResearchWorkModel(
        id=work_id,
        title="Graph Neural Networks in Molecular Discovery",
        abstract="We evaluate graph convolutional architectures.",
        publication_year=2023,
        work_type="article",
        cited_by_count=120,
        is_oa=True,
        created_at=now,
        updated_at=now,
    )
    candidate = HybridSearchResult(
        entity_id=work_id,
        entity_type="research_work",
        hybrid_score=0.033,
        vector_similarity=0.91,
        lexical_score=2.2,
        retrieval_sources=["vector", "lexical"],
        entity=work,
    )
    with patch("app.api.v1.discovery.hybrid_search_service.search_research_works", return_value=[candidate]) as mocked:
        yield mocked


@pytest.fixture
def model():
    """Stands in for the real model: nothing downloads, and every use of it is counted."""
    fake = MagicMock()
    fake.predict.return_value = [2.0]
    with patch.object(discovery.cross_encoder_reranker, "_get_model", return_value=fake) as get_model:
        yield get_model, fake


@pytest.fixture
def disabled(monkeypatch):
    monkeypatch.setattr(settings, "reranker_enabled", False)
    monkeypatch.setattr(discovery.cross_encoder_reranker, "enabled", False)


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "reranker_enabled", True)
    monkeypatch.setattr(discovery.cross_encoder_reranker, "enabled", True)


@pytest.mark.parametrize("value", ["true", "1", "yes", "on", "TRUE"])
def test_a_visitor_cannot_force_the_model(client, search, model, disabled, value) -> None:
    get_model, fake = model
    response = client.get(SEARCH, params={"q": f"graph neural networks {value}", "rerank": value})
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    get_model.assert_not_called()
    fake.predict.assert_not_called()


def test_a_signed_in_person_cannot_force_it_either(client, search, model, disabled) -> None:
    get_model, _ = model
    response = client.get(SEARCH, params={"q": "signed in", "rerank": "true"}, headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 200
    get_model.assert_not_called()


def test_the_parameter_changes_nothing_when_disabled(client, search, model, disabled) -> None:
    with_it = client.get(SEARCH, params={"q": "same query a", "rerank": "true"}).json()["items"]
    without_it = client.get(SEARCH, params={"q": "same query b"}).json()["items"]
    assert [item["final_score"] for item in with_it] == [item["final_score"] for item in without_it]


def test_ordinary_discovery_works_without_the_model(client, search, model, disabled) -> None:
    get_model, _ = model
    response = client.get(SEARCH, params={"q": "plain discovery"})
    assert response.status_code == 200
    assert response.json()["items"][0]["work"]["title"].startswith("Graph Neural")
    get_model.assert_not_called()


def test_the_server_setting_turns_it_on(client, search, model, enabled) -> None:
    get_model, fake = model
    response = client.get(SEARCH, params={"q": "server enabled"})
    assert response.status_code == 200
    get_model.assert_called_once()
    fake.predict.assert_called_once()


def test_a_false_parameter_cannot_turn_it_off_for_one_request(client, search, model, enabled) -> None:
    """The ranking is the server's choice in both directions, so everyone gets the same one."""
    get_model, _ = model
    assert client.get(SEARCH, params={"q": "still on", "rerank": "false"}).status_code == 200
    get_model.assert_called_once()


def test_no_other_route_can_start_the_model() -> None:
    """Only the one search route calls it, and only behind the setting."""
    import inspect

    source = inspect.getsource(discovery)
    assert source.count("cross_encoder_reranker.rerank(") == 1
    assert "force_enabled=rerank" not in source


def test_the_rate_limit_still_applies_to_rerank_requests(client, search, model, disabled, monkeypatch) -> None:
    monkeypatch.setattr(settings, "discovery_rate_limiting_enabled", True)
    monkeypatch.setattr(settings, "discovery_cache_enabled", False, raising=False)
    monkeypatch.setattr(rate_limiter, "requests_per_window", 3)
    answers = [client.get(SEARCH, params={"q": f"limited {n}", "rerank": "true"}).status_code for n in range(5)]
    assert answers[:3] == [200, 200, 200]
    assert answers[3:] == [429, 429]
