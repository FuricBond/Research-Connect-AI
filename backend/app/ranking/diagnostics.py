"""
Academic Data Quality & Coverage Diagnostics for Phase 2.5D.

Provides observable, lightweight metrics to measure academic metadata coverage
(citations, authors, institutions, venues, open access) across candidate sets.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import logging
from typing import Any, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AcademicCoverageDiagnostics:
    """
    Observable diagnostic report summarizing the completeness and reliability
    of academic ranking features across a candidate set.

    Attributes
    ----------
    total_candidates:
        Total number of candidate items analyzed.
    citation_coverage:
        Proportion of candidates with non-zero citation counts in range [0.0, 1.0].
    author_coverage:
        Proportion of candidates with at least one resolved author in range [0.0, 1.0].
    institution_coverage:
        Proportion of candidates with at least one resolved institution in range [0.0, 1.0].
    venue_coverage:
        Proportion of candidates with a resolved primary venue in range [0.0, 1.0].
    oa_coverage:
        Proportion of candidates with explicit open-access status in range [0.0, 1.0].
    overall_academic_completeness:
        Unweighted arithmetic mean of all 5 coverage dimensions in range [0.0, 1.0].
    """

    total_candidates: int = 0
    citation_coverage: float = 0.0
    author_coverage: float = 0.0
    institution_coverage: float = 0.0
    venue_coverage: float = 0.0
    oa_coverage: float = 0.0
    overall_academic_completeness: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert diagnostic container to standard dictionary."""
        return asdict(self)

    @classmethod
    def from_candidates(
        cls, candidates: Sequence[Any] | None
    ) -> AcademicCoverageDiagnostics:
        """
        Compute academic metadata coverage diagnostics from a collection of candidate items.

        Parameters
        ----------
        candidates:
            Sequence of ResearchWorkModel ORM objects, SimilarResearchResult containers,
            HybridSearchResult containers, or dictionary candidate items.

        Returns
        -------
        AcademicCoverageDiagnostics
            Computed coverage diagnostics.
        """
        if not candidates:
            return cls()

        total = len(candidates)
        with_citations = 0
        with_authors = 0
        with_institutions = 0
        with_venue = 0
        with_oa = 0

        for cand in candidates:
            target = getattr(cand, "entity", cand)
            target = getattr(target, "candidate", target)
            target = getattr(target, "candidate_work", target)

            # 1. Citation check
            cits = getattr(target, "cited_by_count", None)
            if isinstance(target, dict) and cits is None:
                cits = target.get("cited_by_count")
            if (
                cits is not None
                and not isinstance(cits, bool)
                and isinstance(cits, (int, float))
                and float(cits) > 0.0
            ):
                with_citations += 1

            # 2. Author check
            authors = getattr(target, "author_links", None)
            if isinstance(target, dict) and authors is None:
                authors = target.get("author_links", target.get("authors"))
            if authors and isinstance(authors, (list, tuple, set)) and len(authors) > 0:
                with_authors += 1

            # 3. Institution check
            insts = getattr(target, "institution_links", None)
            if isinstance(target, dict) and insts is None:
                insts = target.get("institution_links", target.get("institutions"))
            if insts and isinstance(insts, (list, tuple, set)) and len(insts) > 0:
                with_institutions += 1

            # 4. Venue check
            venue = getattr(target, "primary_source", None)
            if isinstance(target, dict) and venue is None:
                venue = target.get("primary_source", target.get("venue"))
            if venue is not None:
                with_venue += 1

            # 5. Open Access check
            oa_status = getattr(target, "oa_status", None)
            is_oa = getattr(target, "is_oa", None)
            if isinstance(target, dict):
                if oa_status is None:
                    oa_status = target.get("oa_status")
                if is_oa is None:
                    is_oa = target.get("is_oa")
            if is_oa is not None or (oa_status is not None and str(oa_status).lower() != "unknown"):
                with_oa += 1

        cit_cov = round(with_citations / total, 4)
        auth_cov = round(with_authors / total, 4)
        inst_cov = round(with_institutions / total, 4)
        venue_cov = round(with_venue / total, 4)
        oa_cov = round(with_oa / total, 4)
        completeness = round(
            (cit_cov + auth_cov + inst_cov + venue_cov + oa_cov) / 5.0, 4
        )

        return cls(
            total_candidates=total,
            citation_coverage=cit_cov,
            author_coverage=auth_cov,
            institution_coverage=inst_cov,
            venue_coverage=venue_cov,
            oa_coverage=oa_cov,
            overall_academic_completeness=completeness,
        )
