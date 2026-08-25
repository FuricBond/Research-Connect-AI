"""
Tests for ml.topic_analysis.taxonomy (TaxonomyNode, DAG hierarchy, traversal, cycle prevention).
"""
import pytest

from ml.topic_analysis.taxonomy import (
    SEED_TAXONOMY,
    TaxonomyNode,
    TaxonomyService,
)


class TestTaxonomyService:
    def test_seed_taxonomy_loaded(self):
        service = TaxonomyService()
        nodes = service.get_all_nodes()
        assert len(nodes) >= 20
        assert service.get_node("artificial-intelligence") is not None
        assert service.get_node("natural-language-processing") is not None
        assert service.get_node("large-language-models") is not None

    def test_ancestor_traversal(self):
        service = TaxonomyService()
        # Large Language Models -> NLP -> AI -> Computer Science
        ancestors = service.get_ancestors("large-language-models")
        assert "natural-language-processing" in ancestors
        assert "artificial-intelligence" in ancestors
        assert "computer-science" in ancestors

        # Immediate parent is first in ordered traversal
        assert ancestors[0] == "natural-language-processing"

    def test_descendant_traversal(self):
        service = TaxonomyService()
        descendants = service.get_descendants("artificial-intelligence")
        assert "machine-learning" in descendants
        assert "natural-language-processing" in descendants
        assert "computer-vision" in descendants
        assert "deep-learning" in descendants
        assert "large-language-models" in descendants

    def test_depth_calculation(self):
        service = TaxonomyService()
        assert service.get_depth("computer-science") == 0
        assert service.get_depth("artificial-intelligence") == 1
        assert service.get_depth("natural-language-processing") == 2
        assert service.get_depth("large-language-models") == 3

    def test_cycle_detection_raises(self):
        # Create circular nodes: A -> B -> C -> A
        cyclic_nodes = [
            TaxonomyNode(name="Node A", slug="node-a", parent_slug="node-c"),
            TaxonomyNode(name="Node B", slug="node-b", parent_slug="node-a"),
            TaxonomyNode(name="Node C", slug="node-c", parent_slug="node-b"),
        ]
        with pytest.raises(ValueError, match="Taxonomy cycle detected"):
            TaxonomyService(nodes=cyclic_nodes)

    def test_add_node_dynamically(self):
        service = TaxonomyService()
        custom = TaxonomyNode(
            name="Neuromorphic Computing",
            slug="neuromorphic-computing",
            parent_slug="computer-science",
            aliases=["Brain-inspired computing"],
        )
        service.add_node(custom)
        assert service.get_node("neuromorphic-computing") is not None
        assert "computer-science" in service.get_ancestors("neuromorphic-computing")
