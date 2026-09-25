"""
Phase 6 — P1 Hardening Regression Suite.

Covers the audit's P1 findings, each of which was a silent correctness or safety gap
rather than a crash:

  P1-1  A personalization reset must be durable: interactions and feedback recorded before
        the reset stay in the append-only store for audit but can never be re-aggregated
        into derived signals.
  P1-2  Phase 5.6 calibrations and Phase 5.7 contextual adaptations must reach the live
        ranking path, and the per-opportunity explanation endpoints must honour the same
        researcher control toggles the ranking honours.
  P1-5  Settings and governance lookups must fail closed, never silently granting an
        unrestricted ALLOW gate or assuming consent to personalize.
  P1-7  The personalization risk gate must see the effective Phase 2.6 assessment rather
        than the never-written opportunities.risk_score column.
  P1-8  Governance must be recomputed when the behavioural signals it governs change,
        not only when somebody happens to read the health endpoint.
  P1-12 An identifier matching no account or profile must be rejected, not passed through
        as an owner id.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.types import TSVector, Vector
from app.models.adaptive_signal import (
    AdaptiveEvidenceState,
    AdaptivePreferenceSignalModel,
    AdaptiveSignalDimension,
)
from app.models.base import Base
from app.models.opportunity import OpportunityModel
from app.models.personalization_calibration import (
    CalibrationState,
    PersonalizationCalibrationModel,
)
from app.models.personalization_governance import (
    GovernanceGateState,
    PersonalizationDriftEvaluationModel,
    PersonalizationHealthState,
)
from app.models.personalization_transparency import (
    ResearcherPersonalizationSettingsModel,
)
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_feedback import ResearcherRecommendationFeedbackModel
from app.models.researcher_interaction import InteractionType, ResearcherInteractionModel
from app.models.user import UserModel
from app.services.adaptive_signal_service import AdaptivePreferenceSignalService
from app.services.feedback_service import ResearcherFeedbackService
from app.services.personalization_ranking_service import (
    PersonalizationRankingService,
    _is_missing_table_error,
)
from app.services.personalization_transparency_service import (
    PersonalizationTransparencyService,
)
from app.services.workspace_service import WorkspaceService

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


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
def profile(db_session: Session) -> ResearchProfileModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="p1.hardening@university.edu",
        hashed_password="hashed",
        full_name="Dr. Hardening",
        role="FACULTY",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    prof = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        academic_status="FACULTY",
        institution="Test University",
        keywords=["machine learning"],
        target_opportunity_types=["CONFERENCE"],
    )
    db_session.add(prof)
    db_session.commit()
    return prof


# Text the Phase 2.6 heuristic extractors recognize: sub-48-hour review, guaranteed
# publication for a fee, and an untraceable payment channel. The engine scores this 1.0,
# which is the point of the P1-7 test: that score exists only in memory, because ingestion
# never writes opportunities.risk_score.
PREDATORY_DESCRIPTION = (
    "Peer review completed within 24 hours. Guaranteed publication upon payment of fee. "
    "Pay the article charge via Western Union."
)


def _make_opportunity(
    db: Session,
    title: str,
    *,
    opportunity_type: str = "CONFERENCE",
    is_predatory: bool = False,
    days_until_deadline: int = 45,
) -> OpportunityModel:
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title=title,
        opportunity_type=opportunity_type,
        status="ACTIVE",
        delivery_mode="ONLINE",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=days_until_deadline),
        is_predatory_flag=is_predatory,
        description=PREDATORY_DESCRIPTION if is_predatory else None,
    )
    db.add(opp)
    db.commit()
    return opp


def _seed_adaptive_signal_and_calibration(
    db: Session,
    profile: ResearchProfileModel,
    *,
    signal_value: str = "CONFERENCE",
    calibration_modifier: float = 0.05,
) -> None:
    """
    Seeds an established adaptive signal plus a matching calibration.

    Both are required to exercise the live calibration path: the scorer is only invoked when
    there are preferences or adaptive signals to evaluate, and a calibration modifies an
    existing adaptive contribution rather than creating one.
    """
    now = datetime.now(timezone.utc)
    db.add(
        AdaptivePreferenceSignalModel(
            id=uuid.uuid4(),
            profile_id=profile.id,
            dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE.value,
            signal_value=signal_value,
            positive_evidence_count=10,
            negative_evidence_count=0,
            total_evidence_count=10,
            decay_adjusted_positive_weight=6.0,
            decay_adjusted_negative_weight=0.0,
            weighted_signal_strength=0.8,
            confidence=0.9,
            evidence_state=AdaptiveEvidenceState.STRONG.value,
            latest_evidence_timestamp=now,
            deterministic_explanation="seeded adaptive signal",
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        PersonalizationCalibrationModel(
            id=uuid.uuid4(),
            profile_id=profile.id,
            dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE.value,
            signal_value=signal_value,
            net_calibration_modifier=calibration_modifier,
            calibration_confidence=0.9,
            calibration_state=CalibrationState.STABLE.value,
            deterministic_explanation="seeded calibration",
        )
    )
    db.commit()


# ===========================================================================
# P1-1 — A reset is a durable cold start
# ===========================================================================


def test_p1_1_reset_records_cutoff_and_clears_derived_state(
    db_session: Session, profile: ResearchProfileModel
):
    """Reset stamps a cutoff, bumps the version, and neutralizes derived state."""
    db_session.add(
        PersonalizationCalibrationModel(
            id=uuid.uuid4(),
            profile_id=profile.id,
            dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE.value,
            signal_value="CONFERENCE",
            net_calibration_modifier=0.04,
            calibration_state=CalibrationState.STABLE.value,
            deterministic_explanation="seeded",
        )
    )
    db_session.add(
        PersonalizationDriftEvaluationModel(
            id=uuid.uuid4(),
            profile_id=profile.id,
            overall_health_state=PersonalizationHealthState.DEGRADED.value,
            governance_state=GovernanceGateState.SUSPEND.value,
            evaluation_timestamp=datetime.now(timezone.utc),
            health_summary="seeded",
            governance_explanation="seeded",
        )
    )
    db_session.commit()

    response = PersonalizationTransparencyService.reset_personalization(
        db_session, profile.id, reason="test reset"
    )

    assert response.personalization_state_version == 2
    assert response.reset_at is not None
    assert response.calibration_states_reset == 1
    assert response.drift_evaluations_reset == 1

    settings = PersonalizationTransparencyService.load_settings(db_session, profile.id)
    assert settings is not None
    assert settings.personalization_reset_at is not None

    # The stale SUSPEND gate must not outlive the reset.
    remaining_drift = db_session.execute(
        select(PersonalizationDriftEvaluationModel).where(
            PersonalizationDriftEvaluationModel.profile_id == profile.id
        )
    ).scalars().all()
    assert remaining_drift == []


def test_p1_1_recompute_after_reset_does_not_resurrect_pre_reset_interactions(
    db_session: Session, profile: ResearchProfileModel
):
    """
    The regression the audit found: interactions are append-only, so the next recompute
    rebuilt exactly the state the researcher had just asked to be cleared.
    """
    opp = _make_opportunity(db_session, "Pre-Reset Conference")

    # Enough explicit positive evidence to clear the ESTABLISHED threshold.
    base = datetime.now(timezone.utc) - timedelta(days=1)
    for i in range(8):
        db_session.add(
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile.id,
                opportunity_id=opp.id,
                interaction_type=InteractionType.INTERESTED.value,
                client_event_id=f"pre-reset-{i}",
                created_at=base,
            )
        )
    db_session.commit()

    before = AdaptivePreferenceSignalService.recompute_adaptive_signals(db_session, profile.id)
    db_session.commit()
    assert before, "expected adaptive signals from pre-reset interactions"

    PersonalizationTransparencyService.reset_personalization(db_session, profile.id)

    after = AdaptivePreferenceSignalService.recompute_adaptive_signals(db_session, profile.id)
    db_session.commit()
    assert not after, "pre-reset interactions must not be re-aggregated after a reset"

    # The audit trail itself is preserved.
    retained = db_session.execute(
        select(ResearcherInteractionModel).where(
            ResearcherInteractionModel.profile_id == profile.id
        )
    ).scalars().all()
    assert len(retained) == 8


def test_p1_1_interactions_after_reset_are_learned_again(
    db_session: Session, profile: ResearchProfileModel
):
    """A reset is a cold start, not a permanent opt-out: new evidence still counts."""
    opp = _make_opportunity(db_session, "Post-Reset Conference")
    PersonalizationTransparencyService.reset_personalization(db_session, profile.id)

    for i in range(8):
        db_session.add(
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile.id,
                opportunity_id=opp.id,
                interaction_type=InteractionType.INTERESTED.value,
                client_event_id=f"post-reset-{i}",
                created_at=datetime.now(timezone.utc),
            )
        )
    db_session.commit()

    signals = AdaptivePreferenceSignalService.recompute_adaptive_signals(db_session, profile.id)
    db_session.commit()
    assert signals, "interactions recorded after the reset must still build signals"


def test_p1_1_reset_cutoff_excludes_prior_feedback_from_behavioral_profile(
    db_session: Session, profile: ResearchProfileModel
):
    """Phase 3.6 feedback is filtered by the same cutoff as Phase 5.5 interactions."""
    opp = _make_opportunity(db_session, "Feedback Venue")
    db_session.add(
        ResearcherRecommendationFeedbackModel(
            id=uuid.uuid4(),
            researcher_id=profile.id,
            opportunity_id=opp.id,
            feedback_type="SAVE",
            source="RECOMMENDATION",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
    )
    db_session.commit()

    before = ResearcherFeedbackService.get_behavioral_profile(db_session, profile.id)
    assert before.signals, "expected behavioral signals before reset"

    PersonalizationTransparencyService.reset_personalization(db_session, profile.id)

    after = ResearcherFeedbackService.get_behavioral_profile(db_session, profile.id)
    assert not after.signals, "pre-reset feedback must not shape ranking after a reset"


def test_p1_1_explicit_cutoff_argument_avoids_extra_lookup(
    db_session: Session, profile: ResearchProfileModel
):
    """
    Callers holding the settings row pass the cutoff in; passing None explicitly means
    "no cutoff" and must not be confused with "resolve it for me".
    """
    opp = _make_opportunity(db_session, "Explicit Cutoff Venue")
    db_session.add(
        ResearcherRecommendationFeedbackModel(
            id=uuid.uuid4(),
            researcher_id=profile.id,
            opportunity_id=opp.id,
            feedback_type="SAVE",
            source="RECOMMENDATION",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
    )
    db_session.commit()
    PersonalizationTransparencyService.reset_personalization(db_session, profile.id)

    # Explicit None: the caller asserts there is no cutoff, so the feedback is included.
    ignored_cutoff = ResearcherFeedbackService.get_behavioral_profile(
        db_session, profile.id, reset_cutoff=None
    )
    assert ignored_cutoff.signals, "explicit None must mean 'apply no cutoff'"

    # Omitted: the service resolves the stored cutoff and filters.
    resolved = ResearcherFeedbackService.get_behavioral_profile(db_session, profile.id)
    assert not resolved.signals


# ===========================================================================
# P1-2 — Calibration and contextual adaptation reach the live ranking path
# ===========================================================================


def test_p1_2_live_ranking_consumes_calibrations(
    db_session: Session, profile: ResearchProfileModel, monkeypatch
):
    """
    Calibrations were computed for the explanation endpoints only, so the explanation a
    researcher read could disagree with the ranking they were served. The live path must
    now pass them to the scorer.
    """
    _make_opportunity(db_session, "Calibrated Conference")
    _seed_adaptive_signal_and_calibration(db_session, profile)

    seen: dict[str, object] = {}
    from app.personalization.scorer import PersonalizationScorer

    original = PersonalizationScorer.score_opportunities_batch

    def _capture(*args, **kwargs):
        seen["calibrations"] = kwargs.get("calibrations")
        seen["contextual_adaptations"] = kwargs.get("contextual_adaptations")
        return original(*args, **kwargs)

    monkeypatch.setattr(PersonalizationScorer, "score_opportunities_batch", _capture)

    PersonalizationRankingService.get_personalized_recommendations(
        db=db_session, profile_id=profile.id, limit=10
    )

    assert seen.get("calibrations"), "live ranking must pass Phase 5.6 calibrations to the scorer"
    assert len(seen["calibrations"]) == 1


def test_p1_2_adaptive_toggle_withholds_calibrations(
    db_session: Session, profile: ResearchProfileModel, monkeypatch
):
    """Derived modifiers are gated by the researcher's adaptive-learning consent."""
    _make_opportunity(db_session, "Gated Conference")
    _seed_adaptive_signal_and_calibration(db_session, profile)
    db_session.add(
        ResearcherPersonalizationSettingsModel(
            id=uuid.uuid4(),
            profile_id=profile.id,
            personalization_enabled=True,
            adaptive_signals_enabled=False,
            feedback_learning_enabled=True,
            personalization_state_version=1,
        )
    )
    db_session.commit()

    seen: dict[str, object] = {}
    from app.personalization.scorer import PersonalizationScorer

    original = PersonalizationScorer.score_opportunities_batch

    def _capture(*args, **kwargs):
        seen["calibrations"] = kwargs.get("calibrations")
        return original(*args, **kwargs)

    monkeypatch.setattr(PersonalizationScorer, "score_opportunities_batch", _capture)

    PersonalizationRankingService.get_personalized_recommendations(
        db=db_session, profile_id=profile.id, limit=10
    )

    assert not seen.get("calibrations"), (
        "adaptive_signals_enabled=False must withhold derived calibration modifiers"
    )


