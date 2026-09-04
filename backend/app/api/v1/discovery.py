"""
FastAPI Discovery API Router (Phase 2.4G).

Exposes versioned discovery endpoints for:
  - Hybrid research work search
  - Similar research work retrieval
  - Research ↔ opportunity matching
  - Explainable result attributions
"""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.explainability.result_explainer import (
    ResultExplanation,
    result_explainer,
)
from app.ranking.diversity import diversity_reranker
from app.ranking.hybrid_ranker import (
    HybridRanker,
    RankedCandidate,
    RankingMode,
    hybrid_ranker,
)
from app.ranking.reranker import cross_encoder_reranker
from app.models.research_knowledge import ResearchWorkModel
from app.schemas.discovery import (
    AcademicEvidenceSchema,
    DiversityExplanationSchema,
    ExplanationSchema,
    OpportunityMatchItem,
    OpportunityMatchResponse,
    ProvenanceEvidenceSchema,
    QueryIntelligenceSchema,
    RankingComparisonRequest,
    RankingComparisonResponse,
    RerankerExplanationSchema,
    ResearchSearchResponse,
    ResearchSearchResultItem,
    ResearchWorkRead,
    ScoreBreakdownSchema,
    SignalContributionSchema,
    SimilarResearchItem,
    SimilarResearchResponse,
    TopicEvidenceSchema,
)
from app.ranking.deadline import deadline_explainability_service
from app.ranking.risk import assess_opportunity_risk, risk_explainability_service
from app.search.query_intelligence import query_intelligence_service
from app.schemas.deadline import OpportunityDeadlineSchema
from app.schemas.opportunity import (
    OpportunityListItem,
    OpportunityRead,
    RiskExplanationSchema,
)
from app.services.opportunity_service import (
    DeliveryMode,
    OpportunityStatus,
    OpportunityType,
)
from app.services.hybrid_search_service import (
    HybridSearchResult,
    HybridSearchService,
    hybrid_search_service,
)
from app.services.research_opportunity_matching_service import (
    ResearchOpportunityMatch,
    ResearchOpportunityMatchingService,
    research_opportunity_matching_service,
)
from app.services.similar_research_service import (
    MissingEmbeddingError,
    ResearchWorkNotFoundError,
    SimilarResearchResult,
    SimilarResearchService,
    similar_research_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discovery", tags=["discovery"])

DbDep = Annotated[Session, Depends(get_db)]


def _to_explanation_schema(explanation: ResultExplanation | None) -> ExplanationSchema | None:
    """Convert an internal ResultExplanation model to its Pydantic API representation."""
    if explanation is None:
        return None

    contributions_dict: dict[str, SignalContributionSchema] = {}
    for name, sc in explanation.signal_contributions.items():
        contributions_dict[name] = SignalContributionSchema(
            signal_name=sc.signal_name,
            score=sc.score,
            weight=sc.weight,
            contribution=sc.contribution,
            qualitative_assessment=sc.qualitative_assessment,
            is_available=sc.is_available,
            is_primary_driver=sc.is_primary_driver,
            raw_value=sc.raw_value,
            is_active=sc.is_active,
        )

    topic_schema = TopicEvidenceSchema(
        shared_topic_ids=explanation.topic_evidence.shared_topic_ids,
        shared_topic_names=explanation.topic_evidence.shared_topic_names,
        topic_similarity=explanation.topic_evidence.topic_similarity,
        description=explanation.topic_evidence.description,
    )

    prov_schema = ProvenanceEvidenceSchema(
        retrieval_sources=explanation.provenance_evidence.retrieval_sources,
        description=explanation.provenance_evidence.description,
    )

    sb_schema: ScoreBreakdownSchema | None = None
    if explanation.score_breakdown:
        sb_schema = ScoreBreakdownSchema.model_validate(explanation.score_breakdown)

    acad_schema: AcademicEvidenceSchema | None = None
    if explanation.academic_evidence:
        acad_schema = AcademicEvidenceSchema.model_validate(explanation.academic_evidence)

    rerank_schema: RerankerExplanationSchema | None = None
    if explanation.reranker_explanation:
        rerank_schema = RerankerExplanationSchema.model_validate(explanation.reranker_explanation)

    div_schema: DiversityExplanationSchema | None = None
    if explanation.diversity_explanation:
        div_schema = DiversityExplanationSchema.model_validate(explanation.diversity_explanation)

    return ExplanationSchema(
        summary=explanation.summary,
        strengths=explanation.strengths,
        limitations=explanation.limitations,
        signal_contributions=contributions_dict,
        topic_evidence=topic_schema,
        provenance_evidence=prov_schema,
        primary_factors=explanation.primary_factors,
        final_score=explanation.final_score,
        rank=explanation.rank,
        base_score=explanation.base_score,
        score_breakdown=sb_schema,
        academic_evidence=acad_schema,
        reranker_explanation=rerank_schema,
        diversity_explanation=div_schema,
    )


# ── 1. Research Search Endpoint ───────────────────────────────────────────────


@router.get(
    "/research/search",
    response_model=ResearchSearchResponse,
    summary="Search Research Works",
    description="Execute multi-channel hybrid search (semantic dense embeddings + lexical full-text) over research works with optional hybrid ranking and explainability.",
)
def search_research_works_route(
    db: DbDep,
    q: Annotated[
        str,
        Query(
            min_length=1,
            description="Natural language query string",
            examples=["Machine learning methods for medical image analysis"],
        ),
    ],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of items to return",
        ),
    ] = 20,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of initial items to skip for pagination",
        ),
    ] = 0,
    publication_year: Annotated[
        int | None,
        Query(description="Filter by exact publication year"),
    ] = None,
    min_year: Annotated[
        int | None,
        Query(description="Filter by minimum publication year"),
    ] = None,
    max_year: Annotated[
        int | None,
        Query(description="Filter by maximum publication year"),
    ] = None,
    work_type: Annotated[
        str | None,
        Query(description="Filter by work type (article, preprint, etc.)"),
    ] = None,
    language: Annotated[
        str | None,
        Query(description="Filter by language code (e.g. 'en')"),
    ] = None,
    primary_source_id: Annotated[
        uuid.UUID | None,
        Query(description="Filter by primary publication venue UUID"),
    ] = None,
    is_oa: Annotated[
        bool | None,
        Query(description="Filter by Open Access availability"),
    ] = None,
    min_citations: Annotated[
        int | None,
        Query(ge=0, description="Filter by minimum citation count"),
    ] = None,
    exclude_work_id: Annotated[
        uuid.UUID | None,
        Query(description="Research work UUID to exclude from results"),
    ] = None,
    ranking_mode: Annotated[
        RankingMode,
        Query(description="Hybrid ranking mode"),
    ] = RankingMode.GENERAL,
    explain: Annotated[
        bool,
        Query(description="Include structured explainability rationale"),
    ] = False,
    include_query_intelligence: Annotated[
        bool,
        Query(description="Include deterministic query normalization and acronym expansion metadata"),
    ] = False,
    rerank: Annotated[
        bool,
        Query(description="Apply optional lightweight cross-encoder reranking on top candidates"),
    ] = False,
    diversity: Annotated[
        bool,
        Query(description="Apply deterministic list-aware diversity and novelty reranking (Phase 2.5E)"),
    ] = False,
) -> ResearchSearchResponse:
    """Search research works using hybrid retrieval, ranking, and explainability."""
    try:
        # Retrieve candidate pool from HybridSearchService
        fetch_limit = min(100, limit + offset)
        candidates = hybrid_search_service.search_research_works(
            session=db,
            query=q,
            limit=fetch_limit,
            exclude_work_id=exclude_work_id,
            publication_year=publication_year,
            min_year=min_year,
            max_year=max_year,
            work_type=work_type,
            language=language,
            primary_source_id=primary_source_id,
            is_oa=is_oa,
            min_citations=min_citations,
        )

        # Rank candidates via HybridRanker with eager relational batch preloading
        ranked = hybrid_ranker.rank(
            candidates=candidates,
            mode=ranking_mode,
            limit=fetch_limit,
            session=db,
        )

        # Optional Cross-Encoder Reranking
        if rerank or getattr(settings, "reranker_enabled", False):
            ranked = cross_encoder_reranker.rerank(
                query=q,
                candidates=ranked,
                force_enabled=rerank,
            )

        # Optional Diversity & Novelty Reranking (Phase 2.5E)
        if diversity:
            ranked = diversity_reranker.rerank(
                candidates=ranked,
                mode=ranking_mode,
                force_enabled=True,
            )

        total = len(ranked)
        sliced = ranked[offset : offset + limit]
        has_more = (offset + limit) < total

        # Optional Explainability
        explanations_map: dict[uuid.UUID, ResultExplanation] = {}
        if explain and sliced:
            explained_batch = result_explainer.explain_batch(
                sliced,
                mode=ranking_mode,
            )
            for item in explained_batch:
                explanations_map[item.result.entity_id] = item.explanation

        # Optional Query Intelligence Metadata
        qi_schema: QueryIntelligenceSchema | None = None
        if include_query_intelligence:
            qi_res = query_intelligence_service.process(q)
            qi_schema = QueryIntelligenceSchema(
                original_query=qi_res.original_query,
                normalized_query=qi_res.normalized_query,
                expanded_query=qi_res.expanded_query,
                was_expanded=qi_res.was_expanded,
                detected_acronyms=qi_res.detected_acronyms,
                detected_terms=qi_res.detected_terms,
                transformations=qi_res.transformations,
            )

        # Build output items
        items: list[ResearchSearchResultItem] = []
        for cand in sliced:
            work_read: ResearchWorkRead
            if cand.candidate is not None:
                work_read = ResearchWorkRead.model_validate(cand.candidate)
            else:
                work_read = ResearchWorkRead(
                    id=cand.entity_id,
                    title="Unknown Title",
                    cited_by_count=0,
                    is_oa=False,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )

            expl_schema = _to_explanation_schema(explanations_map.get(cand.entity_id))

            items.append(
                ResearchSearchResultItem(
                    work=work_read,
                    rank=cand.rank,
                    final_score=cand.final_score,
                    semantic_score=cand.semantic_score,
                    lexical_score=cand.lexical_score,
                    topic_score=cand.topic_score,
                    freshness_score=cand.freshness_score,
                    quality_score=cand.quality_score,
                    retrieval_sources=cand.retrieval_sources,
                    explanation=expl_schema,
                    diversity_adjustment=cand.diversity_adjustment,
                    novelty_score=cand.novelty_score,
                    redundancy_score=cand.redundancy_score,
                )
            )

        return ResearchSearchResponse(
            query=q,
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=has_more,
            ranking_mode=ranking_mode.value,
            query_intelligence=qi_schema,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error executing research search: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while executing research search.",
        ) from exc


