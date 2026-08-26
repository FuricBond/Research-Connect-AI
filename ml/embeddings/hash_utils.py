"""
Deterministic content-hash utilities for Phase 2.3B.

A ``content_hash`` is computed from the *semantic text* that will be embedded
(i.e. the exact string passed to the model).  This allows the pipeline to skip
re-embedding records whose semantic content has not changed between ingestion
runs, making the embedding step idempotent and fast.

Algorithm
---------
SHA-256 over the UTF-8 bytes of the normalised semantic text, hex-encoded.
No salt, no timestamp — purely content-driven.
"""
from __future__ import annotations

import hashlib


def compute_content_hash(text: str) -> str:
    """
    Return the SHA-256 hex digest of *text*.

    Parameters
    ----------
    text:
        The normalised semantic text that will be embedded.  Must be the exact
        same string that the embedding service will receive so that the hash
        faithfully represents what was embedded.

    Returns
    -------
    str
        64-character lowercase hex string, e.g.
        ``"a3f1..."``
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def needs_reembedding(
    new_text: str,
    stored_hash: str | None,
    stored_model: str | None,
    current_model: str,
) -> bool:
    """
    Return ``True`` when a record should be (re-)embedded.

    A record needs embedding when any of the following is true:

    * It has never been embedded (``stored_hash`` is ``None``).
    * The semantic content has changed (hash mismatch).
    * A different embedding model is now in use (model name mismatch).

    Parameters
    ----------
    new_text:
        The current semantic text for the entity.
    stored_hash:
        The ``content_hash`` value already in the database, or ``None``.
    stored_model:
        The ``embedding_model`` value already in the database, or ``None``.
    current_model:
        The name of the model currently in use.
    """
    if stored_hash is None or stored_model is None:
        return True
    if stored_model != current_model:
        return True
    return compute_content_hash(new_text) != stored_hash
