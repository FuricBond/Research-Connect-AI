"""
ml.topic_analysis — Research topic and taxonomy intelligence package.

Modules:
  taxonomy      — Canonical taxonomy tree, DAG hierarchy, and cycle-safe traversal
  normalization — Text, slug, alias, and source topic normalizers
  extraction    — Deterministic keyword and phrase extractor
  assignment    — Multi-evidence topic assignment and confidence scoring engine
  process_topics— Batch processing pipeline for research_works and opportunities
"""
from __future__ import annotations

from ml.topic_analysis.assignment import (
    AssignedTopic,
    TopicAssigner,
    TopicAssignmentResult,
)
from ml.topic_analysis.extraction import ExtractedKeyword, KeywordExtractor
from ml.topic_analysis.normalization import (
    TopicNormalizer,
    generate_topic_slug,
    normalize_topic_name,
)
from ml.topic_analysis.taxonomy import (
    SEED_TAXONOMY,
    TaxonomyNode,
    TaxonomyService,
)

__all__ = [
    "TaxonomyNode",
    "TaxonomyService",
    "SEED_TAXONOMY",
    "normalize_topic_name",
    "generate_topic_slug",
    "TopicNormalizer",
    "ExtractedKeyword",
    "KeywordExtractor",
    "TopicAssigner",
    "AssignedTopic",
    "TopicAssignmentResult",
]
