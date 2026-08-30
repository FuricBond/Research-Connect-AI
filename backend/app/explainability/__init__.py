"""
Phase 2.4F — Explainable Results Package.

Exports:
  - ResultExplainer: Deterministic explanation engine.
  - ResultExplanation: Machine- and human-readable explanation container.
  - ExplainedResult: Result envelope pairing candidate with explanation.
  - SignalContribution: Normalized individual signal contribution model.
  - TopicEvidence: Canonical topic overlap evidence.
  - ProvenanceEvidence: Retrieval channel provenance evidence.
  - result_explainer: Singleton default explainer instance.
"""
from app.explainability.result_explainer import (
    ExplainedResult,
    ProvenanceEvidence,
    ResultExplainer,
    ResultExplanation,
    SignalContribution,
    TopicEvidence,
    result_explainer,
)

__all__ = [
    "ExplainedResult",
    "ProvenanceEvidence",
    "ResultExplainer",
    "ResultExplanation",
    "SignalContribution",
    "TopicEvidence",
    "result_explainer",
]
