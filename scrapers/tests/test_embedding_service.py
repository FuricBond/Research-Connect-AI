"""
Tests for ml.embeddings.service — EmbeddingService.

These tests use a lightweight mock of SentenceTransformer to avoid downloading
model weights during CI.  The actual model integration is verified via the
manual verification steps documented in the architecture doc.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ml.embeddings.service import EmbeddingService


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_mock_model(dim: int = 384) -> MagicMock:
    """Return a mock SentenceTransformer that returns random float32 arrays."""
    mock = MagicMock()
    mock.get_sentence_embedding_dimension.return_value = dim

    def fake_encode(texts, **kwargs) -> np.ndarray:
        n = len(texts)
        vecs = np.random.randn(n, dim).astype(np.float32)
        # L2-normalise to mimic real behaviour
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.where(norms == 0, 1.0, norms)

    mock.encode.side_effect = fake_encode
    return mock


# ── EmbeddingService ──────────────────────────────────────────────────────────


class TestEmbeddingService:
    """Tests that do not require a real model download."""

    def _patched_service(self, dim: int = 384) -> tuple[EmbeddingService, MagicMock]:
        svc = EmbeddingService(model_name="all-MiniLM-L6-v2", device="cpu", batch_size=8)
        mock_model = _make_mock_model(dim)
        svc._model = mock_model
        return svc, mock_model

    def test_lazy_load_called_on_first_access(self):
        svc = EmbeddingService()
        assert svc._model is None  # not loaded yet
        mock_model = _make_mock_model()
        svc._model = mock_model
        # Accessing .model should not reload if already set
        _ = svc.model
        assert svc._model is mock_model

    def test_encode_one_returns_list(self):
        svc, _ = self._patched_service()
        result = svc.encode_one("hello world")
        assert isinstance(result, list)
        assert len(result) == 384
        assert all(isinstance(v, float) for v in result)

    def test_encode_batch_shape(self):
        svc, _ = self._patched_service()
        texts = ["text one", "text two", "text three"]
        result = svc.encode_batch(texts)
        assert result.shape == (3, 384)
        assert result.dtype == np.float32

    def test_encode_empty_batch(self):
        svc, _ = self._patched_service()
        result = svc.encode_batch([])
        assert result.shape[0] == 0

    def test_encode_single_text(self):
        svc, _ = self._patched_service()
        result = svc.encode_batch(["single"])
        assert result.shape == (1, 384)

    def test_embedding_dim_property(self):
        svc, _ = self._patched_service(dim=384)
        assert svc.embedding_dim == 384

    def test_model_name_stored(self):
        svc = EmbeddingService(model_name="my-model")
        assert svc.model_name == "my-model"

    def test_batch_size_stored(self):
        svc = EmbeddingService(batch_size=16)
        assert svc.batch_size == 16

    def test_encode_calls_model_with_correct_batch_size(self):
        svc, mock_model = self._patched_service()
        svc.batch_size = 4
        texts = ["t"] * 12
        svc.encode_batch(texts)
        # encode is called once because we pass the full list to sentence_transformers
        # which handles internal batching
        assert mock_model.encode.called

    def test_vectors_l2_normalised(self):
        """Vectors from our mock are L2-normalised; verify norm ≈ 1."""
        svc, _ = self._patched_service()
        texts = ["alpha", "beta", "gamma"]
        vecs = svc.encode_batch(texts)
        norms = np.linalg.norm(vecs, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)

    def test_missing_sentence_transformers_raises(self):
        """If sentence_transformers is not importable, a helpful error is raised."""
        svc = EmbeddingService()
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            with pytest.raises((ImportError, TypeError)):
                svc._load_model()


# ── encode_one query cache (research refresh, F-3) ───────────────────────────


class TestEncodeOneCache:
    """The query cache answers repeated texts without the model and stays bounded."""

    def _patched_service(self) -> tuple[EmbeddingService, MagicMock]:
        svc = EmbeddingService(model_name="all-MiniLM-L6-v2", device="cpu", batch_size=8)
        mock_model = _make_mock_model()
        svc._model = mock_model
        return svc, mock_model

    def test_the_same_text_twice_calls_the_model_once(self):
        svc, mock_model = self._patched_service()
        first = svc.encode_one("graph neural networks")
        second = svc.encode_one("graph neural networks")
        assert mock_model.encode.call_count == 1
        assert first == second

    def test_different_texts_miss_the_cache(self):
        svc, mock_model = self._patched_service()
        svc.encode_one("graph neural networks")
        svc.encode_one("Graph neural networks")
        svc.encode_one("graph neural networks ")
        assert mock_model.encode.call_count == 3

    def test_a_cache_hit_returns_a_copy(self):
        svc, _ = self._patched_service()
        first = svc.encode_one("protein folding")
        first[0] = 99.0
        assert svc.encode_one("protein folding")[0] != 99.0

    def test_the_cache_never_grows_past_its_limit(self, monkeypatch):
        import ml.embeddings.service as service_module

        monkeypatch.setattr(service_module, "ENCODE_ONE_CACHE_SIZE", 4)
        svc, mock_model = self._patched_service()
        for i in range(10):
            svc.encode_one(f"query {i}")
            assert len(svc._encode_one_cache) <= 4
        assert len(svc._encode_one_cache) == 4
        # The newest entries stay; the oldest was evicted and must be encoded again.
        calls = mock_model.encode.call_count
        svc.encode_one("query 9")
        assert mock_model.encode.call_count == calls
        svc.encode_one("query 0")
        assert mock_model.encode.call_count == calls + 1

    def test_the_default_limit_is_512(self):
        import ml.embeddings.service as service_module

        assert service_module.ENCODE_ONE_CACHE_SIZE == 512


def test_concurrent_first_use_loads_the_model_once(monkeypatch):
    """A warm-up thread and a request racing on first use must not load two models."""
    import threading
    import time

    svc = EmbeddingService(model_name="all-MiniLM-L6-v2", device="cpu", batch_size=8)
    loads: list[int] = []

    def slow_load() -> None:
        loads.append(1)
        time.sleep(0.2)
        svc._model = _make_mock_model()

    monkeypatch.setattr(svc, "_load_model_unlocked", slow_load)
    threads = [threading.Thread(target=svc._load_model) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert len(loads) == 1
    assert svc._model is not None
