"""
Abstract text reconstruction for OpenAlex works.

OpenAlex stores abstracts as an *inverted index*: a mapping from each word
to the list of positions it appears at.

Example::

    {
        "Despite": [0],
        "growing": [1],
        "interest": [2],
        "in": [3, 57],
        ...
    }

This module provides ``reconstruct_abstract()`` which reliably converts that
structure into a plain-text string.  It handles:

  - ``None`` / missing abstract
  - Empty dict ``{}``
  - Malformed structure (wrong types, negative positions, …)
  - Works that store the abstract as a plain string (legacy / non-standard)

Never raises.  Always returns ``str | None``.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def reconstruct_abstract(inverted_index: object) -> str | None:
    """
    Reconstruct the full abstract text from an OpenAlex inverted-index dict.

    Args:
        inverted_index: Value of ``abstract_inverted_index`` from the
                        OpenAlex API response.  May be ``None``, an empty
                        dict, a plain string (non-standard), or a well-formed
                        ``dict[str, list[int]]``.

    Returns:
        Reconstructed abstract string, or ``None`` if the input is missing
        or cannot be reliably reconstructed.
    """
    if inverted_index is None:
        return None

    # Some older / non-standard responses include a plain string
    if isinstance(inverted_index, str):
        stripped = inverted_index.strip()
        return stripped if stripped else None

    if not isinstance(inverted_index, dict):
        logger.debug(
            "abstract_inverted_index has unexpected type %s — skipping",
            type(inverted_index).__name__,
        )
        return None

    if not inverted_index:
        return None

    # Build position → word mapping
    try:
        position_word: dict[int, str] = {}
        for word, positions in inverted_index.items():
            if not isinstance(word, str) or not isinstance(positions, list):
                logger.debug(
                    "Malformed abstract entry: word=%r positions=%r — skipping entry",
                    word,
                    positions,
                )
                continue
            for pos in positions:
                if not isinstance(pos, int) or pos < 0:
                    logger.debug(
                        "Invalid position %r for word %r — skipping position",
                        pos,
                        word,
                    )
                    continue
                position_word[pos] = word

    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse abstract_inverted_index: %s", exc)
        return None

    if not position_word:
        return None

    # Sort by position and join
    words = [position_word[pos] for pos in sorted(position_word)]
    return " ".join(words)