# ── 2. Similar Research Endpoint ──────────────────────────────────────────────


@router.get(
    "/research/{work_id}/similar",
    response_model=SimilarResearchResponse,
    summary="Retrieve Similar Research Works",
    description="Retrieve research works similar to a specified source research work based on semantic embeddings, lexical overlap, and canonical taxonomy DAG proximity.",
)
def get_similar_research_route(
    work_id: uuid.UUID,
    db: DbDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of items to return",
        ),
    ] = 20,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of initial items to skip for pagination",
        ),
    ] = 0,
    publication_year: Annotated[
        int | None,
        Query(description="Filter by exact publication year"),
    ] = None,
    min_year: Annotated[
        int | None,
        Query(description="Filter by minimum publication year"),
    ] = None,
    max_year: Annotated[
        int | None,
        Query(description="Filter by maximum publication year"),
    ] = None,
    work_type: Annotated[
        str | None,
        Query(description="Filter by work type (article, preprint, etc.)"),
    ] = None,
    language: Annotated[
        str | None,
        Query(description="Filter by language code (e.g. 'en')"),
    ] = None,
    primary_source_id: Annotated[
        uuid.UUID | None,
        Query(description="Filter by primary venue UUID"),
    ] = None,
    is_oa: Annotated[
        bool | None,
        Query(description="Filter by Open Access status"),
    ] = None,
    min_citations: Annotated[
        int | None,
        Query(ge=0, description="Filter by minimum citation count"),
    ] = None,
    ranking_mode: Annotated[
        RankingMode,
        Query(description="Hybrid ranking mode"),
    ] = RankingMode.RESEARCH_SIMILARITY,
    explain: Annotated[
        bool,
        Query(description="Include structured explainability rationale"),
    ] = False,
    require_embedding: Annotated[
        bool,
        Query(description="Fail with 422 if source work has no embedding"),
    ] = False,
    diversity: Annotated[
        bool,
        Query(description="Apply deterministic list-aware diversity and novelty reranking (Phase 2.5E)"),
    ] = False,
) -> SimilarResearchResponse:
    """Retrieve similar research works with multi-signal similarity and explainability."""
    try:
        fetch_limit = min(100, limit + offset)
        candidates = similar_research_service.get_similar_research(
            session=db,
            work_id=work_id,
            limit=fetch_limit,
            publication_year=publication_year,
            min_year=min_year,
            max_year=max_year,
            work_type=work_type,
            language=language,
            primary_source_id=primary_source_id,
            is_oa=is_oa,
            min_citations=min_citations,
            require_embedding=require_embedding,
        )

        ranked = hybrid_ranker.rank(
            candidates=candidates,
            mode=ranking_mode,
            limit=fetch_limit,
            session=db,
        )

        # Optional Diversity & Novelty Reranking (Phase 2.5E)
        if diversity:
            ranked = diversity_reranker.rerank(
                candidates=ranked,
                mode=ranking_mode,
                force_enabled=True,
            )

        total = len(ranked)
        sliced = ranked[offset : offset + limit]
        has_more = (offset + limit) < total

        explanations_map: dict[uuid.UUID, ResultExplanation] = {}
        if explain and sliced:
            explained_batch = result_explainer.explain_batch(
                sliced,
                mode=ranking_mode,
            )
            for item in explained_batch:
                explanations_map[item.result.entity_id] = item.explanation

        items: list[SimilarResearchItem] = []
        for cand in sliced:
            work_read: ResearchWorkRead
            if cand.candidate is not None:
                work_read = ResearchWorkRead.model_validate(cand.candidate)
            else:
                work_read = ResearchWorkRead(
                    id=cand.entity_id,
                    title="Unknown Title",
                    cited_by_count=0,
                    is_oa=False,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )

            expl_schema = _to_explanation_schema(explanations_map.get(cand.entity_id))

            items.append(
                SimilarResearchItem(
                    work=work_read,
                    rank=cand.rank,
                    combined_similarity=cand.final_score,
                    semantic_similarity=cand.semantic_score,
                    lexical_similarity=cand.lexical_score,
                    topic_similarity=cand.topic_score,
                    freshness=cand.freshness_score,
                    shared_topic_ids=cand.shared_topic_ids,
                    shared_topic_names=cand.shared_topic_names,
                    retrieval_sources=cand.retrieval_sources,
                    explanation=expl_schema,
                    diversity_adjustment=cand.diversity_adjustment,
                    novelty_score=cand.novelty_score,
                    redundancy_score=cand.redundancy_score,
                )
            )

        return SimilarResearchResponse(
            source_work_id=work_id,
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=has_more,
            ranking_mode=ranking_mode.value,
        )

    except ResearchWorkNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research work '{work_id}' was not found.",
        ) from exc
    except MissingEmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Source research work '{work_id}' does not have a vector embedding.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error retrieving similar research for %s: %s", work_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving similar research.",
        ) from exc


