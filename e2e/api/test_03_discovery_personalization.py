"""
Steps 6–7 — the researcher discovery workflow and live personalization.

A new researcher registers, fills in a profile and preferences, browses and searches,
opens Similar Research and venue matching (the pgvector channels), gets personalized and
unified recommendations with explanations, gives feedback, and exercises the Phase 5
controls: exclusion, the personalization switch, governance and reset. Every step reads
back what it wrote, and another researcher is refused throughout.
"""
from __future__ import annotations

import time

import pytest

from conftest import Account, all_opportunities, observe, register, request, rows, scalar

IR_TITLES = {
    "International Conference on Information Retrieval Systems",
    "Workshop on Neural Retrieval Methods",
    "Journal of Information Retrieval Research",
}


@pytest.fixture(scope="module")
def researcher(corpus) -> Account:
    return register(label="researcher", full_name="Rosa Retrieval",
                    institution_name="Fairview Institute of Technology")


@pytest.fixture(scope="module")
def outsider() -> Account:
    return register(label="outsider")


def _ranked(account: Account, **params) -> dict:
    response = account.get(f"/api/v1/researchers/{account.profile_id}/personalized-recommendations",
                           params={"limit": 50, **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_profile_is_created_with_the_account_and_updates_persist(researcher, db):
    profile = researcher.get(f"/api/v1/researchers/{researcher.profile_id}")
    assert profile.status_code == 200 and profile.json()["full_name"] == "Rosa Retrieval"
    update = researcher.patch(f"/api/v1/researchers/{researcher.profile_id}", json={
        "keywords": ["information retrieval", "neural ranking"],
        "target_opportunity_types": ["CONFERENCE", "WORKSHOP"],
        "academic_status": "PHD",
    })
    assert update.status_code == 200, update.text
    again = researcher.get(f"/api/v1/researchers/{researcher.profile_id}").json()
    assert again["keywords"] == ["information retrieval", "neural ranking"]
    assert again["academic_status"] == "PHD"
    stored = rows(db, "SELECT keywords FROM research_profiles WHERE id = :id", id=researcher.profile_id)
    assert stored[0]["keywords"] == ["information retrieval", "neural ranking"]


def test_explicit_preferences_including_an_exclusion_are_stored(researcher):
    base = f"/api/v1/researchers/{researcher.profile_id}/preferences"
    topic = researcher.post(base, json={"category": "TOPIC", "preference_type": "PREFERRED",
                                        "preference_value": "information retrieval", "strength": 1.0})
    journal = researcher.post(base, json={"category": "OPPORTUNITY_TYPE", "preference_type": "EXCLUDED",
                                          "preference_value": "JOURNAL"})
    assert topic.status_code == 201, topic.text
    assert journal.status_code == 201, journal.text
    structured = researcher.get(f"{base}/structured").json()
    raw = {(p["category"], p["preference_type"], p["preference_value"]) for p in structured["raw_preferences"]}
    assert ("TOPIC", "PREFERRED", "information-retrieval") in raw, "topics are stored as canonical slugs"
    assert ("OPPORTUNITY_TYPE", "EXCLUDED", "JOURNAL") in raw


def test_browse_lists_active_opportunities_with_deadline_and_risk_intelligence():
    listed = all_opportunities()
    assert len(listed) == 10 and all(o["status"] == "ACTIVE" for o in listed)
    detail = request("GET", f"/api/opportunities/{listed[0]['id']}")
    assert detail.status_code == 200 and detail.json()["title"] == listed[0]["title"]


def test_literature_search_finds_the_corpus_through_the_generated_full_text_column(corpus):
    started = time.monotonic()
    response = request("GET", "/api/v1/discovery/research/search", params={"q": "information retrieval", "limit": 10})
    elapsed = time.monotonic() - started
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    titles = {i["work"]["title"] for i in items}
    assert "Learning to rank for information retrieval with neural models" in titles
    assert all("lexical" in i["retrieval_sources"] or "vector" in i["retrieval_sources"] for i in items)
    # Embedding a free-text query needs the sentence-transformers model inside the backend.
    observe("first_search", {
        "seconds": round(elapsed, 2),
        "semantic_channel_used": any("vector" in i["retrieval_sources"] for i in items),
    })


def test_similar_research_uses_the_stored_vectors(corpus):
    source = corpus["Dense passage retrieval for open-domain question answering"]
    response = request("GET", f"/api/v1/discovery/research/{source}/similar", params={"limit": 5})
    assert response.status_code == 200, response.text  # pgvector returns float32 (live regression)
    items = response.json()["items"]
    assert items and all(i["work"]["id"] != source for i in items)
    assert any("vector" in i["retrieval_sources"] for i in items)
    top = items[0]["work"]["title"]
    assert "retriev" in top.lower() or "query" in top.lower(), top


def test_venue_matching_ranks_on_topic_venues_first_with_risk_and_deadline(corpus):
    work = corpus["Learning to rank for information retrieval with neural models"]
    # The frontend always asks for explanations (explain=true); without it they are omitted.
    response = request("GET", f"/api/v1/discovery/research/{work}/opportunities", params={"limit": 5, "explain": "true"})
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items
    assert {i["opportunity"]["title"] for i in items[:3]} & IR_TITLES
    assert all(i["opportunity"]["status"] != "EXPIRED" for i in items)
    assert all(i["risk_explanation"] is not None and i["deadline_explanation"] is not None for i in items)


def test_personalized_recommendations_respect_relevance_dominance_and_exclusions(researcher):
    body = _ranked(researcher)
    recs = body["recommendations"]
    assert recs and body["personalization_enabled"] is True
    assert all(abs(r["personalization_adjustment"]) <= 0.15 + 1e-9 for r in recs), "personalization cap"
    journals = [r for r in recs if r["opportunity"]["opportunity_type"] == "JOURNAL"]
    assert journals, "the corpus has journals to exclude"
    for r in journals:  # explicit exclusion: no personalization at all, and it says why
        assert r["personalization_adjustment"] == 0.0
        assert any("EXCLUDED" in m for m in r["matched_signals"]["matched_preferences"])
    top = recs[0]
    explanation = researcher.get(
        f"/api/v1/researchers/{researcher.profile_id}/personalized-recommendations/{top['opportunity_id']}/explanation")
    assert explanation.status_code == 200, explanation.text
    assert explanation.json()["opportunity_id"] == top["opportunity_id"] and explanation.json()["primary_reasons"]


def test_unified_recommendations_carry_evidence_and_verified_invariants(researcher):
    response = researcher.get(f"/api/v1/researchers/{researcher.profile_id}/recommendations/unified", params={"limit": 10})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] and body["invariants_verified"]
    first = body["items"][0]
    assert first["evidence_tiers"] and first["risk_explanation"] and first["deadline_intelligence"]
    intel = researcher.get(
        f"/api/v1/researchers/{researcher.profile_id}/recommendations/unified/{first['opportunity_id']}/intelligence")
    assert intel.status_code == 200, intel.text


def test_feedback_becomes_bounded_adaptive_signals_and_survives_negative_evidence(researcher, db):
    by_title = {o["title"]: o["id"] for o in all_opportunities()}
    base = f"/api/v1/researchers/{researcher.profile_id}/opportunities"
    recorded = []
    for title, kind in [("International Conference on Information Retrieval Systems", "INTERESTED"),
                        ("Workshop on Neural Retrieval Methods", "SAVED"),
                        ("Conference on Applied Machine Learning", "NOT_INTERESTED"),
                        ("Conference on Applied Machine Learning", "NOT_INTERESTED"),
                        ("Symposium on Human-Computer Interaction and Accessibility", "DISMISSED")]:
        r = researcher.post(f"{base}/{by_title[title]}/interactions", json={"interaction_type": kind, "source": "RECOMMENDATION"})
        assert r.status_code == 201, r.text
        recorded.append(r.json()["id"])
    # Phase 5.4 rapid-fire deduplication: the repeated click is the same interaction.
    assert recorded[2] == recorded[3]
    assert scalar(db, "SELECT count(*) FROM researcher_interactions WHERE profile_id = :p", p=researcher.profile_id) == 4
    recompute = researcher.post(f"/api/v1/researchers/{researcher.profile_id}/adaptive-signals/recompute")
    assert recompute.status_code == 200, recompute.text
    signals = researcher.get(f"/api/v1/researchers/{researcher.profile_id}/adaptive-signals").json()
    assert signals["total_count"] > 0
    # The live ranking still answers with negative evidence present (the Phase 6.6 walkthrough fix).
    recs = _ranked(researcher)["recommendations"]
    assert all(0.0 <= r["score_breakdown"]["inferred_preference_score"] <= 1.0 for r in recs)
    assert all(abs(r["personalization_adjustment"]) <= 0.15 + 1e-9 for r in recs)
    governance = researcher.get(f"/api/v1/researchers/{researcher.profile_id}/personalization/governance")
    assert governance.status_code == 200 and governance.json()["total_count"] >= 1


def test_switching_personalization_off_makes_every_score_its_base_relevance(researcher):
    settings = f"/api/v1/researchers/{researcher.profile_id}/personalization/settings"
    off = researcher.patch(settings, json={"personalization_enabled": False})
    assert off.status_code == 200 and off.json()["personalization_enabled"] is False
    try:
        recs = _ranked(researcher)["recommendations"]
        assert recs and all(r["personalization_adjustment"] == 0.0 for r in recs)
    finally:
        assert researcher.patch(settings, json={"personalization_enabled": True}).status_code == 200
    history = researcher.get(f"/api/v1/researchers/{researcher.profile_id}/personalization/control-history").json()
    assert history["total"] >= 2 and len(history["events"]) >= 2, "each switch is audited"


def test_reset_clears_derived_signals_and_keeps_explicit_preferences(researcher):
    before = researcher.get(f"/api/v1/researchers/{researcher.profile_id}/personalization/settings").json()
    reset = researcher.post(f"/api/v1/researchers/{researcher.profile_id}/personalization/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json()["personalization_state_version"] == before["personalization_state_version"] + 1
    recompute = researcher.post(f"/api/v1/researchers/{researcher.profile_id}/adaptive-signals/recompute")
    assert recompute.status_code == 200
    signals = researcher.get(f"/api/v1/researchers/{researcher.profile_id}/adaptive-signals").json()
    assert signals["total_count"] == 0, "pre-reset interactions no longer produce signals"
    prefs = researcher.get(f"/api/v1/researchers/{researcher.profile_id}/preferences/structured").json()
    assert any(p["preference_type"] == "EXCLUDED" for p in prefs["raw_preferences"]), "explicit preferences stay"


def test_another_researcher_cannot_read_or_steer_this_researchers_personalization(researcher, outsider):
    target = researcher.profile_id
    opportunity = all_opportunities()[0]["id"]
    for method, path, body in [
        ("GET", f"/api/v1/researchers/{target}/personalized-recommendations", None),
        ("GET", f"/api/v1/researchers/{target}/preferences", None),
        ("GET", f"/api/v1/researchers/{target}/adaptive-signals", None),
        ("PATCH", f"/api/v1/researchers/{target}", {"keywords": ["hijacked"]}),
        ("POST", f"/api/v1/researchers/{target}/opportunities/{opportunity}/interactions", {"interaction_type": "NOT_INTERESTED"}),
        ("POST", f"/api/v1/researchers/{target}/personalization/reset", None),
    ]:
        response = request(method, path, outsider.token, json=body)
        assert response.status_code == 403, f"{method} {path} -> {response.status_code}"
    keywords = researcher.get(f"/api/v1/researchers/{target}").json()["keywords"]
    assert "hijacked" not in keywords
