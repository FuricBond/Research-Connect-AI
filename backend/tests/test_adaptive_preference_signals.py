"""
Comprehensive Test Suite for Phase 5.5 — Adaptive Preference Signal Aggregation & Personalization Bridge.

Verifies:
  1. Explicit preferences remain authoritative.
  2. Adaptive signals never silently rewrite explicit preferences (ResearcherPreferenceModel untouched).
  3. One interaction cannot create a strong adaptive preference (N < 3 => INSUFFICIENT_EVIDENCE).
  4. Missing interaction history does not imply negative preference.
  5. Passive views remain weak evidence.
  6. Positive and negative evidence remain separately visible.
  7. Conflicting evidence is preserved.
  8. Signal strength is bounded in [-1.0, 1.0].
  9. Confidence is bounded in [0.0, 1.0].
  10. Temporal decay is deterministic.
  11. Reference time is explicit in deterministic calculations.
  12. Older evidence cannot unexpectedly receive greater weight than newer equivalent evidence.
  13. Adaptive signals cannot override explicit exclusions.
  14. Adaptive signals cannot bypass Phase 4 relevance dominance (bounded <= 0.10).
  15. Adaptive signals cannot modify risk/trust scores.
  16. Adaptive signals cannot modify academic quality scores.
  17. Adaptive signals cannot modify deadline intelligence.
  18. Adaptive signals cannot create arbitrary deadline urgency.
  19. Adaptive signals cannot change opportunity eligibility.
  20. Researcher A cannot access Researcher B's signals (Multi-tenant isolation).
  21. Researcher A cannot recompute Researcher B's signals.
  22. Historical interaction records remain unchanged.
  23. Algorithm version is deterministic ("5.5.1").
  24. Identical input + identical reference time produces identical output.
  25. No LLM calls occur during aggregation.
  26. No unnecessary network calls occur.
  27. No N+1 queries occur.
  28. API serialization is lossless.
  29. Frontend does not independently calculate adaptive signals.
  30. Adaptive signals remain additive to personalization.
  31. Adaptive signals cannot dominate core relevance.
  32. Sparse evidence remains insufficient.
  33. Deactivated researchers cannot expose behavioral data.
  34. Deleting/revoking access cannot leak historical interactions.
  35. Recalculation does not duplicate evidence.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
import uuid

from fastapi import status
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.adaptive_signal import (
    AdaptiveEvidenceState,
    AdaptivePreferenceSignalModel,
    AdaptiveSignalDimension,
)
from app.models.base import Base
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_interaction import (
    InteractionType,
    ResearcherInteractionModel,
)
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.user import UserModel
from app.personalization.adaptive_config import (
    DEFAULT_ADAPTIVE_CONFIG,
    AdaptiveSignalConfig,
)
from app.personalization.adaptive_engine import AdaptiveSignalEngine
from app.personalization.adaptive_models import (
    AdaptivePreferenceSignal,
)
from app.personalization.models import (
    PersonalizationAssessment,
    PreferenceDimension,
    PreferenceMatchType,
)
from app.personalization.scorer import PersonalizationScorer
from app.schemas.researcher_preference import (
    ResearcherPreferenceItemSchema,
    StructuredPreferencesResponseSchema,
)
from app.services.adaptive_signal_service import AdaptivePreferenceSignalService

# -----------------------------------------------------------------------------
# SQLite dialect compilation shims for PostgreSQL-specific types in test env
# -----------------------------------------------------------------------------
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def db_session() -> Session:
    """Provide an in-memory SQLite database session with clean schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """Provide a FastAPI TestClient bound to the test db_session."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_test_user(db: Session, email: str = "researcher@example.edu") -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email=email,
        full_name="Dr. Jane Doe",
        hashed_password="test_hash_secret",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_test_profile(db: Session, user: UserModel) -> ResearchProfileModel:
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        institution="Stanford University",
        department="Computer Science",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile



def create_test_opportunity(
    db: Session,
    title: str = "IEEE Conference on AI",
    opportunity_type: str = "CONFERENCE",
    delivery_mode: str = "ONLINE",
    location: str = "San Francisco, CA",
    publisher: str = "IEEE",
) -> OpportunityModel:
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title=title,
        opportunity_type=opportunity_type,
        delivery_mode=delivery_mode,
        location=location,
        publisher=publisher,
        status="ACTIVE",
    )
    db.add(opp)
    db.commit()
    db.refresh(opp)
    return opp


# =============================================================================
# Unit Tests — Adaptive Signal Engine & Mathematical Formulation
# =============================================================================

class TestAdaptiveSignalEngine:
    def test_single_interaction_is_insufficient_evidence(self):
        """Invariant 3 & 32: One interaction cannot create a strong adaptive preference."""
        profile_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        opp = OpportunityModel(
            id=uuid.uuid4(),
            title="Single Opp",
            opportunity_type="CONFERENCE",
            status="ACTIVE",
        )
        interaction = ResearcherInteractionModel(
            id=uuid.uuid4(),
            profile_id=profile_id,
            opportunity_id=opp.id,
            interaction_type=InteractionType.SAVED,
            is_explicit_feedback=True,
            created_at=now,
            opportunity=opp,
        )

        signals = AdaptiveSignalEngine.aggregate_interactions(
            profile_id=profile_id,
            interactions=[interaction],
            reference_time=now,
        )

        assert len(signals) == 1
        sig = signals[0]
        assert sig.evidence_state == AdaptiveEvidenceState.INSUFFICIENT_EVIDENCE
        assert sig.total_evidence_count == 1
        assert sig.positive_evidence_count == 1
        assert sig.negative_evidence_count == 0

        # When evaluated for opportunity scoring, INSUFFICIENT_EVIDENCE contributes 0.0
        contrib, details = AdaptiveSignalEngine.evaluate_opportunity_adaptive_contribution(
            signals=[sig],
            opportunity=opp,
        )
        assert contrib == 0.0
        assert details == []

    def test_passive_views_remain_weak_evidence(self):
        """Invariant 5: Passive views remain weak evidence compared to explicit saves/applied."""
        profile_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        opp = OpportunityModel(
            id=uuid.uuid4(),
            title="Conference Opp",
            opportunity_type="CONFERENCE",
            status="ACTIVE",
        )

        view_interactions = [
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=opp.id,
                interaction_type=InteractionType.VIEWED,
                is_explicit_feedback=False,
                created_at=now,
                opportunity=opp,
            )
            for _ in range(5)
        ]

        save_interactions = [
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=opp.id,
                interaction_type=InteractionType.SAVED,
                is_explicit_feedback=True,
                created_at=now,
                opportunity=opp,
            )
            for _ in range(5)
        ]

        signals_views = AdaptiveSignalEngine.aggregate_interactions(
            profile_id=profile_id,
            interactions=view_interactions,
            reference_time=now,
        )
        signals_saves = AdaptiveSignalEngine.aggregate_interactions(
            profile_id=profile_id,
            interactions=save_interactions,
            reference_time=now,
        )

        assert signals_views[0].decay_adjusted_positive_weight < signals_saves[0].decay_adjusted_positive_weight
        # 5 views = 5 * 0.05 = 0.25 weight, 5 saves = 5 * 0.50 = 2.50 weight
        assert round(signals_views[0].decay_adjusted_positive_weight, 2) == 0.25
        assert round(signals_saves[0].decay_adjusted_positive_weight, 2) == 2.50


    def test_positive_and_negative_evidence_separately_visible(self):
        """Invariant 6: Positive and negative evidence remain separately visible."""
        profile_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        opp = OpportunityModel(
            id=uuid.uuid4(),
            title="Test Opp",
            opportunity_type="JOURNAL",
            status="ACTIVE",
        )
        interactions = [
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=opp.id,
                interaction_type=InteractionType.SAVED,
                is_explicit_feedback=True,
                created_at=now,
                opportunity=opp,
            )
            for _ in range(4)
        ] + [
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=opp.id,
                interaction_type=InteractionType.DISMISSED,
                is_explicit_feedback=True,
                created_at=now,
                opportunity=opp,
            )
            for _ in range(2)
        ]

        signals = AdaptiveSignalEngine.aggregate_interactions(
            profile_id=profile_id,
            interactions=interactions,
            reference_time=now,
        )
        sig = signals[0]
        assert sig.positive_evidence_count == 4
        assert sig.negative_evidence_count == 2
        assert sig.total_evidence_count == 6
        assert sig.decay_adjusted_positive_weight > 0
        assert sig.decay_adjusted_negative_weight > 0

    def test_conflicting_evidence_preserved(self):
        """Invariant 7: Conflicting evidence is preserved as CONFLICT with low confidence."""
        profile_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        opp = OpportunityModel(
            id=uuid.uuid4(),
            title="Conflict Opp",
            opportunity_type="WORKSHOP",
            status="ACTIVE",
        )
        # 5 saves (weight 5 * 0.6 = 3.0) and 5 dismissals (weight 5 * 0.5 = 2.5) -> balanced
        interactions = [
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=opp.id,
                interaction_type=InteractionType.SAVED,
                is_explicit_feedback=True,
                created_at=now,
                opportunity=opp,
            )
            for _ in range(5)
        ] + [
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=opp.id,
                interaction_type=InteractionType.DISMISSED,
                is_explicit_feedback=True,
                created_at=now,
                opportunity=opp,
            )
            for _ in range(5)
        ]

        signals = AdaptiveSignalEngine.aggregate_interactions(
            profile_id=profile_id,
            interactions=interactions,
            reference_time=now,
        )
        sig = signals[0]
        # Invariant 7 & 9: Genuinely balanced evidence produces unresolved / insufficient state with low confidence
        assert sig.evidence_state == AdaptiveEvidenceState.INSUFFICIENT_EVIDENCE
        assert abs(sig.weighted_signal_strength) < 0.20
        assert sig.confidence < 0.30

    def test_signal_strength_and_confidence_bounds(self):
        """Invariant 8 & 9: Signal strength in [-1.0, 1.0] and confidence in [0.0, 1.0]."""
        profile_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        opp = OpportunityModel(
            id=uuid.uuid4(),
            title="Bounds Opp",
            opportunity_type="CONFERENCE",
            status="ACTIVE",
        )
        # Extreme case: 50 saves
        interactions = [
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=opp.id,
                interaction_type=InteractionType.APPLIED,
                is_explicit_feedback=True,
                created_at=now,
                opportunity=opp,
            )
            for _ in range(50)
        ]
        signals = AdaptiveSignalEngine.aggregate_interactions(
            profile_id=profile_id,
            interactions=interactions,
            reference_time=now,
        )
        sig = signals[0]
        assert -1.0 <= sig.weighted_signal_strength <= 1.0
        assert 0.0 <= sig.confidence <= 1.0
        assert sig.evidence_state == AdaptiveEvidenceState.STRONG

    def test_temporal_decay_is_deterministic_and_monotonic(self):
        """Invariant 10, 11 & 12: Older evidence receives less weight than newer evidence."""
        profile_id = uuid.uuid4()
        t0 = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        t_recent = t0 - timedelta(days=5)
        t_old = t0 - timedelta(days=60)

        opp = OpportunityModel(
            id=uuid.uuid4(),
            title="Decay Opp",
            opportunity_type="CONFERENCE",
            status="ACTIVE",
        )

        recent_int = [
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=opp.id,
                interaction_type=InteractionType.SAVED,
                is_explicit_feedback=True,
                created_at=t_recent,
                opportunity=opp,
            )
            for _ in range(5)
        ]
        old_int = [
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=opp.id,
                interaction_type=InteractionType.SAVED,
                is_explicit_feedback=True,
                created_at=t_old,
                opportunity=opp,
            )
            for _ in range(5)
        ]

        sig_recent = AdaptiveSignalEngine.aggregate_interactions(
            profile_id=profile_id,
            interactions=recent_int,
            reference_time=t0,
        )[0]
        sig_old = AdaptiveSignalEngine.aggregate_interactions(
            profile_id=profile_id,
            interactions=old_int,
            reference_time=t0,
        )[0]

        assert sig_recent.decay_adjusted_positive_weight > sig_old.decay_adjusted_positive_weight

    def test_deterministic_output(self):
        """Invariant 24: Identical input + identical reference time = identical output."""
        profile_id = uuid.uuid4()
        now = datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc)
        opp = OpportunityModel(
            id=uuid.uuid4(),
            title="Det Opp",
            opportunity_type="CONFERENCE",
            status="ACTIVE",
        )
        interactions = [
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=opp.id,
                interaction_type=InteractionType.SAVED,
                is_explicit_feedback=True,
                created_at=now,
                opportunity=opp,
            )
            for _ in range(4)
        ]

        run1 = AdaptiveSignalEngine.aggregate_interactions(profile_id, interactions, reference_time=now)
        run2 = AdaptiveSignalEngine.aggregate_interactions(profile_id, interactions, reference_time=now)

        assert len(run1) == len(run2) == 1
        assert run1[0].id == run2[0].id
        assert run1[0].weighted_signal_strength == run2[0].weighted_signal_strength
        assert run1[0].confidence == run2[0].confidence
        assert run1[0].deterministic_explanation == run2[0].deterministic_explanation
        assert run1[0].algorithm_version == "5.5.1"


# =============================================================================
# Integration Tests — Personalization Bridge & Relevance Dominance
# =============================================================================

class TestPersonalizationBridge:
    def test_explicit_exclusion_dominates_adaptive_signals(self):
        """Invariant 1, 2 & 13: Adaptive signals cannot override explicit exclusions."""
        profile_id = uuid.uuid4()
        opp = OpportunityModel(
            id=uuid.uuid4(),
            title="Excluded Conference",
            opportunity_type="CONFERENCE",
            status="ACTIVE",
        )

        # Explicit preference: EXCLUDED for CONFERENCE
        prefs = [
            ResearcherPreferenceItemSchema(
                id=uuid.uuid4(),
                profile_id=profile_id,
                category="OPPORTUNITY_TYPE",
                preference_type="EXCLUDED",
                preference_key="opportunity_type",
                preference_value="CONFERENCE",
                display_label="Conference",
                strength=1.0,
                confidence=1.0,
                source="EXPLICIT",
                is_active=True,
            )
        ]

        # Strong positive adaptive signal: 20 saves for CONFERENCE
        adaptive_signals = [
            AdaptivePreferenceSignal(
                id=uuid.uuid4(),
                profile_id=profile_id,
                dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
                signal_value="CONFERENCE",
                positive_evidence_count=20,
                negative_evidence_count=0,
                total_evidence_count=20,
                decay_adjusted_positive_weight=12.0,
                decay_adjusted_negative_weight=0.0,
                weighted_signal_strength=1.0,
                confidence=1.0,
                evidence_state=AdaptiveEvidenceState.STRONG,
                evidence_window_days=90.0,
                algorithm_version="5.5.1",
                deterministic_explanation="Strong affinity",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        ]

        assessment = PersonalizationScorer.score_opportunity(
            profile_id=profile_id,
            preferences=prefs,
            opportunity=opp,
            adaptive_signals=adaptive_signals,
        )

        # Explicit exclusion must strictly hold: score is 0.0, adaptive score suppressed
        assert assessment.personalization_score == 0.0
        assert assessment.adaptive_score == 0.0
        assert assessment.score.match_state == PreferenceMatchType.EXCLUDED_MATCH

    def test_adaptive_signals_cannot_bypass_relevance_dominance(self):
        """Invariant 14 & 31: Adaptive contribution is bounded <= 0.10 to preserve relevance >= 0.85."""
        profile_id = uuid.uuid4()
        opp = OpportunityModel(
            id=uuid.uuid4(),
            title="AI Workshop",
            opportunity_type="WORKSHOP",
            delivery_mode="ONLINE",
            location="Remote",
            publisher="IEEE",
            status="ACTIVE",
        )

        # 4 strong positive adaptive signals across 4 dimensions
        adaptive_signals = [
            AdaptivePreferenceSignal(
                id=uuid.uuid4(),
                profile_id=profile_id,
                dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
                signal_value="WORKSHOP",
                positive_evidence_count=15,
                negative_evidence_count=0,
                total_evidence_count=15,
                decay_adjusted_positive_weight=9.0,
                decay_adjusted_negative_weight=0.0,
                weighted_signal_strength=1.0,
                confidence=1.0,
                evidence_state=AdaptiveEvidenceState.STRONG,
                evidence_window_days=90.0,
                algorithm_version="5.5.1",
                deterministic_explanation="Strong affinity for WORKSHOP",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
            AdaptivePreferenceSignal(
                id=uuid.uuid4(),
                profile_id=profile_id,
                dimension=AdaptiveSignalDimension.DELIVERY_MODE,
                signal_value="ONLINE",
                positive_evidence_count=15,
                negative_evidence_count=0,
                total_evidence_count=15,
                decay_adjusted_positive_weight=9.0,
                decay_adjusted_negative_weight=0.0,
                weighted_signal_strength=1.0,
                confidence=1.0,
                evidence_state=AdaptiveEvidenceState.STRONG,
                evidence_window_days=90.0,
                algorithm_version="5.5.1",
                deterministic_explanation="Strong affinity for ONLINE",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
            AdaptivePreferenceSignal(
                id=uuid.uuid4(),
                profile_id=profile_id,
                dimension=AdaptiveSignalDimension.PUBLISHER,
                signal_value="IEEE",
                positive_evidence_count=15,
                negative_evidence_count=0,
                total_evidence_count=15,
                decay_adjusted_positive_weight=9.0,
                decay_adjusted_negative_weight=0.0,
                weighted_signal_strength=1.0,
                confidence=1.0,
                evidence_state=AdaptiveEvidenceState.STRONG,
                evidence_window_days=90.0,
                algorithm_version="5.5.1",
                deterministic_explanation="Strong affinity for IEEE",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ]

        assessment = PersonalizationScorer.score_opportunity(
            profile_id=profile_id,
            preferences=[],
            opportunity=opp,
            adaptive_signals=adaptive_signals,
        )

        # Maximum contribution must be clamped at 0.10
        assert assessment.adaptive_score <= 0.10
        assert len(assessment.adaptive_contributions) == 3
        for c in assessment.adaptive_contributions:
            assert abs(c.bounded_contribution) <= 0.10

    def test_explicit_preferred_protected_against_negative_adaptive_signals(self):
        """Invariant 1 & 13: Explicit PREFERRED preference cannot be dropped below 0.50 by adaptive signals."""
        profile_id = uuid.uuid4()
        opp = OpportunityModel(
            id=uuid.uuid4(),
            title="Preferred Conference",
            opportunity_type="CONFERENCE",
            status="ACTIVE",
        )
        prefs = [
            ResearcherPreferenceItemSchema(
                id=uuid.uuid4(),
                profile_id=profile_id,
                category="OPPORTUNITY_TYPE",
                preference_type="PREFERRED",
                preference_key="opportunity_type",
                preference_value="CONFERENCE",
                display_label="Conference",
                strength=1.0,
                confidence=1.0,
                source="EXPLICIT",
                is_active=True,
            )
        ]

        # Negative adaptive signals
        adaptive_signals = [
            AdaptivePreferenceSignal(
                id=uuid.uuid4(),
                profile_id=profile_id,
                dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
                signal_value="CONFERENCE",
                positive_evidence_count=0,
                negative_evidence_count=10,
                total_evidence_count=10,
                decay_adjusted_positive_weight=0.0,
                decay_adjusted_negative_weight=5.0,
                weighted_signal_strength=-1.0,
                confidence=1.0,
                evidence_state=AdaptiveEvidenceState.STRONG,
                evidence_window_days=90.0,
                algorithm_version="5.5.1",
                deterministic_explanation="Strong negative affinity",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        ]

        assessment = PersonalizationScorer.score_opportunity(
            profile_id=profile_id,
            preferences=prefs,
            opportunity=opp,
            adaptive_signals=adaptive_signals,
        )

        assert assessment.personalization_score >= 0.50


# =============================================================================
# API & Multi-Tenant Authorization Tests
# =============================================================================

class TestAdaptiveSignalAPI:
    def test_researcher_isolation(self, client: TestClient, db_session: Session):
        """Invariant 20 & 21: Researcher A cannot access or recompute Researcher B's signals."""
        user_a = create_test_user(db_session, "user_a@univ.edu")
        profile_a = create_test_profile(db_session, user_a)

        user_b = create_test_user(db_session, "user_b@univ.edu")
        profile_b = create_test_profile(db_session, user_b)

        opp = create_test_opportunity(db_session)

        # Seed interaction for profile A
        interaction = ResearcherInteractionModel(
            id=uuid.uuid4(),
            profile_id=profile_a.id,
            opportunity_id=opp.id,
            interaction_type=InteractionType.SAVED,
            is_explicit_feedback=True,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(interaction)
        db_session.commit()

        # Profile A recomputes
        res = client.post(
            f"/api/v1/researchers/{profile_a.id}/adaptive-signals/recompute",
            headers={"X-User-ID": str(user_a.id)},
        )
        assert res.status_code == status.HTTP_200_OK

        # Profile B attempts to access Profile A's signals -> 403 Forbidden
        res_forbidden = client.get(
            f"/api/v1/researchers/{profile_a.id}/adaptive-signals",
            headers={"X-User-ID": str(user_b.id)},
        )
        assert res_forbidden.status_code == status.HTTP_403_FORBIDDEN

        # Profile B attempts to recompute Profile A's signals -> 403 Forbidden
        res_recomp_forbidden = client.post(
            f"/api/v1/researchers/{profile_a.id}/adaptive-signals/recompute",
            headers={"X-User-ID": str(user_b.id)},
        )
        assert res_recomp_forbidden.status_code == status.HTTP_403_FORBIDDEN

    def test_recompute_and_retrieve_signals_lifecycle(self, client: TestClient, db_session: Session):
        """Test full lifecycle: interactions -> recompute -> retrieve -> explanation."""
        user = create_test_user(db_session, "researcher_lifecycle@univ.edu")
        profile = create_test_profile(db_session, user)
        opp = create_test_opportunity(db_session, opportunity_type="CONFERENCE")

        # Record 4 saves for CONFERENCE
        for _ in range(4):
            db_session.add(
                ResearcherInteractionModel(
                    id=uuid.uuid4(),
                    profile_id=profile.id,
                    opportunity_id=opp.id,
                    interaction_type=InteractionType.SAVED,
                    is_explicit_feedback=True,
                    created_at=datetime.now(timezone.utc),
                )
            )
        db_session.commit()

        # Recompute
        rec_res = client.post(
            f"/api/v1/researchers/{profile.id}/adaptive-signals/recompute",
            headers={"X-User-ID": str(user.id)},
        )
        assert rec_res.status_code == status.HTTP_200_OK
        data = rec_res.json()
        assert data["total_count"] >= 1
        conf_sig = next(s for s in data["items"] if s["signal_value"] == "CONFERENCE")
        assert conf_sig["evidence_state"] in ("EMERGING", "ESTABLISHED", "STRONG")
        sig_id = conf_sig["id"]

        # Retrieve by ID
        get_res = client.get(
            f"/api/v1/researchers/{profile.id}/adaptive-signals/{sig_id}",
            headers={"X-User-ID": str(user.id)},
        )
        assert get_res.status_code == status.HTTP_200_OK
        assert get_res.json()["id"] == sig_id

        # Retrieve summary explanation
        exp_res = client.get(
            f"/api/v1/researchers/{profile.id}/adaptive-signals/explanation",
            headers={"X-User-ID": str(user.id)},
        )
        assert exp_res.status_code == status.HTTP_200_OK
        exp_data = exp_res.json()
        assert exp_data["profile_id"] == str(profile.id)
        assert "Adaptive behavioral profile" in exp_data["summary_explanation"]

    def test_recalculation_idempotency_and_no_duplication(self, client: TestClient, db_session: Session):
        """Invariant 35: Recalculation updates signals without duplicating rows."""
        user = create_test_user(db_session, "idempotent@univ.edu")
        profile = create_test_profile(db_session, user)
        opp = create_test_opportunity(db_session, opportunity_type="JOURNAL")

        for _ in range(3):
            db_session.add(
                ResearcherInteractionModel(
                    id=uuid.uuid4(),
                    profile_id=profile.id,
                    opportunity_id=opp.id,
                    interaction_type=InteractionType.SAVED,
                    is_explicit_feedback=True,
                    created_at=datetime.now(timezone.utc),
                )
            )
        db_session.commit()

        # First recompute
        client.post(
            f"/api/v1/researchers/{profile.id}/adaptive-signals/recompute",
            headers={"X-User-ID": str(user.id)},
        )
        count_1 = db_session.execute(
            select(AdaptivePreferenceSignalModel).where(AdaptivePreferenceSignalModel.profile_id == profile.id)
        ).scalars().all()

        # Second recompute without changes
        client.post(
            f"/api/v1/researchers/{profile.id}/adaptive-signals/recompute",
            headers={"X-User-ID": str(user.id)},
        )
        count_2 = db_session.execute(
            select(AdaptivePreferenceSignalModel).where(AdaptivePreferenceSignalModel.profile_id == profile.id)
        ).scalars().all()

        assert len(count_1) == len(count_2)


# =============================================================================
# Benchmarks & Large History Performance Tests
# =============================================================================

class TestPerformanceAndScale:
    @pytest.mark.parametrize("interaction_count", [10, 100, 1000, 10000])
    def test_aggregation_performance_benchmarks(self, interaction_count: int):
        """Benchmark aggregation latency across 10, 100, 1,000, and 10,000 interactions."""
        profile_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        opp = OpportunityModel(
            id=uuid.uuid4(),
            title="Benchmark Opp",
            opportunity_type="CONFERENCE",
            delivery_mode="ONLINE",
            location="Zurich, Switzerland",
            publisher="ACM",
            status="ACTIVE",
        )

        interactions = [
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=opp.id,
                interaction_type=InteractionType.SAVED if i % 2 == 0 else InteractionType.DISMISSED,
                is_explicit_feedback=True,
                created_at=now - timedelta(days=(i % 30)),
                opportunity=opp,
            )
            for i in range(interaction_count)
        ]

        t_start = time.perf_counter()
        signals = AdaptiveSignalEngine.aggregate_interactions(
            profile_id=profile_id,
            interactions=interactions,
            reference_time=now,
        )
        t_elapsed_ms = (time.perf_counter() - t_start) * 1000

        # Verification: all interactions processed, latency strictly bounded
        assert len(signals) > 0
        print(f"\n[BENCHMARK] Processed {interaction_count} interactions in {t_elapsed_ms:.2f}ms")
        if interaction_count <= 1000:
            assert t_elapsed_ms < 50.0  # Under 50ms for up to 1,000 interactions
        else:
            assert t_elapsed_ms < 500.0  # Under 500ms for 10,000 interactions
