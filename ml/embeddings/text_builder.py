"""
Semantic text construction for Phase 2.3B.

Each entity type requires a carefully chosen combination of fields to produce
a rich, representative embedding.  The functions here are *deterministic*:
given the same entity they always produce the same string, so the content hash
is stable across pipeline runs.

Design principles
-----------------
* Use the fields a researcher would naturally read to understand the entity.
* Prefer quality over quantity: empty or None fields are silently omitted.
* Field ordering follows natural reading order (title first, body second, …).
* Separator is ``" | "`` between major sections so the model can distinguish
  them without relying on newlines (which some tokenisers collapse).
* Maximum length is capped at 8 192 characters to stay within the MiniLM
  context window (512 tokens ≈ ~2 000 characters) with headroom for future
  model changes.  Truncation happens at a word boundary.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Imported lazily to avoid mandatory backend imports in pure-ML context
    pass

_MAX_CHARS: int = 8_192


# ── helpers ────────────────────────────────────────────────────────────────────


def _join(*parts: str | None, sep: str = " | ") -> str:
    """Join non-empty, non-None parts with *sep*."""
    return sep.join(p.strip() for p in parts if p and p.strip())


def _truncate(text: str, max_chars: int = _MAX_CHARS) -> str:
    """Truncate *text* to at most *max_chars* characters at a word boundary."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    return truncated[:last_space] if last_space > 0 else truncated


# ── public builders ────────────────────────────────────────────────────────────


def build_research_work_text(work: Any) -> str:
    """
    Build the semantic text for a ``ResearchWorkModel`` instance.

    Fields used (in order):
    1. ``title``                — primary identity
    2. ``abstract``             — content description
    3. ``work_type``            — article / preprint / …
    4. ``publication_year``     — temporal context
    5. ``language``             — language context

    Parameters
    ----------
    work:
        A ``ResearchWorkModel`` ORM instance or any object with the expected
        attributes.  Pure-Python attributes are accessed directly (no DB I/O).

    Returns
    -------
    str
        Normalised, truncated semantic text ready for embedding.

    Raises
    ------
    ValueError
        If *work* has no title (title is mandatory for a meaningful embedding).
    """
    title: str | None = getattr(work, "title", None)
    if not title or not title.strip():
        raise ValueError(
            f"ResearchWorkModel id={getattr(work, 'id', '?')} has no title; "
            "cannot build semantic text."
        )

    abstract: str | None = getattr(work, "abstract", None)
    work_type: str | None = getattr(work, "work_type", None)
    publication_year: int | None = getattr(work, "publication_year", None)
    language: str | None = getattr(work, "language", None)

    parts: list[str] = [title.strip()]

    if abstract and abstract.strip():
        parts.append(abstract.strip())

    meta_parts: list[str] = []
    if work_type:
        meta_parts.append(work_type.strip())
    if publication_year:
        meta_parts.append(str(publication_year))
    if language and language.lower() not in ("en", "english"):
        # Only include language when it is not English to save tokens
        meta_parts.append(language.strip())

    if meta_parts:
        parts.append(" ".join(meta_parts))

    return _truncate(_join(*parts))


def build_opportunity_text(opportunity: Any) -> str:
    """
    Build the semantic text for an ``OpportunityModel`` instance.

    Fields used (in order):
    1. ``title``                    — primary identity
    2. ``opportunity_type``         — CONFERENCE / JOURNAL / …
    3. ``summary`` / ``description`` — content description
    4. ``publisher`` / ``organizer`` — organisational context
    5. ``location``                 — geographic context
    6. ``series_name``              — series context

    Parameters
    ----------
    opportunity:
        An ``OpportunityModel`` ORM instance or compatible plain object.

    Returns
    -------
    str
        Normalised, truncated semantic text ready for embedding.

    Raises
    ------
    ValueError
        If *opportunity* has no title.
    """
    title: str | None = getattr(opportunity, "title", None)
    if not title or not title.strip():
        raise ValueError(
            f"OpportunityModel id={getattr(opportunity, 'id', '?')} has no title; "
            "cannot build semantic text."
        )

    opportunity_type: str | None = getattr(opportunity, "opportunity_type", None)
    summary: str | None = getattr(opportunity, "summary", None)
    description: str | None = getattr(opportunity, "description", None)
    publisher: str | None = getattr(opportunity, "publisher", None)
    organizer: str | None = getattr(opportunity, "organizer", None)
    location: str | None = getattr(opportunity, "location", None)
    series_name: str | None = getattr(opportunity, "series_name", None)

    # Primary descriptor: title + type
    header_parts: list[str] = [title.strip()]
    if opportunity_type:
        header_parts.append(opportunity_type.strip())
    header = " ".join(header_parts)

    # Body: prefer summary, fall back to description, allow both
    body_parts: list[str] = []
    if summary and summary.strip():
        body_parts.append(summary.strip())
    if description and description.strip() and description.strip() != (summary or "").strip():
        body_parts.append(description.strip())
    body = " ".join(body_parts)

    # Context
    context_parts: list[str] = []
    for val in (publisher, organizer, series_name, location):
        if val and val.strip():
            context_parts.append(val.strip())
    context = ", ".join(context_parts)

    return _truncate(_join(header, body or None, context or None))


def build_text_from_dict(
    entity_type: str,
    data: dict[str, Any],
) -> str:
    """
    Build semantic text from a plain dict instead of an ORM model.

    Useful for dry-run CLI pipelines and tests where full SQLAlchemy
    objects are not available.

    Parameters
    ----------
    entity_type:
        ``"research_work"`` or ``"opportunity"``.
    data:
        Dict with field names matching the ORM model attributes.

    Returns
    -------
    str
    """

    class _Proxy:
        """Lightweight proxy that wraps a dict as attribute access."""
        def __init__(self, d: dict[str, Any]) -> None:
            self._d = d

        def __getattr__(self, name: str) -> Any:
            return self._d.get(name)

    proxy = _Proxy(data)
    if entity_type == "research_work":
        return build_research_work_text(proxy)
    if entity_type == "opportunity":
        return build_opportunity_text(proxy)
    raise ValueError(f"Unknown entity_type: {entity_type!r}")