# ── 3. Research ↔ Opportunity Matching Endpoint ───────────────────────────────


@router.get(
    "/research/{work_id}/opportunities",
    response_model=OpportunityMatchResponse,
    summary="Match Academic Opportunities for Research Work",
    description="Match and rank relevant academic opportunities (conferences, journals, workshops, CFPs) for a given research work based on semantic relevance, topic overlap, type compatibility, and deadline urgency.",
)
def match_opportunities_for_research_route(
    work_id: uuid.UUID,
    db: DbDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of items to return",
        ),
    ] = 20,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of initial items to skip for pagination",
        ),
    ] = 0,
    opportunity_type: Annotated[
        OpportunityType | None,
        Query(description="Filter by opportunity category"),
    ] = None,
    status_filter: Annotated[
        OpportunityStatus | None,
        Query(alias="status", description="Filter by opportunity status"),
    ] = None,
    delivery_mode: Annotated[
        DeliveryMode | None,
        Query(description="Filter by delivery mode"),
    ] = None,
    source_id: Annotated[
        uuid.UUID | None,
        Query(description="Filter by origin ingestion source UUID"),
    ] = None,
    upcoming_only: Annotated[
        bool,
        Query(description="Only show opportunities with future submission deadline"),
    ] = False,
    submission_deadline_after: Annotated[
        datetime | None,
        Query(description="Filter deadlines after datetime"),
    ] = None,
    max_apc_usd: Annotated[
        float | None,
        Query(
            ge=0.0,
            description="Maximum acceptable Article Processing Charge or registration fee in USD",
        ),
    ] = None,
    require_known_apc: Annotated[
        bool,
        Query(description="If True, exclude opportunities with unknown/missing APC metadata"),
    ] = False,
    location: Annotated[
        str | None,
        Query(description="Filter opportunities by city, country, or location keyword"),
    ] = None,
    ranking_mode: Annotated[
        RankingMode,
        Query(description="Hybrid ranking mode"),
    ] = RankingMode.RESEARCH_OPPORTUNITY,
    explain: Annotated[
        bool,
        Query(description="Include structured explainability rationale"),
    ] = False,
    require_embedding: Annotated[
        bool,
        Query(description="Fail with 422 if source work has no embedding"),
    ] = False,
    diversity: Annotated[
        bool,
        Query(description="Apply deterministic list-aware diversity and novelty reranking (Phase 2.5E)"),
    ] = False,
) -> OpportunityMatchResponse:
    """Match academic opportunities to a research work with multi-signal ranking and explainability."""
    try:
        fetch_limit = min(100, limit + offset)
        candidates = research_opportunity_matching_service.match_opportunities(
            session=db,
            work_id=work_id,
            limit=fetch_limit,
            opportunity_type=opportunity_type.value if opportunity_type else None,
            status=status_filter.value if status_filter else None,
            delivery_mode=delivery_mode.value if delivery_mode else None,
            source_id=source_id,
            upcoming_only=upcoming_only,
            submission_deadline_after=submission_deadline_after,
            max_apc_usd=max_apc_usd,
            require_known_apc=require_known_apc,
            location=location,
            require_embedding=require_embedding,
        )

        ranked = hybrid_ranker.rank(
            candidates=candidates,
            mode=ranking_mode,
            limit=fetch_limit,
            session=db,
        )

        # Optional Diversity & Novelty Reranking (Phase 2.5E)
        if diversity:
            ranked = diversity_reranker.rerank(
                candidates=ranked,
                mode=ranking_mode,
                force_enabled=True,
            )

        total = len(ranked)
        sliced = ranked[offset : offset + limit]
        has_more = (offset + limit) < total

        explanations_map: dict[uuid.UUID, ResultExplanation] = {}
        risk_explanations_map: dict[uuid.UUID, RiskExplanationSchema] = {}
        deadline_explanations_map: dict[uuid.UUID, OpportunityDeadlineSchema] = {}
        if explain and sliced:
            explained_batch = result_explainer.explain_batch(
                sliced,
                mode=ranking_mode,
            )
            for item in explained_batch:
                explanations_map[item.result.entity_id] = item.explanation

            # Phase 2.6F: Generate Deterministic Risk & Trust Explanations
            for cand in sliced:
                if cand.candidate is not None:
                    assessment = assess_opportunity_risk(cand.candidate)
                    risk_expl = risk_explainability_service.explain(assessment, opportunity=cand.candidate)
                    risk_explanations_map[cand.entity_id] = RiskExplanationSchema.model_validate(risk_expl.to_dict())

            # Phase 2.7F: Generate Deterministic Deadline Explanations
            for cand in sliced:
                if cand.candidate is not None:
                    deadline_expl = deadline_explainability_service.explain_opportunity_from_model(cand.candidate)
                    deadline_explanations_map[cand.entity_id] = deadline_expl

        items: list[OpportunityMatchItem] = []
        for cand in sliced:
            opp_read: OpportunityRead
            if cand.candidate is not None:
                opp_read = OpportunityRead.model_validate(cand.candidate)
            else:
                opp_read = OpportunityRead(
                    id=cand.entity_id,
                    title="Unknown Opportunity",
                    opportunity_type="CONFERENCE",
                    delivery_mode="ONLINE",
                    is_predatory_flag=False,
                    status="ACTIVE",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )

            expl_schema = _to_explanation_schema(explanations_map.get(cand.entity_id))
            risk_expl_schema = risk_explanations_map.get(cand.entity_id)
            deadline_expl_schema = deadline_explanations_map.get(cand.entity_id)

            if risk_expl_schema is not None:
                opp_read.risk_level = risk_expl_schema.risk_level
                opp_read.risk_confidence = risk_expl_schema.risk_confidence
                opp_read.risk_explanation = risk_expl_schema

            if deadline_expl_schema is not None:
                opp_read.deadline_intelligence = deadline_expl_schema

            items.append(
                OpportunityMatchItem(
                    opportunity=opp_read,
                    rank=cand.rank,
                    match_score=cand.final_score,
                    semantic_similarity=cand.semantic_score,
                    lexical_similarity=cand.lexical_score,
                    topic_similarity=cand.topic_score,
                    type_compatibility=cand.type_score,
                    urgency=cand.urgency_score,
                    quality_score=cand.quality_score,
                    shared_topic_ids=cand.shared_topic_ids,
                    shared_topic_names=cand.shared_topic_names,
                    retrieval_sources=cand.retrieval_sources,
                    explanation=expl_schema,
                    risk_explanation=risk_expl_schema,
                    deadline_explanation=deadline_expl_schema,
                    diversity_adjustment=cand.diversity_adjustment,
                    novelty_score=cand.novelty_score,
                    redundancy_score=cand.redundancy_score,
                )
            )

        return OpportunityMatchResponse(
            research_work_id=work_id,
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=has_more,
            ranking_mode=ranking_mode.value,
        )

    except ResearchWorkNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research work '{work_id}' was not found.",
        ) from exc
    except MissingEmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Source research work '{work_id}' does not have a vector embedding.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error matching opportunities for work %s: %s", work_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while matching opportunities.",
        ) from exc


