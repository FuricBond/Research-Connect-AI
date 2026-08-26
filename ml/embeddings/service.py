"""
Embedding service for Phase 2.3B.

Responsibilities
----------------
* Load (and cache) a SentenceTransformer model on first use.
* Encode single strings or batches of strings into 384-dim float vectors.
* Return numpy arrays — the caller is responsible for list conversion before
  storing in the database.

The service is intentionally *stateless* with respect to the database.
It does not read from or write to PostgreSQL; that is the responsibility of
the pipeline (``generate_embeddings.py``).

Usage
-----
    from ml.embeddings.service import EmbeddingService

    svc = EmbeddingService()                      # loads default model
    vectors = svc.encode_batch(["text 1", "text 2"])
    # vectors.shape == (2, 384)

Thread safety
-------------
``sentence_transformers.SentenceTransformer.encode()`` is not guaranteed to be
thread-safe with shared model state.  Create one ``EmbeddingService`` per
worker process (not per thread).
"""
from __future__ import annotations

import logging
from typing import Sequence

import numpy as np

from ml.embeddings.config import (
    DEFAULT_BATCH_SIZE,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DEVICE,
    EMBEDDING_MODEL,
)

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Wraps a SentenceTransformer model with lazy loading and batch encoding.

    Parameters
    ----------
    model_name:
        HuggingFace model identifier or local path.  Defaults to
        ``EMBEDDING_MODEL`` from config (``all-MiniLM-L6-v2``).
    device:
        PyTorch device string: ``"cpu"``, ``"cuda"``, ``"mps"``.
        Defaults to ``EMBEDDING_DEVICE`` from config.
    batch_size:
        Number of sentences per encoding batch.  Defaults to
        ``EMBEDDING_BATCH_SIZE`` from config.
    """

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.model_name: str = model_name or EMBEDDING_MODEL
        self.device: str = device or EMBEDDING_DEVICE
        self.batch_size: int = batch_size or EMBEDDING_BATCH_SIZE
        self._model: object | None = None  # lazy-loaded

    # ── model loading ──────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Load the SentenceTransformer model if not already loaded."""
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is not installed.  "
                "Run: pip install sentence-transformers==3.3.1"
            ) from exc

        logger.info(
            "Loading embedding model %r on device %r …",
            self.model_name,
            self.device,
        )
        self._model = SentenceTransformer(self.model_name, device=self.device)
        logger.info("Model loaded successfully.")

    @property
    def model(self) -> object:
        """Return the loaded SentenceTransformer model, loading it if necessary."""
        if self._model is None:
            self._load_model()
        return self._model  # type: ignore[return-value]

    # ── encoding ───────────────────────────────────────────────────────────────

    def encode_one(self, text: str) -> list[float]:
        """
        Encode a single string and return a Python list of floats.

        Parameters
        ----------
        text:
            Non-empty semantic text.

        Returns
        -------
        list[float]
            384-element (or model-specific) list of float values.
        """
        result = self.encode_batch([text])
        return result[0].tolist()

    def encode_batch(self, texts: Sequence[str]) -> np.ndarray:
        """
        Encode a batch of strings.

        Parameters
        ----------
        texts:
            Sequence of non-empty semantic text strings.  Empty-string entries
            will raise a warning but will not crash.

        Returns
        -------
        np.ndarray
            Shape ``(len(texts), embedding_dim)`` float32 array.
        """
        if not texts:
            return np.empty((0, 0), dtype=np.float32)

        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        model: SentenceTransformer = self.model  # type: ignore[assignment]

        logger.debug("Encoding batch of %d texts …", len(texts))
        vectors: np.ndarray = model.encode(
            list(texts),
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,  # L2-normalise for cosine-similarity via dot product
        )
        return vectors

    # ── convenience ────────────────────────────────────────────────────────────

    @property
    def embedding_dim(self) -> int:
        """Return the output dimensionality of the current model."""
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        model: SentenceTransformer = self.model  # type: ignore[assignment]
        return model.get_sentence_embedding_dimension()  # type: ignore[return-value]
