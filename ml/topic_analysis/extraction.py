"""
Deterministic keyword and keyphrase extraction engine.

Extracts candidate domain phrases and taxonomy keywords from research work and
opportunity titles, abstracts, and metadata without heavy external dependencies or LLMs.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from ml.topic_analysis.normalization import TopicNormalizer, normalize_topic_name

logger = logging.getLogger(__name__)

# Standard academic English stopwords
_STOPWORDS: set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
    "some", "such", "than", "that", "that's", "the", "their", "theirs", "them",
    "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll",
    "they're", "they've", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves",
    # Academic noise words
    "paper", "study", "approach", "method", "results", "analysis", "using", "based",
    "via", "proposed", "novel", "framework", "performance", "system", "systems",
    "application", "applications", "evaluation", "presents", "show", "shows",
    "demonstrates", "experimental", "experiments", "efficient", "new", "scalable",
}


@dataclass
class ExtractedKeyword:
    """Represents an extracted keyword or phrase with occurrence metrics."""
    keyword: str
    raw_term: str
    count: int
    weight: float
    is_title: bool
    is_abstract: bool
    canonical_topic_slug: str | None = None


class KeywordExtractor:
    """
    Extracts high-value domain keywords and matches taxonomy terms from text.
    """

    def __init__(self, normalizer: TopicNormalizer | None = None) -> None:
        self._normalizer = normalizer or TopicNormalizer()

    def _tokenize(self, text: str) -> list[str]:
        """Split text into cleaned words."""
        cleaned = re.sub(r"[^\w\s-]", " ", text)
        return [w.strip().lower() for w in cleaned.split() if w.strip()]

    def extract_ngrams(self, words: list[str], max_n: int = 3) -> list[str]:
        """Extract unigrams, bigrams, and trigrams."""
        ngrams: list[str] = []
        n_words = len(words)
        for n in range(1, max_n + 1):
            for i in range(n_words - n + 1):
                gram_words = words[i : i + n]
                # Filter out n-grams starting or ending with stopwords (for multi-word phrases)
                if n > 1:
                    if gram_words[0] in _STOPWORDS or gram_words[-1] in _STOPWORDS:
                        continue
                elif gram_words[0] in _STOPWORDS or len(gram_words[0]) < 3:
                    continue
                ngrams.append(" ".join(gram_words))
        return ngrams

    def extract_keywords(
        self,
        title: str | None,
        abstract: str | None = None,
        source_keywords: list[str] | None = None,
        top_k: int = 15,
    ) -> list[ExtractedKeyword]:
        """
        Extract ranked keywords from title, abstract, and optional source keyword tags.

        Weights:
          - Title occurrence: 2.0x weight
          - Abstract occurrence: 1.0x weight
          - Source keyword match: 2.5x weight
        """
        keyword_counts: dict[str, int] = {}
        keyword_weights: dict[str, float] = {}
        is_title_map: dict[str, bool] = {}
        is_abstract_map: dict[str, bool] = {}
        raw_repr_map: dict[str, str] = {}

        # 1. Process Title
        if title:
            title_words = self._tokenize(title)
            title_ngrams = self.extract_ngrams(title_words, max_n=3)
            for gram in title_ngrams:
                norm = normalize_topic_name(gram)
                if not norm:
                    continue
                keyword_counts[norm] = keyword_counts.get(norm, 0) + 1
                keyword_weights[norm] = keyword_weights.get(norm, 0.0) + 2.0
                is_title_map[norm] = True
                raw_repr_map.setdefault(norm, gram)

        # 2. Process Abstract
        if abstract:
            abstract_words = self._tokenize(abstract)
            abstract_ngrams = self.extract_ngrams(abstract_words, max_n=3)
            for gram in abstract_ngrams:
                norm = normalize_topic_name(gram)
                if not norm:
                    continue
                keyword_counts[norm] = keyword_counts.get(norm, 0) + 1
                keyword_weights[norm] = keyword_weights.get(norm, 0.0) + 1.0
                is_abstract_map[norm] = True
                raw_repr_map.setdefault(norm, gram)

        # 3. Process Source Keywords
        if source_keywords:
            for kw in source_keywords:
                if not kw:
                    continue
                norm = normalize_topic_name(kw)
                if not norm:
                    continue
                keyword_counts[norm] = keyword_counts.get(norm, 0) + 1
                keyword_weights[norm] = keyword_weights.get(norm, 0.0) + 2.5
                raw_repr_map.setdefault(norm, kw)

        # 4. Map against canonical taxonomy
        extracted: list[ExtractedKeyword] = []
        for norm, weight in keyword_weights.items():
            slug = self._normalizer.resolve(norm)
            # Boost weight if term directly matches a canonical taxonomy topic
            final_weight = weight * (1.5 if slug else 1.0)
            extracted.append(
                ExtractedKeyword(
                    keyword=norm,
                    raw_term=raw_repr_map.get(norm, norm),
                    count=keyword_counts[norm],
                    weight=final_weight,
                    is_title=is_title_map.get(norm, False),
                    is_abstract=is_abstract_map.get(norm, False),
                    canonical_topic_slug=slug,
                )
            )

        # Sort by weight descending
        extracted.sort(key=lambda x: (x.canonical_topic_slug is not None, x.weight, x.count), reverse=True)
        return extracted[:top_k]
