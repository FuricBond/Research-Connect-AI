"""
Topic label and alias normalizer.

Converts diverse, heterogeneous topic strings, acronyms, and external taxonomy terms
(from OpenAlex, Crossref, user input, or paper metadata) into canonical ResearchConnect topic slugs.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from ml.topic_analysis.taxonomy import SEED_TAXONOMY, TaxonomyService

logger = logging.getLogger(__name__)

# Common Crossref / OpenAlex subject normalization mappings
_EXTERNAL_SUBJECT_MAP: dict[str, str] = {
    # OpenAlex / Crossref general variations
    "artificial intelligence": "artificial-intelligence",
    "computational intelligence": "artificial-intelligence",
    "machine learning": "machine-learning",
    "statistical learning": "machine-learning",
    "natural language processing": "natural-language-processing",
    "computational linguistics": "natural-language-processing",
    "language technologies": "natural-language-processing",
    "speech and natural language processing": "natural-language-processing",
    "computer vision": "computer-vision",
    "visual recognition": "computer-vision",
    "computer vision and pattern recognition": "computer-vision",
    "image processing": "computer-vision",
    "pattern recognition": "computer-vision",
    "deep learning": "deep-learning",
    "neural networks": "deep-learning",
    "deep neural networks": "deep-learning",
    "reinforcement learning": "reinforcement-learning",
    "generative artificial intelligence": "generative-ai",
    "generative ai": "generative-ai",
    "large language models": "large-language-models",
    "large language model": "large-language-models",
    "foundation models": "large-language-models",
    "transformers": "transformers",
    "transformer models": "transformers",
    "information retrieval": "information-retrieval",
    "search engines": "information-retrieval",
    "text mining": "text-classification",
    "sentiment analysis": "text-classification",
    "text classification": "text-classification",
    "question answering": "question-answering",
    "retrieval augmented generation": "question-answering",
    "machine translation": "machine-translation",
    "robotics": "robotics",
    "control and robotics": "robotics",
    "autonomous systems": "robotics",
    "data science": "data-science",
    "data analytics": "data-science",
    "big data": "data-science",
    "data mining": "data-mining",
    "knowledge discovery": "data-mining",
    "software engineering": "software-engineering",
    "software development": "software-engineering",
    "cybersecurity": "cybersecurity",
    "cyber security": "cybersecurity",
    "information security": "cybersecurity",
    "cryptography": "cybersecurity",
    "databases": "databases",
    "database systems": "databases",
    "distributed systems": "distributed-systems",
    "distributed computing": "distributed-systems",
    "cloud computing": "distributed-systems",
    "human-computer interaction": "human-computer-interaction",
    "human computer interaction": "human-computer-interaction",
    "bioinformatics": "bioinformatics",
    "computational biology": "bioinformatics",
    "medical informatics": "medical-informatics",
    "healthcare ai": "medical-informatics",
    "quantum computing": "quantum-computing",
    "quantum information": "quantum-computing",
    "computer science (miscellaneous)": "computer-science",
    "general computer science": "computer-science",
}


def normalize_topic_name(name: str | None) -> str:
    """
    Normalize topic label string:
      - NFKD Unicode normalization (strip accents)
      - Lowercase
      - Strip punctuation
      - Collapse whitespace
    """
    if not name:
        return ""
    # Normalize unicode
    text = unicodedata.normalize("NFKD", name)
    # Strip accents
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Replace punctuation (except hyphens) with space
    text = re.sub(r"[^\w\s-]", " ", text)
    # Lowercase & collapse whitespace
    return " ".join(text.lower().split())


def generate_topic_slug(name: str | None) -> str:
    """
    Generate a deterministic URL/database-safe slug from a topic name.

    Example:
        'Natural Language Processing' -> 'natural-language-processing'
        'Human-Computer Interaction (HCI)' -> 'human-computer-interaction-hci'
    """
    if not name:
        return ""
    normalized = normalize_topic_name(name)
    slug = re.sub(r"[\s_]+", "-", normalized)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


class TopicNormalizer:
    """
    Maps arbitrary input terms, abbreviations, OpenAlex topics, and Crossref subjects
    to canonical ResearchConnect topic slugs.
    """

    def __init__(self, taxonomy_service: TaxonomyService | None = None) -> None:
        self._taxonomy = taxonomy_service or TaxonomyService()
        self._mapping: dict[str, str] = {}
        self._build_mapping()

    def _build_mapping(self) -> None:
        """Construct comprehensive normalized term -> canonical slug lookup map."""
        self._mapping.clear()

        # 1. Map all taxonomy nodes by exact slug
        for node in self._taxonomy.get_all_nodes():
            self._mapping[node.slug] = node.slug
            self._mapping[normalize_topic_name(node.name)] = node.slug

            # Map all node aliases
            for alias in node.aliases:
                self._mapping[normalize_topic_name(alias)] = node.slug

        # 2. Add external subject/domain mappings
        for ext_term, slug in _EXTERNAL_SUBJECT_MAP.items():
            norm_ext = normalize_topic_name(ext_term)
            if slug in self._taxonomy._by_slug:
                self._mapping[norm_ext] = slug

    def resolve(self, raw_term: str | None) -> str | None:
        """
        Attempt to resolve a raw topic string, alias, or external label to a canonical topic slug.

        Args:
            raw_term: Input term (e.g. 'NLP', 'Machine Learning', 'AI', 'Deep Neural Networks')

        Returns:
            Canonical topic slug (e.g. 'natural-language-processing') or None if unmapped.
        """
        if not raw_term:
            return None

        normalized = normalize_topic_name(raw_term)
        if not normalized:
            return None

        # 1. Direct normalized lookup
        if normalized in self._mapping:
            return self._mapping[normalized]

        # 2. Check direct slug match
        slug_candidate = generate_topic_slug(raw_term)
        if slug_candidate in self._mapping:
            return self._mapping[slug_candidate]

        # 3. Check exact acronym match (case sensitive before normalization)
        stripped = raw_term.strip()
        stripped_lower = stripped.lower()
        if stripped_lower in self._mapping:
            return self._mapping[stripped_lower]

        return None

    def resolve_openalex_topic(self, topic_dict: dict[str, Any]) -> tuple[str | None, float]:
        """
        Resolve an OpenAlex topic object to (canonical_slug, source_score).

        OpenAlex topic structure:
          {'id': 'https://openalex.org/T10028', 'display_name': 'Natural Language Processing', 'score': 0.99}
        """
        if not isinstance(topic_dict, dict):
            return None, 0.0

        display_name = topic_dict.get("display_name")
        score = float(topic_dict.get("score") or 0.85)

        slug = self.resolve(display_name)
        return slug, score

    def resolve_crossref_subject(self, raw_subject: str) -> str | None:
        """Resolve a Crossref subject string to canonical slug."""
        return self.resolve(raw_subject)