# ===========================================================================
# P1-5 — Settings and governance lookups fail closed
# ===========================================================================


def test_p1_5_settings_read_failure_disables_personalization(
    db_session: Session, profile: ResearchProfileModel, monkeypatch
):
    """An unreadable controls row must not be treated as consent to personalize."""
    _make_opportunity(db_session, "Fail Closed Conference")

    real_execute = Session.execute

    def _explode_on_settings(self, statement, *args, **kwargs):
        if "researcher_personalization_settings" in str(statement):
            raise RuntimeError("simulated transient database failure")
        return real_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", _explode_on_settings)

    response = PersonalizationRankingService.get_personalized_recommendations(
        db=db_session, profile_id=profile.id, limit=10
    )

    assert response.personalization_enabled is False, (
        "a failed settings read must fail closed, not silently personalize"
    )


def test_p1_5_governance_read_failure_damps_to_hold(
    db_session: Session, profile: ResearchProfileModel, monkeypatch
):
    """An unreadable governance gate must not grant the unrestricted ALLOW multiplier."""
    from app.services import personalization_governance_service as gov_module

    def _explode(cls, db, profile_id):
        raise RuntimeError("simulated governance failure")

    monkeypatch.setattr(
        gov_module.PersonalizationGovernanceService,
        "get_active_governance_state",
        classmethod(_explode),
    )

    captured: dict[str, object] = {}
    from app.ranking.personalization_ranker import PersonalizationRanker

    original_rank = PersonalizationRanker.rank

    def _capture_rank(self, candidates, context, **kwargs):
        captured["governance_state"] = kwargs.get("governance_state")
        return original_rank(self, candidates, context, **kwargs)

    monkeypatch.setattr(PersonalizationRanker, "rank", _capture_rank)

    _make_opportunity(db_session, "Governance Failure Conference")
    PersonalizationRankingService.get_personalized_recommendations(
        db=db_session, profile_id=profile.id, limit=10
    )

    assert captured.get("governance_state") == GovernanceGateState.HOLD.value, (
        "governance read failure must damp to HOLD rather than ALLOW"
    )


