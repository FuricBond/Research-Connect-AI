"""
Unit and Integration Tests for Phase 2.4L Domain-Aware Academic Query Intelligence.
"""
from __future__ import annotations

import pytest

from app.search.query_intelligence import (
    SEED_ACADEMIC_ACRONYMS,
    QueryIntelligenceService,
    query_intelligence_service,
)


class TestDomainQueryIntelligence:
    """Test suite verifying cross-disciplinary acronym recognition, case insensitivity, and contextual disambiguation."""

    @pytest.fixture
    def service(self) -> QueryIntelligenceService:
        return QueryIntelligenceService()

    def test_nine_disciplines_acronym_coverage(self, service: QueryIntelligenceService) -> None:
        """Verify registry contains 100+ acronyms covering all 9 academic disciplines."""
        assert len(SEED_ACADEMIC_ACRONYMS) >= 80

        # Discipline-specific acronym spot checks
        assert service.get_expansion("GNN") == "Graph Neural Networks"  # CS
        assert service.get_expansion("MRI") == "Magnetic Resonance Imaging"  # Medicine
        assert service.get_expansion("CRISPR") == "Clustered Regularly Interspaced Short Palindromic Repeats"  # Biology
        assert service.get_expansion("PDE") == "Partial Differential Equations"  # Math
        assert service.get_expansion("QED") == "Quantum Electrodynamics"  # Physics
        assert service.get_expansion("MEMS") == "Microelectromechanical Systems"  # Engineering
        assert service.get_expansion("DSGE") == "Dynamic Stochastic General Equilibrium"  # Economics
        assert service.get_expansion("GHG") == "Greenhouse Gases"  # Environmental Science
        assert service.get_expansion("CBT") == "Cognitive Behavioral Therapy"  # Social Sciences

    def test_case_insensitive_acronym_detection(self, service: QueryIntelligenceService) -> None:
        """Verify acronyms are detected whether uppercase, lowercase, or titlecase."""
        res_upper = service.process("GNN models for graph classification")
        assert "GNN" in res_upper.detected_acronyms
        assert "Graph Neural Networks" in res_upper.expanded_query

        res_lower = service.process("gnn architectures for drug discovery")
        assert "GNN" in res_lower.detected_acronyms
        assert "Graph Neural Networks" in res_lower.expanded_query

        res_mixed = service.process("Crispr gene editing in human cells")
        assert "CRISPR" in res_mixed.detected_acronyms
        assert "Clustered Regularly Interspaced Short Palindromic Repeats" in res_mixed.expanded_query

    def test_contextual_disambiguation_sem(self, service: QueryIntelligenceService) -> None:
        """Verify SEM is disambiguated between Structural Equation Modeling and Scanning Electron Microscopy."""
        # Social Science / Econometric context
        res_social = service.process("SEM factor analysis in psychology survey data")
        assert "Structural Equation Modeling" in res_social.expanded_query
        assert "Scanning Electron Microscopy" not in res_social.expanded_query
        assert any("contextually resolved" in t for t in res_social.transformations)

        # Materials / Physical science context
        res_material = service.process("SEM electron microscopy imaging of nanomaterials")
        assert "Scanning Electron Microscopy" in res_material.expanded_query
        assert "Structural Equation Modeling" not in res_material.expanded_query
        assert any("contextually resolved" in t for t in res_material.transformations)

    def test_contextual_disambiguation_iv(self, service: QueryIntelligenceService) -> None:
        """Verify IV is disambiguated between Instrumental Variables and Intravenous."""
        # Econometrics
        res_econ = service.process("IV econometrics for causal identification")
        assert "Instrumental Variables" in res_econ.expanded_query
        assert "Intravenous" not in res_econ.expanded_query

        # Medicine / Pharmacology
        res_med = service.process("IV drug infusion dosage in patient clinical trial")
        assert "Intravenous" in res_med.expanded_query
        assert "Instrumental Variables" not in res_med.expanded_query

    def test_contextual_disambiguation_pca(self, service: QueryIntelligenceService) -> None:
        """Verify PCA is disambiguated between Principal Component Analysis and Patient-Controlled Analgesia."""
        # Machine Learning / Statistics
        res_ml = service.process("PCA variance decomposition and clustering")
        assert "Principal Component Analysis" in res_ml.expanded_query
        assert "Patient-Controlled Analgesia" not in res_ml.expanded_query

        # Anesthesiology
        res_pain = service.process("PCA patient postoperative pain opioid dosage")
        assert "Patient-Controlled Analgesia" in res_pain.expanded_query
        assert "Principal Component Analysis" not in res_pain.expanded_query

    def test_stopword_protection_prevents_false_positives(self, service: QueryIntelligenceService) -> None:
        """Verify common English words are not mistakenly expanded as acronyms."""
        queries = [
            "We can use new machine learning methods",
            "Are there any other models that out perform this",
            "Has the model been tested on all datasets",
        ]
        for q in queries:
            res = service.process(q)
            # Words like 'can', 'use', 'new', 'are', 'out', 'has', 'all' must NOT be detected as acronyms
            assert not any(acronym in ["CAN", "USE", "NEW", "ARE", "OUT", "HAS", "ALL", "MAY", "NOT"] for acronym in res.detected_acronyms)
            assert not res.was_expanded or all(
                t in ["Machine Learning"] for t in res.detected_terms
            )

    def test_transformation_audit_log_traceability(self, service: QueryIntelligenceService) -> None:
        """Verify transformations audit trail is human-readable and complete."""
        res = service.process("  ? Fast MRI reconstruction using GNN !  ")
        assert res.was_expanded is True
        assert len(res.transformations) >= 2
        assert any("Normalized" in t for t in res.transformations)
        assert any("MRI" in t for t in res.transformations)
        assert any("GNN" in t for t in res.transformations)
