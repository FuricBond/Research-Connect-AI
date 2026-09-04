"""
Risk & Trust Intelligence Layer for Phase 2.6.

Exports structured evidence models, pattern matchers, registries, extraction services,
and the deterministic risk scoring engine.
"""
from app.ranking.risk.engine import RiskEvidenceExtractor, risk_evidence_extractor
from app.ranking.risk.models import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceProvenance,
    EvidenceSignal,
    EvidenceStrength,
    ResolutionStatus,
    ResolvedAcademicEntity,
    RiskAssessment,
    RiskEvidence,
    RiskEvidenceCollection,
    RiskLevel,
)
from app.ranking.risk.graph import (
    AcademicTrustGraph,
    GraphBuilder,
    SuspiciousGraphAnalyzer,
    SuspiciousGraphService,
    TrustEdge,
    TrustEdgeType,
    TrustNode,
    TrustNodeType,
    project_graph_evidence,
    suspicious_graph_service,
)
from app.ranking.risk.scoring import (
    DeterministicRiskScoringEngine,
    RiskScoringConfig,
    assess_opportunity_risk,
    risk_scoring_engine,
)
from app.ranking.risk.venue_intelligence import (
    KNOWN_DOI_PREFIXES,
    PUBLISHER_DOMAINS,
    VenuePublisherIntelligenceService,
    venue_publisher_intelligence_service,
)

__all__ = [
    "AcademicTrustGraph",
    "DeterministicRiskScoringEngine",
    "EvidenceCategory",
    "EvidenceConfidence",
    "EvidenceProvenance",
    "EvidenceSignal",
    "EvidenceStrength",
    "GraphBuilder",
    "KNOWN_DOI_PREFIXES",
    "PUBLISHER_DOMAINS",
    "ResolutionStatus",
    "ResolvedAcademicEntity",
    "RiskAssessment",
    "RiskEvidence",
    "RiskEvidenceCollection",
    "RiskEvidenceExtractor",
    "RiskLevel",
    "RiskScoringConfig",
    "SuspiciousGraphAnalyzer",
    "SuspiciousGraphService",
    "TrustEdge",
    "TrustEdgeType",
    "TrustNode",
    "TrustNodeType",
    "VenuePublisherIntelligenceService",
    "assess_opportunity_risk",
    "project_graph_evidence",
    "risk_evidence_extractor",
    "risk_scoring_engine",
    "suspicious_graph_service",
    "venue_publisher_intelligence_service",
]