def test_p1_5_absent_feature_table_applies_defaults_not_lockout():
    """
    A table that was never created means the feature is not deployed, which is different
    from a failed read: defaults apply instead of failing closed.
    """
    assert _is_missing_table_error(Exception("no such table: foo"))
    assert _is_missing_table_error(Exception('relation "foo" does not exist'))
    assert not _is_missing_table_error(RuntimeError("connection reset by peer"))


# ===========================================================================
# P1-7 — The risk gate sees the effective Phase 2.6 assessment
# ===========================================================================


def test_p1_7_effective_risk_reaches_base_relevance_ranking(
    db_session: Session, profile: ResearchProfileModel, monkeypatch
):
    """
    opportunities.risk_score is never written by ingestion, so reading the column left the
    base quality signal's predatory penalty inert. The effective in-memory assessment from
    candidate generation must be what the Phase 2 ranker sees.
    """
    _make_opportunity(db_session, "Flagged Venue", is_predatory=True)

    captured: dict[str, object] = {}
    from app.ranking.hybrid_ranker import HybridRanker

    original_rank = HybridRanker.rank

    def _capture(self, candidates, **kwargs):
        captured["candidates"] = list(candidates)
        return original_rank(self, candidates, **kwargs)

    monkeypatch.setattr(HybridRanker, "rank", _capture)

    PersonalizationRankingService.get_personalized_recommendations(
        db=db_session, profile_id=profile.id, limit=10
    )

    ranked_inputs = captured.get("candidates") or []
    assert ranked_inputs, "expected candidates to reach the base ranker"
    flagged = [c for c in ranked_inputs if c["is_predatory_flag"]]
    assert flagged, "the predatory flag must be visible to the base quality signal"
    assert flagged[0]["risk_score"] > 0.0, (
        "the base ranker must receive the effective Phase 2.6 risk score, not the "
        "never-written database column default"
    )


