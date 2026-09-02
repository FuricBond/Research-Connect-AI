"""
Academic Feature Extraction & Normalization Layer for Phase 2.5B.

Converts raw academic metadata (work citations, researcher prominence, author position,
institution prestige, venue prestige, and open-access tier) into deterministic,
bounded [0.0, 1.0] feature vectors for recommendation ranking (Phase 2.5C).

Key Guarantees:
---------------
1. All extracted features are strictly bounded to [0.0, 1.0].
2. Outputs are 100% deterministic (same input produces identical output).
3. Defensive handling: NaN, Infinity, negative values, and unexpected types are clamped or defaulted.
4. Monotonic saturation: Logarithmic scaling for citation-derived metrics prevents mega-cited works from monopolizing features.
5. Zero N+1 queries: Batch extraction utility supports pre-loaded models and batch resolution.
6. Zero side-effects on Phase 2.4 ranking: This module provides feature contracts for Phase 2.5C without altering production ranking behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import math
from typing import Any, Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.ranking.signals import validate_signal
from app.ranking.venue_intelligence import venue_resolver

logger = logging.getLogger(__name__)

# ── Feature Constants & Saturation Thresholds ────────────────────────────────

DEFAULT_MAX_WORK_CITATIONS: float = 10000.0
DEFAULT_MAX_AUTHOR_CITATIONS: float = 50000.0
DEFAULT_MAX_INST_CITATIONS: float = 500000.0
DEFAULT_MAX_VENUE_CITATIONS: float = 100000.0
DEFAULT_DOAJ_VENUE_BONUS: float = 0.10

# Author position priority weights
AUTHOR_POSITION_SCORES: dict[str, float] = {
    "CORRESPONDING": 1.00,
    "CORRESPONDING_AUTHOR": 1.00,
    "SINGLE": 1.00,
    "SOLE": 1.00,
    "FIRST": 0.90,
    "FIRST_AUTHOR": 0.90,
    "CO-FIRST": 0.90,
    "CO_FIRST": 0.90,
    "LEAD": 0.90,
    "PRIMARY": 0.90,
    "LAST": 0.80,
    "SENIOR": 0.80,
    "SENIOR_AUTHOR": 0.80,
    "PI": 0.80,
    "SUPERVISOR": 0.80,
    "MIDDLE": 0.50,
    "CONTRIBUTOR": 0.50,
    "UNKNOWN": 0.50,
}

# Open Access tier weights
OA_STATUS_SCORES: dict[str, float] = {
    "GOLD": 1.00,
    "DIAMOND": 1.00,
    "PLATINUM": 1.00,
    "HYBRID": 0.85,
    "GREEN": 0.70,
    "BRONZE": 0.55,
    "CLOSED": 0.20,
    "RESTRICTED": 0.20,
    "SUBSCRIPTION": 0.20,
    "PAYWALLED": 0.20,
    "UNKNOWN": 0.35,
}


# ── 1. Citation Impact Normalization ──────────────────────────────────────────


def calculate_citation_impact(
    cited_by_count: int | float | None = None,
    max_citations: float = DEFAULT_MAX_WORK_CITATIONS,
) -> float:
    """
    Calculate normalized citation impact using monotonic logarithmic saturation.

    Formula:
        citation_impact = log10(1 + max(0, citations)) / log10(1 + max_citations)

    Parameters
    ----------
    cited_by_count:
        Total citations recorded for the research work.
    max_citations:
        Citation saturation upper bound (default 10,000 citations).

    Returns
    -------
    float
        Normalized score in [0.0, 1.0].
    """
    if max_citations <= 0.0:
        raise ValueError(f"max_citations must be positive, got {max_citations}")

    if cited_by_count is None:
        return 0.0

    if isinstance(cited_by_count, bool) or not isinstance(cited_by_count, (int, float)):
        return 0.0

    f_cit = float(cited_by_count)
    if math.isnan(f_cit) or math.isinf(f_cit) or f_cit <= 0.0:
        return 0.0

    denominator = math.log10(1.0 + max_citations)
    numerator = math.log10(1.0 + f_cit)

    score = numerator / denominator
    return round(min(1.0, max(0.0, score)), 6)


# ── 2. Author Prominence Normalization ─────────────────────────────────────────


def calculate_author_prominence(
    authors: Sequence[Any] | Any | None = None,
    max_author_citations: float = DEFAULT_MAX_AUTHOR_CITATIONS,
) -> float:
    """
    Calculate normalized author prominence based on researcher citation impact.

    Multi-Author Policy:
        Derives prominence from the maximum individual author citation score among
        the research work's co-authors:
            author_prominence = max_{a in authors} [ log10(1 + c_a) / log10(1 + max_author_cit) ]

    Why Maximum?
        Anchors prominence to the senior / lead researcher without artificially
        inflating papers authored by large multi-institution consortia (e.g. 500+ author papers).

    Parameters
    ----------
    authors:
        Sequence of author links (ResearchWorkAuthorModel), researcher models (ResearcherModel),
        parent ResearchWorkModel, or author dictionaries with 'cited_by_count' or 'researcher' attributes.
    max_author_citations:
        Saturation denominator for author citations (default 50,000 citations).

    Returns
    -------
    float
        Normalized prominence score in [0.0, 1.0].
    """
    if max_author_citations <= 0.0:
        raise ValueError(f"max_author_citations must be positive, got {max_author_citations}")

    if authors is None:
        return 0.0

    if hasattr(authors, "author_links"):
        authors = getattr(authors, "author_links")

    if not authors:
        return 0.0

    denom = math.log10(1.0 + max_author_citations)
    best_score = 0.0

    # Ensure iterable
    author_list = authors if isinstance(authors, (list, tuple, set)) else [authors]

    for author_item in author_list:
        if author_item is None:
            continue

        cits: float | None = None

        # Check if direct researcher model
        if hasattr(author_item, "cited_by_count"):
            cits = getattr(author_item, "cited_by_count", None)

        # Check if junction link (ResearchWorkAuthorModel)
        if cits is None and hasattr(author_item, "researcher"):
            researcher = getattr(author_item, "researcher", None)
            if researcher is not None and hasattr(researcher, "cited_by_count"):
                cits = getattr(researcher, "cited_by_count", None)

        # Check if dictionary
        if cits is None and isinstance(author_item, dict):
            cits = author_item.get("cited_by_count")
            if cits is None and "researcher" in author_item and isinstance(author_item["researcher"], dict):
                cits = author_item["researcher"].get("cited_by_count")

        if cits is None or isinstance(cits, bool) or not isinstance(cits, (int, float)):
            continue

        f_cits = float(cits)
        if math.isnan(f_cits) or math.isinf(f_cits) or f_cits <= 0.0:
            continue

        author_score = math.log10(1.0 + f_cits) / denom
        if author_score > best_score:
            best_score = author_score

    return round(min(1.0, max(0.0, best_score)), 6)


# ── 3. Author Position Scoring ────────────────────────────────────────────────


def calculate_author_position_score(
    author_position: str | None = None,
    is_corresponding: bool = False,
    authors: Sequence[Any] | Any | None = None,
) -> float:
    """
    Calculate normalized author contribution weight based on authorship position.

    Hierarchy:
      1. Corresponding author -> 1.00
      2. Single / Sole author -> 1.00
      3. First / Lead author -> 0.90
      4. Last / Senior author / PI -> 0.80
      5. Middle / Contributing author -> 0.50
      6. Unknown / Missing -> 0.50 (Neutral missing-data policy)

    Parameters
    ----------
    author_position:
        Position string (e.g. 'first', 'middle', 'last', 'corresponding') or work/authors object if passed positionally.
    is_corresponding:
        Boolean indicating whether the author is corresponding author.
    authors:
        Optional sequence of ResearchWorkAuthorModel items, parent work, or author dicts.

    Returns
    -------
    float
        Normalized position weight in [0.0, 1.0].
    """
    # 1. Direct corresponding flag takes top priority
    if is_corresponding:
        return AUTHOR_POSITION_SCORES["CORRESPONDING"]

    # 2. String position check
    if author_position is not None:
        if isinstance(author_position, str) and author_position.strip():
            pos_key = author_position.strip().upper()
            return AUTHOR_POSITION_SCORES.get(pos_key, AUTHOR_POSITION_SCORES["UNKNOWN"])
        elif not isinstance(author_position, str):
            # Positional argument was actually an authors collection or parent work
            authors = author_position

    # 3. Resolve from author list / links
    if authors is not None:
        if hasattr(authors, "author_links"):
            authors = getattr(authors, "author_links")

        if not authors:
            return AUTHOR_POSITION_SCORES["UNKNOWN"]

        author_list = authors if isinstance(authors, (list, tuple, set)) else [authors]
        best_score = AUTHOR_POSITION_SCORES["UNKNOWN"]

        for a in author_list:
            if a is None:
                continue
            if getattr(a, "is_corresponding", False) or (
                isinstance(a, dict) and a.get("is_corresponding")
            ):
                return AUTHOR_POSITION_SCORES["CORRESPONDING"]

            pos = getattr(a, "author_position", None)
            if isinstance(a, dict) and pos is None:
                pos = a.get("author_position")

            if pos and isinstance(pos, str):
                score = AUTHOR_POSITION_SCORES.get(
                    pos.strip().upper(), AUTHOR_POSITION_SCORES["UNKNOWN"]
                )
                if score > best_score:
                    best_score = score

        return best_score

    return AUTHOR_POSITION_SCORES["UNKNOWN"]


# ── 4. Institution Prestige Normalization ─────────────────────────────────────


def calculate_institution_prestige(
    institutions: Sequence[Any] | Any | None = None,
    max_inst_citations: float = DEFAULT_MAX_INST_CITATIONS,
) -> float:
    """
    Calculate normalized institution prestige based on affiliated institution citation metrics.

    Multi-Institution Policy:
        Derives prestige from the maximum institution citation score among affiliated institutions:
            institution_prestige = max_{i in institutions} [ log10(1 + c_i) / log10(1 + max_inst_cit) ]

    Parameters
    ----------
    institutions:
        Sequence of institution links (ResearchWorkInstitutionModel), institution models (InstitutionModel),
        parent ResearchWorkModel, or institution dictionaries.
    max_inst_citations:
        Saturation denominator for institution citations (default 500,000 citations).

    Returns
    -------
    float
        Normalized institution prestige in [0.0, 1.0].
    """
    if max_inst_citations <= 0.0:
        raise ValueError(f"max_inst_citations must be positive, got {max_inst_citations}")

    if institutions is None:
        return 0.0

    if hasattr(institutions, "institution_links"):
        institutions = getattr(institutions, "institution_links")

    if not institutions:
        return 0.0

    denom = math.log10(1.0 + max_inst_citations)
    best_score = 0.0

    inst_list = institutions if isinstance(institutions, (list, tuple, set)) else [institutions]

    for inst_item in inst_list:
        if inst_item is None:
            continue

        cits: float | None = None

        # Check if direct institution model
        if hasattr(inst_item, "cited_by_count"):
            cits = getattr(inst_item, "cited_by_count", None)

        # Check if junction link (ResearchWorkInstitutionModel)
        if cits is None and hasattr(inst_item, "institution"):
            inst_obj = getattr(inst_item, "institution", None)
            if inst_obj is not None and hasattr(inst_obj, "cited_by_count"):
                cits = getattr(inst_obj, "cited_by_count", None)

        # Check if dictionary
        if cits is None and isinstance(inst_item, dict):
            cits = inst_item.get("cited_by_count")
            if cits is None and "institution" in inst_item and isinstance(inst_item["institution"], dict):
                cits = inst_item["institution"].get("cited_by_count")

        if cits is None or isinstance(cits, bool) or not isinstance(cits, (int, float)):
            continue

        f_cits = float(cits)
        if math.isnan(f_cits) or math.isinf(f_cits) or f_cits <= 0.0:
            continue

        inst_score = math.log10(1.0 + f_cits) / denom
        if inst_score > best_score:
            best_score = inst_score

    return round(min(1.0, max(0.0, best_score)), 6)


# ── 5. Venue Prestige Normalization ───────────────────────────────────────────


def calculate_venue_prestige(
    venue: Any | None = None,
    *,
    cited_by_count: int | float | None = None,
    is_in_doaj: bool = False,
    max_venue_citations: float = DEFAULT_MAX_VENUE_CITATIONS,
    doaj_bonus: float = DEFAULT_DOAJ_VENUE_BONUS,
) -> float:
    """
    Calculate normalized publication venue prestige.

    Combines:
      1. Logarithmic citation impact of the publication venue / journal (ResearchSourceModel).
      2. Directory of Open Access Journals (DOAJ) verified quality bonus (+0.10).

    Formula:
        venue_prestige = min(1.0, [ log10(1 + c_venue) / log10(1 + max_venue_cit) ] + (doaj_bonus if is_in_doaj else 0.0))

    Parameters
    ----------
    venue:
        Optional ResearchSourceModel ORM instance, parent ResearchWorkModel, or venue dictionary.
    cited_by_count:
        Direct citation override for venue.
    is_in_doaj:
        Boolean override for DOAJ inclusion flag.
    max_venue_citations:
        Saturation denominator for venue citations (default 100,000 citations).
    doaj_bonus:
        Quality boost for DOAJ inclusion (default 0.10).

    Returns
    -------
    float
        Normalized venue prestige score in [0.0, 1.0].
    """
    if max_venue_citations <= 0.0:
        raise ValueError(f"max_venue_citations must be positive, got {max_venue_citations}")

    eff_cits = cited_by_count
    eff_doaj = is_in_doaj

    if venue is not None:
        if hasattr(venue, "primary_source"):
            venue = getattr(venue, "primary_source")

        if eff_cits is None:
            eff_cits = getattr(venue, "cited_by_count", None)
            if isinstance(venue, dict) and eff_cits is None:
                eff_cits = venue.get("cited_by_count")

        if not eff_doaj:
            eff_doaj = bool(getattr(venue, "is_in_doaj", False))
            if isinstance(venue, dict) and not eff_doaj:
                eff_doaj = bool(venue.get("is_in_doaj", False))

    if eff_cits is None and not eff_doaj:
        return 0.0

    cit_score = 0.0
    if eff_cits is not None and not isinstance(eff_cits, bool) and isinstance(eff_cits, (int, float)):
        f_cits = float(eff_cits)
        if not math.isnan(f_cits) and not math.isinf(f_cits) and f_cits > 0.0:
            denom = math.log10(1.0 + max_venue_citations)
            cit_score = math.log10(1.0 + f_cits) / denom

    bonus = doaj_bonus if eff_doaj else 0.0
    composite = cit_score + bonus
    return round(min(1.0, max(0.0, composite)), 6)


# ── 6. Open Access Tier Normalization ─────────────────────────────────────────


def calculate_open_access_tier(
    oa_status: str | None = None,
    is_oa: bool | None = None,
) -> float:
    """
    Calculate normalized open-access accessibility tier.

    Hierarchy:
      - Gold / Diamond (Open CC license, immediate access): 1.00
      - Hybrid (Open in subscription journal): 0.85
      - Green (Repository / preprint self-archive): 0.70
      - Bronze (Free to read on publisher site, no license): 0.55
      - Closed (Paywalled access): 0.20
      - Unknown / Missing:
          - If is_oa is True -> 0.70 (defensive open baseline)
          - If is_oa is False -> 0.20
          - If is_oa is None -> 0.35 (neutral unknown)

    Parameters
    ----------
    oa_status:
        OpenAlex/Crossref OA classification: 'gold', 'hybrid', 'green', 'bronze', 'closed'.
    is_oa:
        Boolean indicating open access availability.

    Returns
    -------
    float
        Normalized OA tier in [0.0, 1.0].
    """
    if oa_status is not None and isinstance(oa_status, str) and oa_status.strip():
        key = oa_status.strip().upper()
        if key in OA_STATUS_SCORES and key != "UNKNOWN":
            return OA_STATUS_SCORES[key]

    if is_oa is True:
        return 0.70
    elif is_oa is False:
        return OA_STATUS_SCORES["CLOSED"]

    return OA_STATUS_SCORES["UNKNOWN"]


# ── 7. Canonical Academic Features Model ──────────────────────────────────────


@dataclass(frozen=True)
class AcademicFeatures:
    """
    Immutable canonical container for normalized academic ranking features.

    All feature attributes are guaranteed to be finite floats strictly bounded in [0.0, 1.0].
    """

    citation_impact: float = 0.0
    author_prominence: float = 0.0
    author_position: float = 0.50
    institution_prestige: float = 0.0
    venue_prestige: float = 0.0
    open_access_tier: float = 0.35
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate all features are numeric, finite, and in [0.0, 1.0]."""
        self.validate()

    def validate(self) -> None:
        """Assert all features are valid normalized floats."""
        features = [
            ("citation_impact", self.citation_impact),
            ("author_prominence", self.author_prominence),
            ("author_position", self.author_position),
            ("institution_prestige", self.institution_prestige),
            ("venue_prestige", self.venue_prestige),
            ("open_access_tier", self.open_access_tier),
        ]
        for name, val in features:
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ValueError(f"Feature '{name}' must be numeric, got {type(val).__name__}.")
            f_val = float(val)
            if math.isnan(f_val):
                raise ValueError(f"Feature '{name}' cannot be NaN.")
            if math.isinf(f_val):
                raise ValueError(f"Feature '{name}' cannot be infinite.")
            if f_val < 0.0 or f_val > 1.0:
                raise ValueError(f"Feature '{name}' must be in [0.0, 1.0], got {f_val}.")

    def to_dict(self) -> dict[str, float]:
        """Export features as a standard string-to-float dictionary."""
        return {
            "citation_impact": self.citation_impact,
            "author_prominence": self.author_prominence,
            "author_position": self.author_position,
            "institution_prestige": self.institution_prestige,
            "venue_prestige": self.venue_prestige,
            "open_access_tier": self.open_access_tier,
        }

    def to_vector(self) -> list[float]:
        """Export ordered feature values as a dense numerical vector."""
        return [
            self.citation_impact,
            self.author_prominence,
            self.author_position,
            self.institution_prestige,
            self.venue_prestige,
            self.open_access_tier,
        ]


