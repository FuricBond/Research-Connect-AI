"""
Unit and Integration Tests for Phase 2.4L Taxonomy Expansion.
"""
from __future__ import annotations

import pytest

from ml.topic_analysis.taxonomy import SEED_TAXONOMY, TaxonomyService, TaxonomyNode


class TestTaxonomyExpansion:
    """Test suite verifying Track A taxonomy expansion quality, coverage, and backward compatibility."""

    @pytest.fixture
    def taxonomy_service(self) -> TaxonomyService:
        return TaxonomyService()

    def test_node_count_exceeds_minimum(self, taxonomy_service: TaxonomyService) -> None:
        """Verify taxonomy contains at least 150 canonical topic nodes (target 180+)."""
        nodes = taxonomy_service.get_all_nodes()
        assert len(nodes) >= 150, f"Expected at least 150 nodes, found {len(nodes)}"
        assert len(nodes) >= 180, f"Expected >=180 nodes for comprehensive coverage, found {len(nodes)}"

    def test_nine_disciplinary_roots_represented(self, taxonomy_service: TaxonomyService) -> None:
        """Verify all 9 major academic disciplines are represented as root nodes."""
        expected_roots = {
            "computer-science",
            "medicine",
            "biology",
            "mathematics",
            "physics",
            "engineering",
            "social-sciences",
            "economics",
            "environmental-science",
        }
        actual_roots = {node.slug for node in taxonomy_service.get_all_nodes() if node.parent_slug is None}
        assert expected_roots == actual_roots, f"Root mismatch. Missing: {expected_roots - actual_roots}, Extra: {actual_roots - expected_roots}"

    def test_disciplinary_balance_improvement(self, taxonomy_service: TaxonomyService) -> None:
        """Verify Computer Science is no longer heavily dominant (previous 66.7% -> <= 20%)."""
        report = taxonomy_service.generate_coverage_report()
        cs_pct = report["discipline_percentages"]["Computer Science"]
        assert cs_pct <= 22.0, f"CS concentration should be <= 22%, got {cs_pct}%"

        # Verify all 9 disciplines have meaningful representations (>5% each)
        for disc, pct in report["discipline_percentages"].items():
            assert pct >= 5.0, f"Discipline {disc} has insufficient coverage ({pct}%)"

    def test_dag_cycle_freedom_and_zero_orphans(self, taxonomy_service: TaxonomyService) -> None:
        """Verify strict DAG validity: no cycles, zero orphans, all parents exist."""
        validation = taxonomy_service.validate_dag()
        assert validation["is_valid"] is True
        assert validation["orphan_count"] == 0
        assert len(validation["invalid_parents"]) == 0

    def test_backward_compatibility_with_original_36_topics(self, taxonomy_service: TaxonomyService) -> None:
        """Verify all 36 original canonical topic slugs from Phase 2.3A are preserved."""
        original_slugs = [
            "computer-science", "medicine", "biology", "mathematics", "physics",
            "engineering", "social-sciences", "economics", "environmental-science",
            "artificial-intelligence", "data-science", "software-engineering", "cybersecurity",
            "databases", "distributed-systems", "human-computer-interaction", "computer-networks",
            "machine-learning", "natural-language-processing", "computer-vision", "robotics",
            "knowledge-representation", "deep-learning", "reinforcement-learning", "generative-ai",
            "large-language-models", "transformers", "information-retrieval", "text-classification",
            "question-answering", "machine-translation", "object-detection", "image-segmentation",
            "data-mining", "vector-databases", "bioinformatics", "medical-informatics", "quantum-computing"
        ]
        for slug in original_slugs:
            node = taxonomy_service.get_node(slug)
            assert node is not None, f"Original canonical topic slug '{slug}' is missing!"

    def test_interdisciplinary_nodes_reachable(self, taxonomy_service: TaxonomyService) -> None:
        """Verify interdisciplinary topics (Bioinformatics, Computational Neuroscience, etc.) exist and are reachable."""
        interdisciplinary_slugs = [
            "bioinformatics",
            "medical-informatics",
            "computational-neuroscience",
            "materials-informatics",
            "computational-social-science",
            "physics-informed-machine-learning",
            "quantum-computing",
            "environmental-modeling",
        ]
        for slug in interdisciplinary_slugs:
            node = taxonomy_service.get_node(slug)
            assert node is not None, f"Interdisciplinary node '{slug}' not found"
            ancestors = taxonomy_service.get_ancestors(slug)
            assert len(ancestors) >= 1, f"Node '{slug}' should have at least 1 ancestor"

    def test_ontology_mappings_support(self, taxonomy_service: TaxonomyService) -> None:
        """Verify ontology mapping retrieval for MeSH, ACM CCS, and OpenAlex."""
        cs_openalex = taxonomy_service.get_ontology_mapping("computer-science", "openalex")
        assert cs_openalex == "C41008148"

        med_mesh = taxonomy_service.get_ontology_mapping("medicine", "mesh")
        assert med_mesh == "D008511"

        ir_acm = taxonomy_service.get_ontology_mapping("information-retrieval", "acm_ccs")
        assert ir_acm == "10002951.10003317"

    def test_coverage_report_metrics(self, taxonomy_service: TaxonomyService) -> None:
        """Verify that generate_coverage_report returns complete metrics."""
        report = taxonomy_service.generate_coverage_report()
        assert report["total_nodes"] >= 180
        assert report["root_count"] == 9
        assert report["max_depth"] >= 3
        assert report["average_depth"] >= 1.5
        assert report["is_valid_dag"] is True
