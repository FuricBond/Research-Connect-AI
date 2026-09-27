"""
Step 11 — peer discovery is consent-driven.

Two new researchers get research topics (in the product they come from linked publications,
which needs OpenAlex, so the suite writes the same interest rows the seeder does). Then,
entirely through the API: without consent a researcher is absent from others' results,
searching never creates consent, opting in makes them discoverable with only the fields they
chose to disclose, and opting out removes them again. Nobody can read another's settings or
search as them.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy.orm import Session

from conftest import Account, register, rows, scalar


def _give_topics(db, profile_id: str, topics: list[dict]) -> None:
    from app.models.researcher_interest import ResearcherInterestModel

    with Session(db) as session:
        for t in topics:
            session.add(ResearcherInterestModel(
                id=uuid.uuid4(), profile_id=uuid.UUID(profile_id), topic_id=t["topic_id"],
                topic_name=t["topic_name"], topic_slug=t["topic_slug"], strength=0.8, confidence=0.9,
                evidence_count=4, classification="PRIMARY_EXPERTISE", is_primary_expertise=True,
                source="E2E", provenance={"reasons": ["E2E fixture"]},
                created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
            ))
        session.commit()


@pytest.fixture(scope="module")
def demo_topics(db, demo) -> list[dict]:
    topics = rows(db, """
        SELECT DISTINCT topic_id, topic_name, topic_slug FROM researcher_interests
        WHERE profile_id IN (:f, :s) ORDER BY topic_slug""", f=demo["faculty"].profile_id, s=demo["student"].profile_id)
    assert len(topics) >= 3, "the seeder records expertise topics for its researchers"
    return topics


@pytest.fixture(scope="module")
def seeker(db, demo_topics) -> Account:
    account = register(label="peer-seeker", full_name="Sam Seeker")
    _give_topics(db, account.profile_id, demo_topics[:3])
    return account


@pytest.fixture(scope="module")
def candidate(db, demo_topics) -> Account:
    account = register(label="peer-candidate", full_name="Casey Candidate",
                       institution_name="Northbridge University")
    _give_topics(db, account.profile_id, demo_topics[:2])
    return account


def _search(account: Account) -> dict:
    response = account.get(f"/api/v1/researchers/{account.profile_id}/peers", params={"limit": 50})
    assert response.status_code == 200, response.text
    return response.json()


def _match_for(result: dict, profile_id: str) -> dict | None:
    return next((m for m in result["matches"] if m["peer"]["profile_id"] == profile_id), None)


def test_without_consent_a_researcher_is_absent_and_searching_creates_no_consent(seeker, candidate, demo, db):
    result = _search(seeker)
    assert result["data_sufficiency"] != "INSUFFICIENT_PROFILE", result
    assert _match_for(result, candidate.profile_id) is None, "no consent, no disclosure"
    assert _match_for(result, demo["faculty"].profile_id), "consented, overlapping researchers are found"
    # Neither searching nor reading one's own settings writes a consent row.
    own = seeker.get(f"/api/v1/researchers/{seeker.profile_id}/discovery-settings").json()
    assert own["is_discoverable"] is False and result["is_discoverable"] is False
    assert scalar(db, "SELECT count(*) FROM researcher_discovery_settings WHERE profile_id = :p", p=seeker.profile_id) == 0


def test_opting_in_discloses_only_the_chosen_fields(seeker, candidate):
    settings = f"/api/v1/researchers/{candidate.profile_id}/discovery-settings"
    opted = candidate.patch(settings, json={
        "is_discoverable": True, "collaboration_status": "OPEN_TO_ENQUIRIES",
        "collaboration_interests": ["CO_AUTHORSHIP"], "show_institution": False, "show_contact_email": False,
        "collaboration_note": "Happy to discuss retrieval evaluation.",
    })
    assert opted.status_code == 200, opted.text
    assert opted.json()["is_discoverable"] is True and opted.json()["consent_updated_at"]

    match = _match_for(_search(seeker), candidate.profile_id)
    assert match is not None, "consent makes the researcher discoverable"
    peer = match["peer"]
    assert peer["full_name"] == "Casey Candidate"
    assert peer["institution"] is None and peer["contact_email"] is None, "withheld fields stay hidden"
    assert match["shared_topics"] or match["complementary_topics"]
    assert match["explanation_reasons"] and 0 < match["match_score"] <= 1

    shown = candidate.patch(settings, json={"show_institution": True})
    assert shown.status_code == 200
    peer = _match_for(_search(seeker), candidate.profile_id)["peer"]
    assert peer["institution"] == "Northbridge University" and peer["contact_email"] is None


def test_opting_out_removes_the_researcher_again(seeker, candidate):
    off = candidate.patch(f"/api/v1/researchers/{candidate.profile_id}/discovery-settings", json={"is_discoverable": False})
    assert off.status_code == 200 and off.json()["is_discoverable"] is False
    assert _match_for(_search(seeker), candidate.profile_id) is None


def test_nobody_reads_anothers_settings_or_searches_as_them(seeker, candidate):
    assert seeker.get(f"/api/v1/researchers/{candidate.profile_id}/discovery-settings").status_code == 403
    assert seeker.patch(f"/api/v1/researchers/{candidate.profile_id}/discovery-settings",
                        json={"is_discoverable": True}).status_code == 403
    assert seeker.get(f"/api/v1/researchers/{candidate.profile_id}/peers").status_code == 403
    assert candidate.get(f"/api/v1/researchers/{candidate.profile_id}/discovery-settings").json()["is_discoverable"] is False