# ── 8. Academic Feature Extractor Service ─────────────────────────────────────


class AcademicFeatureExtractor:
    """
    Production-grade Academic Feature Extractor.

    Extracts, normalizes, and packages canonical academic features from
    ResearchWorkModel instances, dictionaries, or candidate envelopes.
    Supports batch prefetching to eliminate N+1 database queries.
    """

    def __init__(
        self,
        max_work_citations: float = DEFAULT_MAX_WORK_CITATIONS,
        max_author_citations: float = DEFAULT_MAX_AUTHOR_CITATIONS,
        max_inst_citations: float = DEFAULT_MAX_INST_CITATIONS,
        max_venue_citations: float = DEFAULT_MAX_VENUE_CITATIONS,
        doaj_bonus: float = DEFAULT_DOAJ_VENUE_BONUS,
    ) -> None:
        self.max_work_citations = max_work_citations
        self.max_author_citations = max_author_citations
        self.max_inst_citations = max_inst_citations
        self.max_venue_citations = max_venue_citations
        self.doaj_bonus = doaj_bonus

    def extract_from_work(self, work: Any) -> AcademicFeatures:
        """
        Extract canonical normalized academic features from a single research work.

        Parameters
        ----------
        work:
            ResearchWorkModel ORM instance, dict fixture, or candidate wrapper.

        Returns
        -------
        AcademicFeatures
            Validated, normalized academic features container.
        """
        if work is None:
            return AcademicFeatures()

        # Unwrap candidate envelope if necessary
        target = getattr(work, "entity", work)
        target = getattr(target, "candidate", target)
        target = getattr(target, "candidate_work", target)

        if isinstance(target, AcademicFeatures):
            return target

        if hasattr(target, "academic_features") and getattr(target, "academic_features") is not None:
            af = getattr(target, "academic_features")
            if isinstance(af, AcademicFeatures):
                return af
            elif isinstance(af, dict):
                return AcademicFeatures(
                    citation_impact=validate_signal(af.get("citation_impact", 0.0), "citation_impact"),
                    author_prominence=validate_signal(af.get("author_prominence", 0.0), "author_prominence"),
                    author_position=validate_signal(af.get("author_position", 0.50), "author_position", default=0.50),
                    institution_prestige=validate_signal(af.get("institution_prestige", 0.0), "institution_prestige"),
                    venue_prestige=validate_signal(af.get("venue_prestige", 0.0), "venue_prestige"),
                    open_access_tier=validate_signal(af.get("open_access_tier", 0.35), "open_access_tier", default=0.35),
                )

        if isinstance(target, dict) and "academic_features" in target and target["academic_features"] is not None:
            af = target["academic_features"]
            if isinstance(af, AcademicFeatures):
                return af
            elif isinstance(af, dict):
                return AcademicFeatures(
                    citation_impact=validate_signal(af.get("citation_impact", 0.0), "citation_impact"),
                    author_prominence=validate_signal(af.get("author_prominence", 0.0), "author_prominence"),
                    author_position=validate_signal(af.get("author_position", 0.50), "author_position", default=0.50),
                    institution_prestige=validate_signal(af.get("institution_prestige", 0.0), "institution_prestige"),
                    venue_prestige=validate_signal(af.get("venue_prestige", 0.0), "venue_prestige"),
                    open_access_tier=validate_signal(af.get("open_access_tier", 0.35), "open_access_tier", default=0.35),
                )

        if isinstance(target, dict) and any(
            k in target
            for k in (
                "citation_impact",
                "author_prominence",
                "author_position",
                "institution_prestige",
                "venue_prestige",
                "open_access_tier",
            )
        ):
            return AcademicFeatures(
                citation_impact=validate_signal(target.get("citation_impact", 0.0), "citation_impact"),
                author_prominence=validate_signal(target.get("author_prominence", 0.0), "author_prominence"),
                author_position=validate_signal(target.get("author_position", 0.50), "author_position", default=0.50),
                institution_prestige=validate_signal(target.get("institution_prestige", 0.0), "institution_prestige"),
                venue_prestige=validate_signal(target.get("venue_prestige", 0.0), "venue_prestige"),
                open_access_tier=validate_signal(target.get("open_access_tier", 0.35), "open_access_tier", default=0.35),
            )

        # 1. Citation Impact
        cits = getattr(target, "cited_by_count", None)
        if isinstance(target, dict) and cits is None:
            cits = target.get("cited_by_count")
        cit_impact = calculate_citation_impact(cits, max_citations=self.max_work_citations)

        # 2. Author Prominence & Position
        authors = getattr(target, "author_links", None)
        if isinstance(target, dict) and authors is None:
            authors = target.get("author_links", target.get("authors"))

        auth_prominence = calculate_author_prominence(
            authors, max_author_citations=self.max_author_citations
        )
        auth_pos = calculate_author_position_score(authors=authors)

        # 3. Institution Prestige
        insts = getattr(target, "institution_links", None)
        if isinstance(target, dict) and insts is None:
            insts = target.get("institution_links", target.get("institutions"))
        inst_prestige = calculate_institution_prestige(
            insts, max_inst_citations=self.max_inst_citations
        )

        # 4. Venue Prestige
        venue = getattr(target, "primary_source", None)
        if isinstance(target, dict) and venue is None:
            venue = target.get("primary_source", target.get("venue"))
        venue_prestige = calculate_venue_prestige(
            venue,
            max_venue_citations=self.max_venue_citations,
            doaj_bonus=self.doaj_bonus,
        )

        # 5. Open Access Tier
        oa_status = getattr(target, "oa_status", None)
        is_oa = getattr(target, "is_oa", None)
        if isinstance(target, dict):
            if oa_status is None:
                oa_status = target.get("oa_status")
            if is_oa is None:
                is_oa = target.get("is_oa")
        oa_tier = calculate_open_access_tier(oa_status=oa_status, is_oa=is_oa)

        return AcademicFeatures(
            citation_impact=cit_impact,
            author_prominence=auth_prominence,
            author_position=auth_pos,
            institution_prestige=inst_prestige,
            venue_prestige=venue_prestige,
            open_access_tier=oa_tier,
        )

    def extract_batch(
        self,
        works: Sequence[Any],
        session: Session | None = None,
    ) -> list[AcademicFeatures]:
        """
        Extract normalized academic features for a batch of works with optional DB prefetching.

        Parameters
        ----------
        works:
            Sequence of research works or candidate objects.
        session:
            Optional active SQLAlchemy Session for efficient batch relational preloading.

        Returns
        -------
        list[AcademicFeatures]
            Ordered list of feature containers matching input sequence.
        """
        if not works:
            return []

        # If session provided, perform single-pass eager join to eliminate N+1 queries.
        if session is not None:
            work_ids: list[uuid.UUID] = []
            for w in works:
                target = getattr(w, "entity", w)
                target = getattr(target, "candidate", target)
                target = getattr(target, "candidate_work", target)
                w_id = getattr(target, "id", None)
                if w_id is None:
                    w_id = getattr(w, "candidate_work_id", None)
                if w_id is None:
                    w_id = getattr(w, "entity_id", None)
                if isinstance(target, dict) and w_id is None:
                    w_id = target.get("id", target.get("entity_id", target.get("candidate_work_id")))

                if w_id is not None:
                    try:
                        if isinstance(w_id, str):
                            w_id = uuid.UUID(w_id)
                        if isinstance(w_id, uuid.UUID):
                            work_ids.append(w_id)
                    except (ValueError, TypeError):
                        pass

            if work_ids:
                try:
                    from app.models.research_knowledge import (
                        ResearchWorkAuthorModel,
                        ResearchWorkInstitutionModel,
                        ResearchWorkModel,
                    )

                    stmt = (
                        select(ResearchWorkModel)
                        .options(
                            joinedload(ResearchWorkModel.primary_source),
                            selectinload(ResearchWorkModel.author_links).joinedload(
                                ResearchWorkAuthorModel.researcher
                            ),
                            selectinload(ResearchWorkModel.institution_links).joinedload(
                                ResearchWorkInstitutionModel.institution
                            ),
                        )
                        .where(ResearchWorkModel.id.in_(work_ids))
                    )
                    loaded_works = session.scalars(stmt).unique().all()
                    loaded_map = {lw.id: lw for lw in loaded_works}

                    results: list[AcademicFeatures] = []
                    for w in works:
                        target = getattr(w, "entity", w)
                        target = getattr(target, "candidate", target)
                        target = getattr(target, "candidate_work", target)
                        w_id = getattr(target, "id", None)
                        if w_id is None:
                            w_id = getattr(w, "candidate_work_id", None)
                        if w_id is None:
                            w_id = getattr(w, "entity_id", None)
                        if isinstance(target, dict) and w_id is None:
                            w_id = target.get("id", target.get("entity_id", target.get("candidate_work_id")))

                        resolved_id: uuid.UUID | None = None
                        if w_id is not None:
                            try:
                                resolved_id = uuid.UUID(str(w_id))
                            except (ValueError, TypeError):
                                resolved_id = None

                        populated_work = (
                            loaded_map.get(resolved_id, target)
                            if resolved_id is not None
                            else target
                        )
                        results.append(self.extract_from_work(populated_work))
                    return results
                except Exception as exc:
                    logger.warning("Batch prefetching failed, falling back to direct extraction: %s", exc)

        # Direct extraction fallback
        return [self.extract_from_work(w) for w in works]


# Global singleton instance
academic_feature_extractor = AcademicFeatureExtractor()
