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
from app.ranking.hybrid_ranker import (
    HybridRanker,
    RankedCandidate,
    RankingMode,
    hybrid_ranker,
)
from app.ranking.reranker import cross_encoder_reranker
from app.schemas.discovery import (
    ExplanationSchema,
    OpportunityMatchItem,
    OpportunityMatchResponse,
    ProvenanceEvidenceSchema,
    QueryIntelligenceSchema,
    ResearchSearchResponse,
    ResearchSearchResultItem,
    ResearchWorkRead,
    SignalContributionSchema,
    SimilarResearchItem,
    SimilarResearchResponse,
    TopicEvidenceSchema,
)
from app.search.query_intelligence import query_intelligence_service
from app.schemas.opportunity import (
    OpportunityListItem,
    OpportunityRead,
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

        # Rank candidates via HybridRanker
        ranked = hybrid_ranker.rank(
            candidates=candidates,
            mode=ranking_mode,
            limit=fetch_limit,
        )

        # Optional Cross-Encoder Reranking
        if rerank or getattr(settings, "reranker_enabled", False):
            ranked = cross_encoder_reranker.rerank(
                query=q,
                candidates=ranked,
                force_enabled=rerank,
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