# ===========================================================================
# P1-8 — Governance tracks the signals it governs
# ===========================================================================


def test_p1_8_adaptive_recompute_refreshes_governance(
    db_session: Session, profile: ResearchProfileModel
):
    """
    Governance used to be recalculated only when the health or drift endpoint was read, so
    the gate damping live ranking could lag the behaviour it was meant to govern.
    """
    opp = _make_opportunity(db_session, "Governance Sync Conference")
    for i in range(6):
        db_session.add(
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile.id,
                opportunity_id=opp.id,
                interaction_type=InteractionType.INTERESTED.value,
                client_event_id=f"gov-sync-{i}",
                created_at=datetime.now(timezone.utc),
            )
        )
    db_session.commit()

    assert db_session.execute(
        select(PersonalizationDriftEvaluationModel).where(
            PersonalizationDriftEvaluationModel.profile_id == profile.id
        )
    ).scalars().first() is None

    AdaptivePreferenceSignalService.recompute_adaptive_signals(db_session, profile.id)
    db_session.commit()

    evaluation = db_session.execute(
        select(PersonalizationDriftEvaluationModel).where(
            PersonalizationDriftEvaluationModel.profile_id == profile.id
        )
    ).scalars().first()
    assert evaluation is not None, (
        "recomputing adaptive signals must also refresh the governance gate"
    )


