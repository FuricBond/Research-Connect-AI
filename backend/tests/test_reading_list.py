"""
Phase 5.14 — Personal reading list API.

A signed-in user of any role saves papers, tracks them as TO_READ / READING / DONE, keeps
private notes, removes them and exports them as BibTeX. Ownership is the core rule:

  401  for every route without an identity
  403  for another user's item, on read, update, delete and export
  404  for an unknown item or work
  Notes are private: they never appear in an export, and another user's items never do either.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.reading_list import ReadingListItemModel
from app.models.research_knowledge import (
    ResearcherModel,
    ResearchSourceModel,
    ResearchWorkAuthorModel,
    ResearchWorkModel,
)
from app.models.researcher_feedback import ResearcherRecommendationFeedbackModel
from app.models.researcher_interaction import ResearcherInteractionModel
from app.models.user import UserModel

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")

BASE = "/api/v1/reading-list"


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── Fixture helpers ─────────────────────────────────────────────────────────


def _user(db: Session, name: str, role: str = "STUDENT") -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email=f"{name.lower().replace(' ', '.')}.{uuid.uuid4().hex[:6]}@university.edu",
        hashed_password="hashed",
        full_name=name,
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def _work(db: Session, title: str, *, year: int = 2024, author: str = "Ada Lovelace") -> ResearchWorkModel:
    source = ResearchSourceModel(id=uuid.uuid4(), display_name="Journal of Retrieval", source_type="journal")
    researcher = ResearcherModel(id=uuid.uuid4(), display_name=author)
    work = ResearchWorkModel(
        id=uuid.uuid4(),
        openalex_id=f"W{uuid.uuid4().int % 10**10}",
        title=title,
        publication_year=year,
        work_type="article",
        doi=f"10.1000/{title.lower().replace(' ', '-')}",
        primary_source_id=source.id,
    )
    db.add_all([source, researcher, work])
    db.flush()
    db.add(ResearchWorkAuthorModel(work_id=work.id, researcher_id=researcher.id, author_position="first"))
    db.commit()
    return work


def _headers(user: UserModel) -> dict[str, str]:
    return {"X-User-ID": str(user.id)}


def _save(client: TestClient, user: UserModel, work: ResearchWorkModel, **body) -> dict:
    res = client.post(BASE, json={"work_id": str(work.id), **body}, headers=_headers(user))
    assert res.status_code in (200, 201), res.text
    return res.json()


# ===========================================================================
# Authentication
# ===========================================================================


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "", None),
        ("GET", "/lookup", None),
        ("GET", "/export.bib", None),
        ("POST", "", {"work_id": str(uuid.uuid4())}),
        ("GET", f"/{uuid.uuid4()}", None),
        ("PATCH", f"/{uuid.uuid4()}", {"status": "READING"}),
        ("DELETE", f"/{uuid.uuid4()}", None),
    ],
)
def test_every_route_requires_authentication(client: TestClient, method, path, body):
    res = client.request(method, f"{BASE}{path}", json=body)
    assert res.status_code == 401, res.text


def test_any_role_may_use_the_reading_list(client: TestClient, db_session: Session):
    work = _work(db_session, "Dense retrieval")
    for role in ("STUDENT", "FACULTY", "ADMIN"):
        user = _user(db_session, f"{role.title()} User", role=role)
        res = client.post(BASE, json={"work_id": str(work.id)}, headers=_headers(user))
        assert res.status_code == 201, (role, res.text)


# ===========================================================================
# Saving
# ===========================================================================


def test_saving_is_idempotent(client: TestClient, db_session: Session):
    user = _user(db_session, "Sam Student")
    work = _work(db_session, "Dense retrieval")

    first = client.post(BASE, json={"work_id": str(work.id), "notes": "read section 3"}, headers=_headers(user))
    second = client.post(BASE, json={"work_id": str(work.id), "status": "DONE"}, headers=_headers(user))

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == "TO_READ", "saving again changes nothing"
    assert second.json()["notes"] == "read section 3"
    assert db_session.execute(select(func.count()).select_from(ReadingListItemModel)).scalar_one() == 1

    body = first.json()
    assert body["work"]["title"] == "Dense retrieval"
    assert body["work"]["authors"] == ["Ada Lovelace"]
    assert body["work"]["venue_name"] == "Journal of Retrieval"
    assert body["work"]["doi"] == "10.1000/dense-retrieval"


def test_saving_an_unknown_work_is_404(client: TestClient, db_session: Session):
    user = _user(db_session, "Sam Student")
    res = client.post(BASE, json={"work_id": str(uuid.uuid4())}, headers=_headers(user))
    assert res.status_code == 404


def test_saving_records_no_personalization_signal(client: TestClient, db_session: Session):
    user = _user(db_session, "Sam Student")
    work = _work(db_session, "Dense retrieval")
    _save(client, user, work)

    assert db_session.execute(select(func.count()).select_from(ResearcherInteractionModel)).scalar_one() == 0
    assert db_session.execute(
        select(func.count()).select_from(ResearcherRecommendationFeedbackModel)
    ).scalar_one() == 0


# ===========================================================================
# Listing
# ===========================================================================


def test_status_filter_pagination_and_counts(client: TestClient, db_session: Session):
    user = _user(db_session, "Sam Student")
    other = _user(db_session, "Olive Other")
    items = [_save(client, user, _work(db_session, f"Paper {index}")) for index in range(5)]
    for item in items[:2]:
        client.patch(f"{BASE}/{item['id']}", json={"status": "READING"}, headers=_headers(user))
    _save(client, other, _work(db_session, "Someone else's paper"))

    everything = client.get(BASE, headers=_headers(user)).json()
    reading = client.get(BASE, params={"status": "READING"}, headers=_headers(user)).json()
    first_page = client.get(BASE, params={"limit": 2, "offset": 0}, headers=_headers(user)).json()
    second_page = client.get(BASE, params={"limit": 2, "offset": 2}, headers=_headers(user)).json()

    assert everything["total_count"] == 5
    assert everything["counts_by_status"] == {"TO_READ": 3, "READING": 2, "DONE": 0}
    assert {i["id"] for i in reading["items"]} == {items[0]["id"], items[1]["id"]}
    assert reading["total_count"] == 2
    assert reading["counts_by_status"] == everything["counts_by_status"], "counts ignore the filter"
    assert len(first_page["items"]) == 2 and len(second_page["items"]) == 2
    assert not {i["id"] for i in first_page["items"]} & {i["id"] for i in second_page["items"]}
    assert (first_page["limit"], first_page["offset"]) == (2, 0)
    # Most recently updated first: the two moved to READING lead.
    assert {i["id"] for i in first_page["items"]} == {items[0]["id"], items[1]["id"]}


def test_listing_query_count_does_not_grow_with_items(client: TestClient, db_session: Session):
    from app.services.reading_list_service import ReadingListService

    user = _user(db_session, "Sam Student")
    user_id = user.id

    def count_queries() -> int:
        engine = db_session.get_bind()
        count = 0

        def _listener(*args, **kwargs):
            nonlocal count
            count += 1

        event.listen(engine, "before_cursor_execute", _listener)
        try:
            ReadingListService.list_items(db_session, user_id)
        finally:
            event.remove(engine, "before_cursor_execute", _listener)
        return count

    for index in range(2):
        _save(client, user, _work(db_session, f"Paper {index}"))
    few = count_queries()
    for index in range(2, 10):
        _save(client, user, _work(db_session, f"Paper {index}"))
    many = count_queries()

    assert few == many, f"query count grew with items: {few} -> {many}"


# ===========================================================================
# Updating
# ===========================================================================


def test_status_changes_record_when_reading_started_and_finished(client: TestClient, db_session: Session):
    user = _user(db_session, "Sam Student")
    item = _save(client, user, _work(db_session, "Dense retrieval"))
    url = f"{BASE}/{item['id']}"
    assert item["started_at"] is None and item["finished_at"] is None

    reading = client.patch(url, json={"status": "READING"}, headers=_headers(user)).json()
    assert reading["status"] == "READING"
    assert reading["started_at"] is not None
    assert reading["finished_at"] is None
    assert reading["status_updated_at"] != item["status_updated_at"]

    done = client.patch(url, json={"status": "DONE"}, headers=_headers(user)).json()
    assert done["finished_at"] is not None
    assert done["started_at"] == reading["started_at"]

    reopened = client.patch(url, json={"status": "READING"}, headers=_headers(user)).json()
    assert reopened["finished_at"] is None, "leaving DONE clears the finish time"
    assert reopened["started_at"] == reading["started_at"], "the first start is kept"


def test_notes_are_set_and_cleared_and_only_sent_fields_change(client: TestClient, db_session: Session):
    user = _user(db_session, "Sam Student")
    item = _save(client, user, _work(db_session, "Dense retrieval"), status="READING")
    url = f"{BASE}/{item['id']}"

    noted = client.patch(url, json={"notes": "Compare with BM25."}, headers=_headers(user)).json()
    assert noted["notes"] == "Compare with BM25."
    assert noted["status"] == "READING", "status was not sent, so it is unchanged"
    assert noted["status_updated_at"] == item["status_updated_at"]

    cleared = client.patch(url, json={"notes": None}, headers=_headers(user)).json()
    assert cleared["notes"] is None

    assert client.patch(url, json={"status": None}, headers=_headers(user)).status_code == 422
    assert client.patch(url, json={"notes": "x" * 10_001}, headers=_headers(user)).status_code == 422


# ===========================================================================
# Ownership
# ===========================================================================


def test_another_users_item_is_forbidden(client: TestClient, db_session: Session):
    owner = _user(db_session, "Owen Owner")
    intruder = _user(db_session, "Ivy Intruder")
    item = _save(client, owner, _work(db_session, "Dense retrieval"), notes="private thought")
    url = f"{BASE}/{item['id']}"

    assert client.get(url, headers=_headers(intruder)).status_code == 403
    assert client.patch(url, json={"notes": "defaced"}, headers=_headers(intruder)).status_code == 403
    assert client.delete(url, headers=_headers(intruder)).status_code == 403

    still = client.get(url, headers=_headers(owner)).json()
    assert still["notes"] == "private thought"


def test_delete_then_the_item_is_gone(client: TestClient, db_session: Session):
    user = _user(db_session, "Sam Student")
    item = _save(client, user, _work(db_session, "Dense retrieval"))
    url = f"{BASE}/{item['id']}"

    assert client.delete(url, headers=_headers(user)).status_code == 204
    assert client.get(url, headers=_headers(user)).status_code == 404
    assert client.delete(url, headers=_headers(user)).status_code == 404
    assert client.patch(url, json={"status": "DONE"}, headers=_headers(user)).status_code == 404


def test_lookup_returns_only_the_callers_items(client: TestClient, db_session: Session):
    user = _user(db_session, "Sam Student")
    other = _user(db_session, "Olive Other")
    mine = _work(db_session, "Mine")
    theirs = _work(db_session, "Theirs")
    unsaved = _work(db_session, "Unsaved")
    my_item = _save(client, user, mine)
    _save(client, other, theirs)

    res = client.get(
        f"{BASE}/lookup",
        params={"work_ids": [str(mine.id), str(theirs.id), str(unsaved.id)]},
        headers=_headers(user),
    )

    assert res.status_code == 200
    assert res.json()["saved"] == {str(mine.id): my_item["id"]}

    too_many = client.get(
        f"{BASE}/lookup",
        params={"work_ids": [str(uuid.uuid4()) for _ in range(101)]},
        headers=_headers(user),
    )
    assert too_many.status_code == 422


# ===========================================================================
# Export
# ===========================================================================


def test_export_all_is_bibtex_without_notes_or_other_users_items(client: TestClient, db_session: Session):
    user = _user(db_session, "Sam Student")
    other = _user(db_session, "Olive Other")
    _save(client, user, _work(db_session, "Dense retrieval"), notes="SECRET-NOTE")
    _save(client, user, _work(db_session, "Sparse retrieval", author="Charles Babbage"), status="DONE")
    _save(client, other, _work(db_session, "Their private paper"), notes="THEIR-NOTE")

    res = client.get(f"{BASE}/export.bib", headers=_headers(user))

    assert res.status_code == 200
    assert res.headers["content-type"] == "application/x-bibtex; charset=utf-8"
    assert res.headers["content-disposition"] == 'attachment; filename="reading-list.bib"'
    assert res.headers["cache-control"] == "no-store"
    body = res.text
    assert body.count("@article{") == 2
    assert "{{Dense retrieval}}" in body and "{{Sparse retrieval}}" in body
    assert "SECRET-NOTE" not in body and "THEIR-NOTE" not in body
    assert "Their private paper" not in body
    assert "TO_READ" not in body and "DONE" not in body

    done_only = client.get(f"{BASE}/export.bib", params={"status": "DONE"}, headers=_headers(user)).text
    assert "Sparse retrieval" in done_only and "Dense retrieval" not in done_only


def test_export_selected_items(client: TestClient, db_session: Session):
    user = _user(db_session, "Sam Student")
    chosen = _save(client, user, _work(db_session, "Chosen paper"))
    _save(client, user, _work(db_session, "Skipped paper"))

    res = client.get(f"{BASE}/export.bib", params={"item_ids": [chosen["id"]]}, headers=_headers(user))

    assert res.status_code == 200
    assert "Chosen paper" in res.text and "Skipped paper" not in res.text

    unknown = client.get(f"{BASE}/export.bib", params={"item_ids": [str(uuid.uuid4())]}, headers=_headers(user))
    assert unknown.status_code == 404


def test_export_with_a_foreign_id_is_forbidden(client: TestClient, db_session: Session):
    user = _user(db_session, "Sam Student")
    other = _user(db_session, "Olive Other")
    mine = _save(client, user, _work(db_session, "Mine"))
    theirs = _save(client, other, _work(db_session, "Theirs"), notes="THEIR-NOTE")

    res = client.get(
        f"{BASE}/export.bib",
        params={"item_ids": [mine["id"], theirs["id"]]},
        headers=_headers(user),
    )

    assert res.status_code == 403
    assert "Theirs" not in res.text and "THEIR-NOTE" not in res.text


def test_an_empty_export_is_an_empty_file(client: TestClient, db_session: Session):
    user = _user(db_session, "Sam Student")
    res = client.get(f"{BASE}/export.bib", headers=_headers(user))
    assert res.status_code == 200
    assert res.content == b""


# ===========================================================================
# Routing
# ===========================================================================


def test_static_routes_are_not_read_as_an_item_id(client: TestClient, db_session: Session):
    """`/lookup` and `/export.bib` would fail UUID parsing (422) if `/{item_id}` caught them."""
    user = _user(db_session, "Sam Student")

    for prefix in ("/api/v1/reading-list", "/api/reading-list"):
        assert client.get(f"{prefix}/lookup", headers=_headers(user)).status_code == 200
        assert client.get(f"{prefix}/export.bib", headers=_headers(user)).status_code == 200
        assert client.get(prefix, headers=_headers(user)).status_code == 200
