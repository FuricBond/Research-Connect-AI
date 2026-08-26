"""
Tests for ml.embeddings.hash_utils — SHA-256 content hashing utilities.
"""
import pytest

from ml.embeddings.hash_utils import compute_content_hash, needs_reembedding


class TestComputeContentHash:
    def test_returns_64_char_hex_string(self):
        h = compute_content_hash("hello world")
        assert isinstance(h, str)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        text = "Machine learning for climate change prediction"
        assert compute_content_hash(text) == compute_content_hash(text)

    def test_different_texts_produce_different_hashes(self):
        h1 = compute_content_hash("text one")
        h2 = compute_content_hash("text two")
        assert h1 != h2

    def test_empty_string(self):
        h = compute_content_hash("")
        assert len(h) == 64

    def test_unicode(self):
        h = compute_content_hash("Ψηφιακή τεχνολογία")
        assert len(h) == 64

    def test_whitespace_sensitivity(self):
        # Trailing whitespace produces a different hash — text_builder strips, not hashing
        h1 = compute_content_hash("hello")
        h2 = compute_content_hash("hello ")
        assert h1 != h2

    def test_known_value(self):
        import hashlib
        text = "ResearchConnect AI"
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert compute_content_hash(text) == expected


class TestNeedsReembedding:
    MODEL = "all-MiniLM-L6-v2"

    def test_no_stored_hash_returns_true(self):
        assert needs_reembedding("some text", None, None, self.MODEL) is True

    def test_no_stored_model_returns_true(self):
        h = compute_content_hash("some text")
        assert needs_reembedding("some text", h, None, self.MODEL) is True

    def test_matching_hash_and_model_returns_false(self):
        text = "same text same model"
        h = compute_content_hash(text)
        assert needs_reembedding(text, h, self.MODEL, self.MODEL) is False

    def test_changed_text_returns_true(self):
        old_text = "original text"
        new_text = "modified text"
        h = compute_content_hash(old_text)
        assert needs_reembedding(new_text, h, self.MODEL, self.MODEL) is True

    def test_model_change_returns_true(self):
        text = "same text"
        h = compute_content_hash(text)
        assert needs_reembedding(text, h, "old-model-v1", "new-model-v2") is True

    def test_model_same_text_same(self):
        text = "neural networks"
        h = compute_content_hash(text)
        assert needs_reembedding(text, h, self.MODEL, self.MODEL) is False
