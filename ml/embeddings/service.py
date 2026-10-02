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
worker process (not per thread).  Model loading and the ``encode_one`` cache are
guarded by locks, so a startup warm-up thread and a request can share one service.

Query cache
-----------
``encode_one`` keeps the most recent ``ENCODE_ONE_CACHE_SIZE`` results, keyed by
model name and exact text, so a repeated literature query skips the model.  Each
hit returns a fresh copy, so a caller can never mutate a cached vector.
"""
from __future__ import annotations

from collections import OrderedDict
import logging
import threading
from typing import Sequence

import numpy as np

from ml.embeddings.config import (
    DEFAULT_BATCH_SIZE,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DEVICE,
    EMBEDDING_MODEL,
)

logger = logging.getLogger(__name__)

# Most recent single-text encodings kept per service instance.
ENCODE_ONE_CACHE_SIZE: int = 512


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
        self._load_lock = threading.Lock()
        self._encode_one_cache: OrderedDict[tuple[str, str], list[float]] = OrderedDict()
        self._encode_one_cache_lock = threading.Lock()

    # ── model loading ──────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Load the SentenceTransformer model if not already loaded."""
        if self._model is not None:
            return
        with self._load_lock:
            # A concurrent caller may have finished loading while this one waited.
            if self._model is not None:
                return
            self._load_model_unlocked()

    def _load_model_unlocked(self) -> None:
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
            384-element (or model-specific) list of float values.  Served from
            the query cache when the same text was encoded recently.
        """
        key = (self.model_name, text)
        with self._encode_one_cache_lock:
            cached = self._encode_one_cache.get(key)
            if cached is not None:
                self._encode_one_cache.move_to_end(key)
                return list(cached)

        # Encode outside the lock, so a slow encode never blocks cache hits.
        vector = self.encode_batch([text])[0].tolist()
        with self._encode_one_cache_lock:
            self._encode_one_cache[key] = vector
            self._encode_one_cache.move_to_end(key)
            while len(self._encode_one_cache) > ENCODE_ONE_CACHE_SIZE:
                self._encode_one_cache.popitem(last=False)
        return list(vector)

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