def test_p1_8_governance_failure_does_not_discard_signal_recompute(
    db_session: Session, profile: ResearchProfileModel, monkeypatch
):
    """A governance error must not lose a valid adaptive signal recomputation."""
    opp = _make_opportunity(db_session, "Resilient Recompute Conference")
    for i in range(8):
        db_session.add(
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile.id,
                opportunity_id=opp.id,
                interaction_type=InteractionType.INTERESTED.value,
                client_event_id=f"resilient-{i}",
                created_at=datetime.now(timezone.utc),
            )
        )
    db_session.commit()

    from app.services import personalization_governance_service as gov_module

    def _explode(cls, **kwargs):
        raise RuntimeError("simulated governance failure")

    monkeypatch.setattr(
        gov_module.PersonalizationGovernanceService,
        "recompute_governance",
        classmethod(_explode),
    )

    signals = AdaptivePreferenceSignalService.recompute_adaptive_signals(db_session, profile.id)
    db_session.commit()
    assert signals, "signal recomputation must survive a governance failure"


# ===========================================================================
# P1-12 — Unknown identifiers are rejected
# ===========================================================================


def test_p1_12_unknown_identifier_is_rejected(db_session: Session):
    """Passing an unknown UUID through created workspace rows owned by nobody."""
    with pytest.raises(ValueError, match="does not match any user account"):
        WorkspaceService.resolve_user_id(db_session, uuid.uuid4())


def test_p1_12_user_and_profile_identifiers_still_resolve(
    db_session: Session, profile: ResearchProfileModel
):
    """Both accepted identifier forms continue to resolve to the canonical user id."""
    assert WorkspaceService.resolve_user_id(db_session, profile.user_id) == profile.user_id
    assert WorkspaceService.resolve_user_id(db_session, profile.id) == profile.user_id
