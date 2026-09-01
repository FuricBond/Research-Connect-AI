"""
Academic Query Intelligence Layer for Phase 2.4I.

Provides deterministic query normalization, academic acronym expansion,
and entity recognition prior to lexical and semantic retrieval.

Responsibilities
----------------
* Whitespace, punctuation, and casing normalization while preserving original query.
* Deterministic academic acronym expansion using an extensible registry (e.g., GNN, LLM, NLP, RAG).
* False-positive prevention (exact uppercase token matching, whole-word boundaries, stopword protection).
* Generation of a structured `QueryIntelligenceResult` capturing transformations.
* Zero LLM reliance, strictly deterministic and reproducible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import Mapping

logger = logging.getLogger(__name__)

# ── Academic Acronym Seed Registry ─────────────────────────────────────────────

SEED_ACADEMIC_ACRONYMS: dict[str, str] = {
    # Artificial Intelligence / Machine Learning
    "GNN": "Graph Neural Networks",
    "CNN": "Convolutional Neural Networks",
    "RNN": "Recurrent Neural Networks",
    "LSTM": "Long Short-Term Memory",
    "GAN": "Generative Adversarial Networks",
    "VAE": "Variational Autoencoder",
    "NLP": "Natural Language Processing",
    "LLM": "Large Language Models",
    "LLMS": "Large Language Models",
    "RAG": "Retrieval-Augmented Generation",
    "RL": "Reinforcement Learning",
    "DRL": "Deep Reinforcement Learning",
    "CV": "Computer Vision",
    "ML": "Machine Learning",
    "DL": "Deep Learning",
    "IR": "Information Retrieval",
    "KG": "Knowledge Graphs",
    "KGS": "Knowledge Graphs",
    "QA": "Question Answering",
    "MT": "Machine Translation",
    "NMT": "Neural Machine Translation",
    "HCI": "Human-Computer Interaction",
    "XAI": "Explainable Artificial Intelligence",
    "BERT": "Bidirectional Encoder Representations from Transformers",
    "GPT": "Generative Pre-trained Transformer",
    "VIT": "Vision Transformer",
    "CLIP": "Contrastive Language-Image Pretraining",
    "SSL": "Self-Supervised Learning",
    "SNN": "Spiking Neural Networks",
    "GBDT": "Gradient Boosted Decision Trees",
    "SVM": "Support Vector Machines",
    "HPO": "Hyperparameter Optimization",
    "NAS": "Neural Architecture Search",
    "ANN": "Approximate Nearest Neighbors",
    "HNSW": "Hierarchical Navigable Small World",
    "FTS": "Full-Text Search",
    "RRF": "Reciprocal Rank Fusion",
    # Systems, Networks & IoT
    "IOT": "Internet of Things",
    "CPS": "Cyber-Physical Systems",
    "SDN": "Software-Defined Networking",
    "WSN": "Wireless Sensor Networks",
    "P2P": "Peer-to-Peer",
    # Extended Disciplines & Graphics
    "AR": "Augmented Reality",
    "VR": "Virtual Reality",
    "XR": "Extended Reality",
    "GIS": "Geographic Information Systems",
    "BCI": "Brain-Computer Interface",
}

# Protected words that should NEVER be treated as acronyms even if capitalized
STOPWORDS: set[str] = {
    "A", "AN", "THE", "AND", "OR", "BUT", "IF", "BE", "BY", "FOR", "IN",
    "OF", "ON", "TO", "AT", "IT", "IS", "AS", "DO", "NO", "SO", "UP",
    "WE", "HE", "ME", "MY", "US", "GO", "WITH", "FROM", "THAT", "THIS",
}


# ── Query Intelligence Data Structure ──────────────────────────────────────────


@dataclass(frozen=True)
class QueryIntelligenceResult:
    """
    Container for processed query intelligence metadata.

    Attributes
    ----------
    original_query:
        The exact verbatim query string submitted by the client.
    normalized_query:
        Cleaned query with normalized whitespace and trimmed punctuation.
    expanded_query:
        Expanded query containing both original tokens and recognized academic expansions.
    detected_acronyms:
        List of identified academic acronyms (e.g., ['GNN', 'LLM']).
    detected_terms:
        List of expanded long-form phrases corresponding to detected acronyms.
    was_expanded:
        Boolean indicating whether any expansion took place.
    transformations:
        Human-readable audit log of transformations applied to the query.
    """

    original_query: str
    normalized_query: str
    expanded_query: str
    detected_acronyms: list[str] = field(default_factory=list)
    detected_terms: list[str] = field(default_factory=list)
    was_expanded: bool = False
    transformations: list[str] = field(default_factory=list)


# ── Query Intelligence Service ────────────────────────────────────────────────


class QueryIntelligenceService:
    """
    Deterministic academic query normalization and expansion engine.
    """

    def __init__(
        self,
        acronym_registry: Mapping[str, str] | None = None,
        custom_stopwords: set[str] | None = None,
    ) -> None:
        self._registry: dict[str, str] = dict(
            acronym_registry if acronym_registry is not None else SEED_ACADEMIC_ACRONYMS
        )
        self._stopwords: set[str] = (
            custom_stopwords if custom_stopwords is not None else set(STOPWORDS)
        )

    # ── Acronym Registry Management ───────────────────────────────────────────

    def register_acronym(self, acronym: str, expansion: str) -> None:
        """Register or override an academic acronym expansion."""
        clean_key = acronym.strip().upper()
        if clean_key:
            self._registry[clean_key] = expansion.strip()

    def get_expansion(self, acronym: str) -> str | None:
        """Retrieve registered expansion for an acronym if present."""
        return self._registry.get(acronym.strip().upper())

    # ── Normalization ─────────────────────────────────────────────────────────

    def normalize(self, query: str | None) -> str:
        """
        Normalize query string:
        - Collapses multiple whitespace/tabs/newlines to single space.
        - Strips leading and trailing whitespace.
        - Strips isolated leading/trailing punctuation characters (e.g., '? query !' -> 'query')
          while preserving hyphens in compound words (e.g. 'graph-based', 'multi-agent').
        """
        if not query:
            return ""

        # Collapse whitespace
        cleaned = re.sub(r"\s+", " ", query).strip()
        if not cleaned:
            return ""

        # Strip surrounding punctuation (e.g., "?query!", quotes, parentheses)
        cleaned = re.sub(r"^[\s!?,.:;\"\'\(\)\[\]\{\}]+|[\s!?,.:;\"\'\(\)\[\]\{\}]+$", "", cleaned)
        return cleaned

    # ── Core Processing ───────────────────────────────────────────────────────

    def process(self, query: str | None) -> QueryIntelligenceResult:
        """
        Execute full deterministic query intelligence pipeline:
        1. Normalize query
        2. Detect known academic acronyms
        3. Construct expanded lexical query
        4. Record transformation audit trace
        """
        if not query or not query.strip():
            return QueryIntelligenceResult(
                original_query=query or "",
                normalized_query="",
                expanded_query="",
                detected_acronyms=[],
                detected_terms=[],
                was_expanded=False,
                transformations=[],
            )

        original = query
        normalized = self.normalize(original)

        if not normalized:
            return QueryIntelligenceResult(
                original_query=original,
                normalized_query="",
                expanded_query="",
                detected_acronyms=[],
                detected_terms=[],
                was_expanded=False,
                transformations=[],
            )

        transformations: list[str] = []
        if normalized != original:
            transformations.append(f"Normalized whitespace and punctuation: '{original}' -> '{normalized}'")

        # Extract tokens and find acronyms
        # Match whole words, including uppercase tokens or capitalized variants
        # Regex matches standalone alphanumeric tokens
        tokens = re.findall(r"\b[A-Za-z0-9_\-]+\b", normalized)

        detected_acronyms: list[str] = []
        detected_terms: list[str] = []
        seen_acronyms: set[str] = set()

        for token in tokens:
            upper_token = token.upper()

            # Skip stopwords and already processed acronyms
            if upper_token in self._stopwords or upper_token in seen_acronyms:
                continue

            # Must match registry
            if upper_token in self._registry:
                # Require token to be mostly uppercase or exact match to prevent false positives
                # on common lowercase english words that coincide with acronyms
                if token.isupper() or len(token) >= 3:
                    seen_acronyms.add(upper_token)
                    detected_acronyms.append(upper_token)
                    expansion = self._registry[upper_token]
                    detected_terms.append(expansion)
                    transformations.append(
                        f"Detected academic acronym '{upper_token}' -> expanded to '{expansion}'"
                    )

        was_expanded = len(detected_terms) > 0

        # Construct expanded query
        if was_expanded:
            # Append unique expanded phrases that aren't already present in the normalized query
            terms_to_append: list[str] = []
            lower_normalized = normalized.lower()
            for term in detected_terms:
                if term.lower() not in lower_normalized:
                    terms_to_append.append(term)

            if terms_to_append:
                expanded_query = f"{normalized} " + " ".join(terms_to_append)
            else:
                expanded_query = normalized
        else:
            expanded_query = normalized

        return QueryIntelligenceResult(
            original_query=original,
            normalized_query=normalized,
            expanded_query=expanded_query,
            detected_acronyms=detected_acronyms,
            detected_terms=detected_terms,
            was_expanded=was_expanded,
            transformations=transformations,
        )


# Default singleton service instance
query_intelligence_service = QueryIntelligenceService()