# ── 4. Comparative Ranking Explanation Endpoint (Phase 2.5F) ───────────────


@router.post(
    "/research/compare",
    response_model=RankingComparisonResponse,
    summary="Compare Two Ranked Research Works",
    description="Deterministic comparative attribution explaining why Result A was ranked above Result B (Phase 2.5F).",
)
def compare_research_works_route(
    db: DbDep,
    request: RankingComparisonRequest,
) -> RankingComparisonResponse:
    """Compare two research works and attribute why one scored higher than the other."""
    try:
        work_a = db.get(ResearchWorkModel, request.candidate_a_id)
        if not work_a:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Research work '{request.candidate_a_id}' was not found.",
            )

        work_b = db.get(ResearchWorkModel, request.candidate_b_id)
        if not work_b:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Research work '{request.candidate_b_id}' was not found.",
            )

        try:
            mode = RankingMode(request.ranking_mode.lower())
        except ValueError:
            mode = RankingMode.GENERAL

        items_to_rank = [work_a, work_b]

        ranked = hybrid_ranker.rank(
            candidates=items_to_rank,
            mode=mode,
            session=db,
        )

        cand_a = next((c for c in ranked if c.entity_id == request.candidate_a_id), ranked[0])
        cand_b = next((c for c in ranked if c.entity_id == request.candidate_b_id), ranked[1] if len(ranked) > 1 else ranked[0])

        comp = result_explainer.compare(cand_a, cand_b, mode=mode)

        return RankingComparisonResponse.model_validate(comp)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error comparing research works %s and %s: %s", request.candidate_a_id, request.candidate_b_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while comparing research works.",
        ) from exc

