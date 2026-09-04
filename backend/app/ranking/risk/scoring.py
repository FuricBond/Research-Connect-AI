"""
Deterministic Risk Scoring Engine for Phase 2.6C.

Transforms a structured RiskEvidenceCollection into a calibrated, bounded risk score
[0.00, 1.00], categorical risk level (LOW_RISK, MODERATE_RISK, HIGH_RISK, INSUFFICIENT_EVIDENCE),
evidence confidence, and deterministic human-readable reasons.

Enforces:
  1. UNKNOWN != PREDATORY (Missing metadata lowers confidence, never creates high risk).
  2. Bounded mathematical formulation [0.00, 1.00].
  3. Anti-correlation & diminishing returns for correlated signals.
  4. Positive trust mitigation (trust reduces risk without absolute blind spots).
  5. 100% offline, zero database queries, zero network calls, strictly deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ranking.risk.engine import risk_evidence_extractor
from app.ranking.risk.models import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceProvenance,
    EvidenceSignal,
    EvidenceStrength,
    RiskAssessment,
    RiskEvidence,
    RiskEvidenceCollection,
    RiskLevel,
)


@dataclass(frozen=True)
class RiskScoringConfig:
    """
    Centralized configuration and weights for deterministic risk scoring.
    """

    # ── Strength Multipliers ──────────────────────────────────────────────────
    strength_multipliers: dict[EvidenceStrength, float] = field(
        default_factory=lambda: {
            EvidenceStrength.STRONG: 1.00,
            EvidenceStrength.MODERATE: 0.60,
            EvidenceStrength.WEAK: 0.30,
            EvidenceStrength.NONE: 0.00,
        }
    )

    # ── Confidence Multipliers ────────────────────────────────────────────────
    confidence_multipliers: dict[EvidenceConfidence, float] = field(
        default_factory=lambda: {
            EvidenceConfidence.HIGH: 1.00,
            EvidenceConfidence.MEDIUM: 0.75,
            EvidenceConfidence.LOW: 0.50,
        }
    )

    # ── Provenance Reliability Multipliers ────────────────────────────────────
    provenance_weights: dict[EvidenceProvenance, float] = field(
        default_factory=lambda: {
            EvidenceProvenance.STATIC_TRUST_REGISTRY: 1.00,
            EvidenceProvenance.EXTERNAL_VERIFICATION: 0.95,
            EvidenceProvenance.NORMALIZED_METADATA: 0.90,
            EvidenceProvenance.SCRAPED_METADATA: 0.75,
            EvidenceProvenance.DERIVED: 0.70,
            EvidenceProvenance.UNKNOWN: 0.30,
        }
    )

    # ── Base Negative Signal Weights ──────────────────────────────────────────
    negative_signal_weights: dict[str, float] = field(
        default_factory=lambda: {
            EvidenceSignal.SUSPICIOUS_PAYMENT_LANGUAGE.value: 0.55,
            EvidenceSignal.SUSPICIOUS_REVIEW_CLAIM.value: 0.55,
            EvidenceSignal.SUSPICIOUS_EDITORIAL_CLAIM.value: 0.45,
            EvidenceSignal.SUSPICIOUS_DOMAIN.value: 0.45,
            EvidenceSignal.SUSPICIOUS_PUBLISHER_PATTERN.value: 0.50,
            EvidenceSignal.SUSPICIOUS_CONTACT_PATTERN.value: 0.35,
            EvidenceSignal.UNVERIFIABLE_CLAIM.value: 0.30,
            EvidenceSignal.CONFLICTING_METADATA.value: 0.20,
        }
    )

    # ── Base Positive Trust Signal Weights ────────────────────────────────────
    positive_signal_weights: dict[str, float] = field(
        default_factory=lambda: {
            EvidenceSignal.VERIFIED_PUBLISHER.value: 0.40,
            EvidenceSignal.VERIFIED_PUBLISHER_IDENTITY.value: 0.40,
            EvidenceSignal.VERIFIED_SOCIETY.value: 0.35,
            EvidenceSignal.VERIFIED_VENUE.value: 0.35,
            EvidenceSignal.VERIFIED_VENUE_IDENTITY.value: 0.40,
            EvidenceSignal.VERIFIED_INDEXING.value: 0.35,
            EvidenceSignal.DOAJ_INDEXED.value: 0.30,
            EvidenceSignal.VALID_ISSN.value: 0.15,
            EvidenceSignal.VERIFIED_ISSN_L.value: 0.20,
            EvidenceSignal.VALID_DOI.value: 0.15,
            EvidenceSignal.PUBLISHER_DOMAIN_MATCH.value: 0.25,
            EvidenceSignal.OPENALEX_METADATA_MATCH.value: 0.20,
            EvidenceSignal.CROSSREF_METADATA_MATCH.value: 0.15,
            EvidenceSignal.TRANSPARENT_PEER_REVIEW.value: 0.10,
            EvidenceSignal.TRANSPARENT_FEE_STRUCTURE.value: 0.10,
        }
    )

    # ── Signal Group Mapping (for anti-correlation caps) ──────────────────────
    signal_groups: dict[str, str] = field(
        default_factory=lambda: {
            EvidenceSignal.SUSPICIOUS_PAYMENT_LANGUAGE.value: "PAYMENT",
            EvidenceSignal.SUSPICIOUS_REVIEW_CLAIM.value: "REVIEW",
            EvidenceSignal.SUSPICIOUS_EDITORIAL_CLAIM.value: "EDITORIAL",
            EvidenceSignal.SUSPICIOUS_DOMAIN.value: "DOMAIN",
            EvidenceSignal.SUSPICIOUS_PUBLISHER_PATTERN.value: "PUBLISHER",
            EvidenceSignal.SUSPICIOUS_CONTACT_PATTERN.value: "CONTACT",
            EvidenceSignal.UNVERIFIABLE_CLAIM.value: "GENERAL",
            EvidenceSignal.CONFLICTING_METADATA.value: "EDITORIAL",
        }
    )

    # ── Group Contribution Caps ───────────────────────────────────────────────
    group_caps: dict[str, float] = field(
        default_factory=lambda: {
            "PAYMENT": 0.65,
            "REVIEW": 0.65,
            "EDITORIAL": 0.50,
            "DOMAIN": 0.50,
            "PUBLISHER": 0.55,
            "CONTACT": 0.40,
            "GENERAL": 0.40,
        }
    )

    # Correlation decay within the same group: contribution_i = base * (decay ^ i)
    group_decay_factor: float = 0.50

    # Trust mitigation limit: trust can damp at most 65% of negative suspicious score
    max_trust_mitigation_ratio: float = 0.65

    # ── Risk Level Thresholds ─────────────────────────────────────────────────
    high_risk_threshold: float = 0.70
    moderate_risk_threshold: float = 0.30

    # Minimum confidence to permit HIGH_RISK classification
    min_confidence_for_high_risk: float = 0.40

    # Minimum confidence for is_predatory_flag=True
    min_confidence_for_predatory_flag: float = 0.50

    # Confidence threshold to distinguish LOW_RISK from INSUFFICIENT_EVIDENCE
    confidence_sufficient_threshold: float = 0.40


class DeterministicRiskScoringEngine:
    """
    Deterministic scoring engine consuming a RiskEvidenceCollection and producing
    a calibrated RiskAssessment.
    """

    def __init__(self, config: RiskScoringConfig | None = None) -> None:
        self.config = config or RiskScoringConfig()

    def score(self, evidence_collection: RiskEvidenceCollection) -> RiskAssessment:
        """
        Compute deterministic risk assessment for an evidence collection.

        Parameters
        ----------
        evidence_collection:
            RiskEvidenceCollection extracted by Phase 2.6B.

        Returns
        -------
        RiskAssessment
            Calibrated numerical risk score, risk level, confidence, and structured reasons.
        """
        cfg = self.config

        # 1. Calculate Gross Negative Suspicious Score with Group Diminishing Returns
        negative_items = sorted(
            evidence_collection.negative_evidence,
            key=lambda e: (e.signal, e.source_field, str(e.matched_value)),
        )

        grouped_negative_weights: dict[str, list[float]] = {}
        for item in negative_items:
            base_w = cfg.negative_signal_weights.get(item.signal, 0.30)
            str_mult = cfg.strength_multipliers.get(item.strength, 0.00)
            conf_mult = cfg.confidence_multipliers.get(item.confidence, 0.50)
            effective_w = base_w * str_mult * conf_mult

            group = cfg.signal_groups.get(item.signal, "GENERAL")
            grouped_negative_weights.setdefault(group, []).append(effective_w)

        gross_negative = 0.0
        for group, weights in grouped_negative_weights.items():
            # Sort descending: strongest signal in group has full weight, subsequent decay
            weights.sort(reverse=True)
            decayed_sum = 0.0
            for i, w in enumerate(weights):
                decayed_sum += w * (cfg.group_decay_factor ** i)

            group_cap = cfg.group_caps.get(group, 0.50)
            gross_negative += min(group_cap, decayed_sum)

        gross_negative = min(1.00, gross_negative)

        # 2. Calculate Positive Trust Score
        positive_items = sorted(
            evidence_collection.positive_evidence,
            key=lambda e: (e.signal, e.source_field, str(e.matched_value)),
        )

        gross_positive = 0.0
        for item in positive_items:
            base_w = cfg.positive_signal_weights.get(item.signal, 0.20)
            str_mult = cfg.strength_multipliers.get(item.strength, 0.00)
            conf_mult = cfg.confidence_multipliers.get(item.confidence, 0.50)
            effective_w = base_w * str_mult * conf_mult
            gross_positive += effective_w

        gross_positive = min(1.00, gross_positive)

        # 3. Apply Trust Mitigation with Cap
        # Trust evidence dampens negative score, but cannot exceed max_trust_mitigation_ratio
        if gross_negative > 0.0:
            max_allowed_mitigation = gross_negative * cfg.max_trust_mitigation_ratio
            trust_mitigation = min(max_allowed_mitigation, gross_positive)
        else:
            trust_mitigation = 0.0

        # 4. Compute Final Bounded Risk Score
        final_risk_score = round(max(0.00, min(1.00, gross_negative - trust_mitigation)), 2)

        # 5. Compute Risk Assessment Confidence
        risk_confidence = self._calculate_confidence(evidence_collection)

        # 6. Classify Risk Level
        risk_level = self._classify_risk_level(
            final_risk_score,
            risk_confidence,
            evidence_collection,
        )

        # 7. Determine Legacy is_predatory_flag
        is_predatory = self._determine_is_predatory(
            final_risk_score,
            risk_level,
            risk_confidence,
            evidence_collection,
        )

        # 8. Generate Structured Risk Reasons & Dominant Signals
        reasons, dominant_signals = self._generate_reasons_and_signals(
            evidence_collection,
            risk_level,
            final_risk_score,
            trust_mitigation,
        )

        return RiskAssessment(
            opportunity_id=evidence_collection.opportunity_id,
            risk_score=final_risk_score,
            risk_level=risk_level,
            risk_confidence=risk_confidence,
            is_predatory_flag=is_predatory,
            risk_reasons=reasons,
            dominant_signals=dominant_signals,
            gross_negative_score=round(gross_negative, 4),
            trust_mitigation_score=round(trust_mitigation, 4),
            evidence_collection=evidence_collection,
        )

    def assess_opportunity(self, opportunity: Any) -> RiskAssessment:
        """
        Convenience end-to-end method: extracts evidence and scores in one step.
        """
        evidence_col = risk_evidence_extractor.extract(opportunity)
        return self.score(evidence_col)

    def score_batch(self, collections: list[RiskEvidenceCollection]) -> list[RiskAssessment]:
        """Score a batch of evidence collections in-memory."""
        return [self.score(col) for col in collections]

    def _calculate_confidence(self, collection: RiskEvidenceCollection) -> float:
        """
        Deterministically calculate assessment confidence in range [0.00, 1.00].
        Reflects metadata completeness, evidence provenance, and signal depth.
        """
        cfg = self.config

        # 1. Metadata completeness contribution (40%)
        completeness_contrib = collection.metadata_completeness_score * 0.40

        # 2. Provenance reliability contribution (35%)
        affirmative_items = [item for item in collection.items if item.is_present]
        if affirmative_items:
            prov_scores = [
                cfg.provenance_weights.get(item.provenance, 0.70)
                for item in affirmative_items
            ]
            provenance_contrib = (sum(prov_scores) / len(prov_scores)) * 0.35
        else:
            provenance_contrib = 0.10

        # 3. Evidence depth contribution (25%)
        # Caps at 4 distinct affirmative signals
        signal_depth = min(1.0, len(affirmative_items) / 4.0)
        depth_contrib = signal_depth * 0.25

        confidence = completeness_contrib + provenance_contrib + depth_contrib
        return round(max(0.05, min(1.00, confidence)), 2)

    def _classify_risk_level(
        self,
        risk_score: float,
        confidence: float,
        collection: RiskEvidenceCollection,
    ) -> RiskLevel:
        """
        Classify risk level with strict safeguard:
        INSUFFICIENT_EVIDENCE != HIGH_RISK.
        """
        cfg = self.config

        if risk_score >= cfg.high_risk_threshold and collection.has_suspicious_evidence:
            if confidence >= cfg.min_confidence_for_high_risk:
                return RiskLevel.HIGH_RISK
            else:
                # Conservative downgrade if confidence is too low
                return RiskLevel.MODERATE_RISK

        elif risk_score >= cfg.moderate_risk_threshold:
            return RiskLevel.MODERATE_RISK

        else:
            # Low risk score (< 0.30)
            # Distinguish genuine LOW_RISK from INSUFFICIENT_EVIDENCE
            if (
                confidence < cfg.confidence_sufficient_threshold
                and not collection.has_trust_evidence
                and not collection.has_suspicious_evidence
            ):
                return RiskLevel.INSUFFICIENT_EVIDENCE
            return RiskLevel.LOW_RISK

    def _determine_is_predatory(
        self,
        risk_score: float,
        level: RiskLevel,
        confidence: float,
        collection: RiskEvidenceCollection,
    ) -> bool:
        """
        Determine whether opportunity meets criteria for legacy is_predatory_flag=True.
        Requires high risk and corroborating evidence.
        """
        cfg = self.config

        if level != RiskLevel.HIGH_RISK:
            return False

        # Flag predatory if confidence >= 0.50 OR multiple strong suspicious signals
        if confidence >= cfg.min_confidence_for_predatory_flag:
            return True

        if len(collection.strong_suspicious_signals) >= 2:
            return True

        return False

    def _generate_reasons_and_signals(
        self,
        collection: RiskEvidenceCollection,
        risk_level: RiskLevel,
        risk_score: float,
        trust_mitigation: float,
    ) -> tuple[list[str], list[str]]:
        """
        Generate deterministic ordered human-readable reasons and dominant signals.
        """
        reasons: list[str] = []
        dominant_signals: list[str] = []

        # 1. Strong suspicious signals first
        strong_neg = sorted(
            collection.strong_suspicious_signals,
            key=lambda e: (e.signal, e.source_field, str(e.matched_value)),
        )
        for item in strong_neg:
            msg = f"High Risk: {item.explanation}"
            if msg not in reasons:
                reasons.append(msg)
            if item.signal not in dominant_signals:
                dominant_signals.append(item.signal)

        # 2. Moderate suspicious signals
        mod_neg = sorted(
            [e for e in collection.negative_evidence if e.strength == EvidenceStrength.MODERATE],
            key=lambda e: (e.signal, e.source_field, str(e.matched_value)),
        )
        for item in mod_neg:
            msg = f"Cautionary Risk: {item.explanation}"
            if msg not in reasons:
                reasons.append(msg)
            if item.signal not in dominant_signals:
                dominant_signals.append(item.signal)

        # 3. Positive Trust Evidence
        trust_items = sorted(
            collection.positive_evidence,
            key=lambda e: (e.strength.value, e.signal, e.source_field),
            reverse=True,
        )
        for item in trust_items:
            msg = f"Trust Evidence: {item.explanation}"
            if msg not in reasons:
                reasons.append(msg)
            if item.signal not in dominant_signals:
                dominant_signals.append(item.signal)

        # 4. Contextual summary reasons if list is empty or level is special
        if risk_level == RiskLevel.INSUFFICIENT_EVIDENCE:
            reasons.append(
                "Insufficient metadata available to establish venue authenticity (neutral assessment)."
            )
        elif risk_level == RiskLevel.LOW_RISK and not reasons:
            reasons.append("Opportunity exhibits standard academic characteristics with zero suspicious indicators.")

        if trust_mitigation > 0.0 and collection.has_suspicious_evidence:
            reasons.append(
                f"Suspicious risk partially mitigated (-{trust_mitigation:.2f}) by verified publisher or indexing records."
            )

        return reasons, dominant_signals


# Global singleton
risk_scoring_engine = DeterministicRiskScoringEngine()


def assess_opportunity_risk(opportunity: Any) -> RiskAssessment:
    """
    Convenience functional API for end-to-end risk assessment.
    """
    return risk_scoring_engine.assess_opportunity(opportunity)
