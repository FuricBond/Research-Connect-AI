"""
Unit tests for Academic Query Intelligence in app.search.query_intelligence.
"""
from __future__ import annotations

import pytest

from app.search.query_intelligence import (
    QueryIntelligenceResult,
    QueryIntelligenceService,
    query_intelligence_service,
)


class TestQueryIntelligenceNormalization:
    """Tests for whitespace, punctuation, and casing normalization."""

    def test_empty_and_whitespace_queries(self):
        svc = QueryIntelligenceService()
        assert svc.normalize("") == ""
        assert svc.normalize("   ") == ""
        assert svc.normalize("\t\n  \r\n") == ""
        assert svc.normalize(None) == ""

        res = svc.process("")
        assert res.original_query == ""
        assert res.normalized_query == ""
        assert res.expanded_query == ""
        assert res.was_expanded is False
        assert res.detected_acronyms == []
        assert res.detected_terms == []

    def test_whitespace_collapsing(self):
        svc = QueryIntelligenceService()
        raw = "  Graph    Neural   Networks   \t for   molecular \n prediction  "
        normalized = svc.normalize(raw)
        assert normalized == "Graph Neural Networks for molecular prediction"

    def test_punctuation_stripping(self):
        svc = QueryIntelligenceService()
        assert svc.normalize("?What is machine learning?!") == "What is machine learning"
        assert svc.normalize("  [deep learning] (methods)... ") == "deep learning] (methods"  # strips outer punctuation
        assert svc.normalize('"reinforcement learning"') == "reinforcement learning"

    def test_preserves_internal_hyphens(self):
        svc = QueryIntelligenceService()
        assert svc.normalize("multi-agent reinforcement learning") == "multi-agent reinforcement learning"
        assert svc.normalize("graph-based semi-supervised learning") == "graph-based semi-supervised learning"


class TestAcademicAcronymExpansion:
    """Tests for academic acronym identification and expansion."""

    def test_single_known_acronym_expansion(self):
        svc = QueryIntelligenceService()
        res = svc.process("GNN for molecular property prediction")
        assert res.original_query == "GNN for molecular property prediction"
        assert res.normalized_query == "GNN for molecular property prediction"
        assert "GNN" in res.detected_acronyms
        assert "Graph Neural Networks" in res.detected_terms
        assert res.was_expanded is True
        assert res.expanded_query == "GNN for molecular property prediction Graph Neural Networks"
        assert any("GNN" in t and "Graph Neural Networks" in t for t in res.transformations)

    def test_multiple_acronyms_expansion(self):
        svc = QueryIntelligenceService()
        res = svc.process("Combining LLM and RAG for biomedical QA")
        assert "LLM" in res.detected_acronyms
        assert "RAG" in res.detected_acronyms
        assert "QA" in res.detected_acronyms
        assert "Large Language Models" in res.detected_terms
        assert "Retrieval-Augmented Generation" in res.detected_terms
        assert "Question Answering" in res.detected_terms
        assert res.was_expanded is True
        assert "Large Language Models" in res.expanded_query
        assert "Retrieval-Augmented Generation" in res.expanded_query
        assert "Question Answering" in res.expanded_query

    def test_no_duplicate_expansion_if_term_already_present(self):
        svc = QueryIntelligenceService()
        # Query already contains the full phrase "Graph Neural Networks" alongside GNN
        res = svc.process("GNN and Graph Neural Networks benchmarks")
        assert "GNN" in res.detected_acronyms
        assert res.was_expanded is True
        # Since "Graph Neural Networks" was already in the query, it should not be appended again
        assert res.expanded_query.count("Graph Neural Networks") == 1

    def test_unknown_acronym_preservation(self):
        svc = QueryIntelligenceService()
        res = svc.process("Novel XYZ protocol for ABC systems")
        assert res.detected_acronyms == []
        assert res.detected_terms == []
        assert res.was_expanded is False
        assert res.expanded_query == "Novel XYZ protocol for ABC systems"

    def test_false_positive_prevention_on_stopwords(self):
        svc = QueryIntelligenceService()
        # Capitalized English words should not trigger spurious acronyms
        res = svc.process("AN ANALYSIS OF DATA IN A DISTRIBUTED SYSTEM FOR US")
        # 'A', 'AN', 'IN', 'FOR', 'US' are stopwords
        assert "A" not in res.detected_acronyms
        assert "AN" not in res.detected_acronyms
        assert "IN" not in res.detected_acronyms
        assert "FOR" not in res.detected_acronyms
        assert "US" not in res.detected_acronyms
        assert res.was_expanded is False

    def test_custom_acronym_registration(self):
        svc = QueryIntelligenceService()
        svc.register_acronym("MYALG", "My Custom Machine Learning Algorithm")
        assert svc.get_expansion("MYALG") == "My Custom Machine Learning Algorithm"

        res = svc.process("Benchmarks for MYALG in 2026")
        assert "MYALG" in res.detected_acronyms
        assert "My Custom Machine Learning Algorithm" in res.detected_terms
        assert "My Custom Machine Learning Algorithm" in res.expanded_query
        assert res.was_expanded is True

    def test_deterministic_repeated_execution(self):
        svc = QueryIntelligenceService()
        q = "Self-supervised GNN and CNN for CV"
        res1 = svc.process(q)
        res2 = svc.process(q)
        res3 = svc.process(q)

        assert res1.expanded_query == res2.expanded_query == res3.expanded_query
        assert res1.detected_acronyms == res2.detected_acronyms == res3.detected_acronyms
        assert res1.detected_terms == res2.detected_terms == res3.detected_terms
        assert res1.transformations == res2.transformations == res3.transformations
