"""
Multi-evidence topic assignment and confidence scoring engine.

Combines explicit source metadata (OpenAlex, Crossref), alias mappings, and rule-based
keyword inferences to assign canonical ResearchConnect topics with robust confidence scores.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ml.topic_analysis.extraction import ExtractedKeyword, KeywordExtractor
from ml.topic_analysis.normalization import TopicNormalizer
from ml.topic_analysis.taxonomy import TaxonomyNode, TaxonomyService

logger = logging.getLogger(__name__)

# Minimum confidence threshold for assigning a topic
MIN_CONFIDENCE_THRESHOLD = 0.40


@dataclass
class TopicEvidence:
    """A single piece of evidence linking an entity to a canonical topic."""
    topic_slug: str
    assignment_method: str  # SOURCE_EXPLICIT, ALIAS_MATCH, RULE_INFERRED, MANUAL
    source: str             # OpenAlex, Crossref, TitleRule, AbstractRule, KeywordRule
    raw_term: str
    confidence: float
    is_title: bool = False
    is_abstract: bool = False


@dataclass
class AssignedTopic:
    """A final assigned canonical topic with aggregated confidence and provenance."""
    topic_slug: str
    topic_name: str
    confidence_score: float
    is_primary: bool
    assignment_method: str
    source: str
    evidence_count: int
    ancestor_slugs: list[str] = field(default_factory=list)


@dataclass
class TopicAssignmentResult:
    """Complete result envelope from the topic assignment engine."""
    entity_id: str | None
    title: str
    assigned_topics: list[AssignedTopic]
    primary_topic: AssignedTopic | None
    extracted_keywords: list[str] = field(default_factory=list)


class TopicAssigner:
    """
    Topic assignment engine for Research Works, Opportunities, and academic texts.
    """

    def __init__(
        self,
        taxonomy_service: TaxonomyService | None = None,
        normalizer: TopicNormalizer | None = None,
        extractor: KeywordExtractor | None = None,
    ) -> None:
        self._taxonomy = taxonomy_service or TaxonomyService()
        self._normalizer = normalizer or TopicNormalizer(self._taxonomy)
        self._extractor = extractor or KeywordExtractor(self._normalizer)

    def _aggregate_confidence(self, confidences: list[float]) -> float:
        """
        Aggregate multiple confidence signals using Noisy-OR combination:
            C_combined = 1 - product(1 - c_i)
        Bounded to [0.0, 1.0] and rounded to 2 decimal places.
        """
        if not confidences:
            return 0.0
        product = 1.0
        for c in confidences:
            clamped = min(1.0, max(0.0, c))
            product *= (1.0 - clamped)
        combined = 1.0 - product
        return round(min(1.0, max(0.0, combined)), 2)

    def assign_topics(
        self,
        title: str,
        abstract: str | None = None,
        openalex_topics: list[dict[str, Any]] | None = None,
        crossref_subjects: list[str] | None = None,
        source_keywords: list[str] | None = None,
        entity_id: str | None = None,
    ) -> TopicAssignmentResult:
        """
        Main multi-signal topic assignment logic.

        Steps:
          1. Extract OpenAlex explicit topic evidence.
          2. Extract Crossref explicit subject evidence.
          3. Extract keyword rule evidence from title & abstract.
          4. Group evidence by canonical topic slug.
          5. Aggregate multi-source confidence scores.
          6. Select primary topic based on evidence strength, title anchoring, and taxonomy depth.
        """
        evidence_by_slug: dict[str, list[TopicEvidence]] = {}

        def add_evidence(ev: TopicEvidence) -> None:
            if ev.topic_slug in self._taxonomy._by_slug:
                evidence_by_slug.setdefault(ev.topic_slug, []).append(ev)

        # 1. OpenAlex Topics Evidence
        if openalex_topics:
            for item in openalex_topics:
                if not isinstance(item, dict):
                    continue
                slug, source_score = self._normalizer.resolve_openalex_topic(item)
                if slug:
                    # Scale source score [0.0 - 1.0] to confidence [0.75 - 0.98]
                    calibrated = min(0.98, max(0.75, 0.70 + (source_score * 0.28)))
                    add_evidence(
                        TopicEvidence(
                            topic_slug=slug,
                            assignment_method="SOURCE_EXPLICIT",
                            source="OpenAlex",
                            raw_term=item.get("display_name", slug),
                            confidence=calibrated,
                        )
                    )

        # 2. Crossref Subjects Evidence
        if crossref_subjects:
            for sub in crossref_subjects:
                if not sub:
                    continue
                slug = self._normalizer.resolve_crossref_subject(sub)
                if slug:
                    add_evidence(
                        TopicEvidence(
                            topic_slug=slug,
                            assignment_method="SOURCE_EXPLICIT",
                            source="Crossref",
                            raw_term=sub,
                            confidence=0.80,
                        )
                    )

        # 3. Keyword Rule Evidence from Title, Abstract, and Keywords
        extracted_kws = self._extractor.extract_keywords(
            title=title,
            abstract=abstract,
            source_keywords=source_keywords,
        )

        for kw in extracted_kws:
            if kw.canonical_topic_slug:
                slug = kw.canonical_topic_slug
                # Title matches are weighted significantly higher than abstract mentions
                if kw.is_title:
                    conf = 0.75
                    source_name = "TitleRule"
                elif kw.is_abstract:
                    conf = 0.55
                    source_name = "AbstractRule"
                else:
                    conf = 0.65
                    source_name = "KeywordRule"

                add_evidence(
                    TopicEvidence(
                        topic_slug=slug,
                        assignment_method="RULE_INFERRED",
                        source=source_name,
                        raw_term=kw.raw_term,
                        confidence=conf,
                        is_title=kw.is_title,
                        is_abstract=kw.is_abstract,
                    )
                )

        # 4. Aggregate topics
        assigned_list: list[AssignedTopic] = []
        for slug, ev_list in evidence_by_slug.items():
            confidences = [e.confidence for e in ev_list]
            agg_conf = self._aggregate_confidence(confidences)

            if agg_conf < MIN_CONFIDENCE_THRESHOLD:
                continue

            node = self._taxonomy.get_node(slug)
            topic_name = node.name if node else slug

            # Determine dominant assignment method and primary source
            has_explicit = any(e.assignment_method == "SOURCE_EXPLICIT" for e in ev_list)
            has_alias = any(e.assignment_method == "ALIAS_MATCH" for e in ev_list)
            if has_explicit:
                method = "SOURCE_EXPLICIT"
            elif has_alias:
                method = "ALIAS_MATCH"
            else:
                method = "RULE_INFERRED"

            sources = list(dict.fromkeys(e.source for e in ev_list))
            dominant_source = ", ".join(sources)

            ancestor_slugs = self._taxonomy.get_ancestors(slug)

            assigned_list.append(
                AssignedTopic(
                    topic_slug=slug,
                    topic_name=topic_name,
                    confidence_score=agg_conf,
                    is_primary=False,
                    assignment_method=method,
                    source=dominant_source,
                    evidence_count=len(ev_list),
                    ancestor_slugs=ancestor_slugs,
                )
            )

        # 5. Primary Topic Selection
        # Ranking criteria:
        #   1. Title presence (is_title evidence in topic)
        #   2. Confidence score
        #   3. Taxonomy depth (prefer specific topics like 'Large Language Models' over broad 'Computer Science')
        def ranking_key(item: AssignedTopic) -> tuple[int, float, int]:
            evs = evidence_by_slug.get(item.topic_slug, [])
            has_title = int(any(e.is_title for e in evs))
            depth = self._taxonomy.get_depth(item.topic_slug)
            return (has_title, item.confidence_score, depth)

        assigned_list.sort(key=ranking_key, reverse=True)

        primary_topic: AssignedTopic | None = None
        if assigned_list:
            assigned_list[0].is_primary = True
            primary_topic = assigned_list[0]

        return TopicAssignmentResult(
            entity_id=entity_id,
            title=title,
            assigned_topics=assigned_list,
            primary_topic=primary_topic,
            extracted_keywords=[k.keyword for k in extracted_kws],
        )

    def assign_research_work(self, work: Any) -> TopicAssignmentResult:
        """Assign canonical topics to a ResearchWorkModel or normalized work dictionary."""
        if isinstance(work, dict):
            title = work.get("title", "")
            abstract = work.get("abstract")
            raw_meta = work.get("raw_metadata") or {}
            work_id = str(work.get("id")) if work.get("id") else None
        else:
            title = getattr(work, "title", "")
            abstract = getattr(work, "abstract", None)
            raw_meta = getattr(work, "raw_metadata", {}) or {}
            work_id = str(getattr(work, "id", None)) if getattr(work, "id", None) else None

        # Extract OpenAlex topics from raw_metadata
        openalex_topics = raw_meta.get("topics") if isinstance(raw_meta, dict) else None

        # Extract Crossref subjects from raw_metadata
        crossref_subjects = None
        if isinstance(raw_meta, dict) and "crossref" in raw_meta:
            crossref_subjects = raw_meta["crossref"].get("subject")

        return self.assign_topics(
            title=title,
            abstract=abstract,
            openalex_topics=openalex_topics,
            crossref_subjects=crossref_subjects,
            entity_id=work_id,
        )

    def assign_opportunity(self, opp: Any) -> TopicAssignmentResult:
        """Assign canonical topics to an OpportunityModel or dictionary."""
        if isinstance(opp, dict):
            title = opp.get("title", "")
            summary = opp.get("summary")
            desc = opp.get("description")
            opp_id = str(opp.get("id")) if opp.get("id") else None
        else:
            title = getattr(opp, "title", "")
            summary = getattr(opp, "summary", None)
            desc = getattr(opp, "description", None)
            opp_id = str(getattr(opp, "id", None)) if getattr(opp, "id", None) else None

        combined_text = f"{summary or ''} {desc or ''}".strip() or None

        return self.assign_topics(
            title=title,
            abstract=combined_text,
            entity_id=opp_id,
        )
