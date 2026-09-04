"""
Phase 2.5F — Explainable Results Package.

Exports:
  - ResultExplainer: Deterministic explanation engine.
  - ResultExplanation: Machine- and human-readable explanation container.
  - ExplainedResult: Result envelope pairing candidate with explanation.
  - SignalContribution: Normalized individual signal contribution model.
  - ScoreBreakdown: Detailed mathematical breakdown of subtotals and score reconciliation.
  - AcademicQualityEvidence: Structured academic quality and venue intelligence evidence.
  - RerankerExplanation: Cross-encoder reranking attribution model.
  - DiversityExplanation: List-aware diversity and novelty attribution model.
  - ComparativeExplanation: Deterministic comparison between two ranked candidates.
  - TopicEvidence: Canonical topic overlap evidence.
  - ProvenanceEvidence: Retrieval channel provenance evidence.
  - result_explainer: Singleton default explainer instance.
"""
from app.explainability.result_explainer import (
    AcademicQualityEvidence,
    ComparativeExplanation,
    DiversityExplanation,
    ExplainedResult,
    ProvenanceEvidence,
    RerankerExplanation,
    ResultExplainer,
    ResultExplanation,
    ScoreBreakdown,
    SignalContribution,
    TopicEvidence,
    result_explainer,
)

__all__ = [
    "AcademicQualityEvidence",
    "ComparativeExplanation",
    "DiversityExplanation",
    "ExplainedResult",
    "ProvenanceEvidence",
    "RerankerExplanation",
    "ResultExplainer",
    "ResultExplanation",
    "ScoreBreakdown",
    "SignalContribution",
    "TopicEvidence",
    "result_explainer",
]

