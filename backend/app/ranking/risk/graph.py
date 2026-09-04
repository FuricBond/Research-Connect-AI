"""
Academic Trust Graph & Suspicious Pattern Intelligence for Phase 2.6E.

Constructs an in-memory, deterministic academic trust graph linking:
Opportunity -> Venue -> Publisher -> Organizer -> Domain -> ISSN -> ResearchSource

Detects observable suspicious structural patterns:
  - HIGH_ORGANIZER_REUSE
  - HIGH_DOMAIN_REUSE
  - GRAPH_IDENTITY_CONFLICT
  - SUSPICIOUS_ORGANIZER_CLUSTER
  - SUSPICIOUS_PUBLISHER_CLUSTER
  - CONSISTENT_GRAPH_IDENTITY (Positive trust corroboration)

Enforces:
  1. 100% in-memory, zero network calls, zero database queries.
  2. Graph Degree Alone != Predatory (Strict safeguards for trusted societies & publishers).
  3. Isolated Node Neutrality (UNKNOWN != PREDATORY).
  4. Anti-correlation / Correlated Evidence Deduplication.
  5. Deterministic node/edge canonicalization and sorting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
import re
from typing import Any

from app.ranking.risk.extractors import _get_field
from app.ranking.risk.models import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceProvenance,
    EvidenceSignal,
    EvidenceStrength,
    ResolutionStatus,
    ResolvedAcademicEntity,
    RiskEvidence,
    RiskEvidenceCollection,
)
from app.ranking.risk.normalizers import normalize_url, validate_issn
from app.ranking.risk.registries import (
    match_trusted_publisher,
    match_trusted_society,
)
from app.ranking.risk.venue_intelligence import (
    PUBLISHER_DOMAINS,
)
from app.ranking.venue_intelligence import get_canonical_venue_key, normalize_venue_name

logger = logging.getLogger(__name__)

# ── Threshold Constants (Deterministic, Documented) ───────────────────────────

MAX_LEGITIMATE_UNVERIFIED_ORGANIZER_EVENTS: int = 5
MAX_LEGITIMATE_UNVERIFIED_DOMAIN_ENTITIES: int = 4
MIN_CLUSTER_OPPORTUNITIES: int = 3
MIN_CLUSTER_SUSPICIOUS_OPPORTUNITIES: int = 2

# Known legitimate shared hosting platforms & academic preprint / submission hosts
# Domains here host hundreds of legitimate conferences and must never be flagged for reuse
LEGITIMATE_SHARED_PLATFORMS: set[str] = {
    "edas.info",
    "easychair.org",
    "openreview.net",
    "confconference.org",
    "acm.org",
    "ieee.org",
    "springer.com",
    "nature.com",
    "elsevier.com",
    "wiley.com",
    "sciencedirect.com",
    "tandfonline.com",
    "oup.com",
    "cambridge.org",
    "frontiersin.org",
    "mdpi.com",
    "plos.org",
    "arxiv.org",
    "biorxiv.org",
    "medrxiv.org",
    "github.com",
    "gitlab.com",
    "orcid.org",
    "crossref.org",
    "openalex.org",
    "doaj.org",
}


class TrustNodeType(str, Enum):
    """Canonical node types in the academic trust graph."""

    OPPORTUNITY = "OPPORTUNITY"
    VENUE = "VENUE"
    PUBLISHER = "PUBLISHER"
    ORGANIZER = "ORGANIZER"
    DOMAIN = "DOMAIN"
    ISSN = "ISSN"
    RESEARCH_SOURCE = "RESEARCH_SOURCE"


class TrustEdgeType(str, Enum):
    """Canonical edge types representing verified or extracted relationships."""

    OPPORTUNITY_IN_VENUE = "OPPORTUNITY_IN_VENUE"
    VENUE_PUBLISHED_BY = "VENUE_PUBLISHED_BY"
    VENUE_ORGANIZED_BY = "VENUE_ORGANIZED_BY"
    OPPORTUNITY_ORGANIZED_BY = "OPPORTUNITY_ORGANIZED_BY"
    HAS_DOMAIN = "HAS_DOMAIN"
    HAS_IDENTIFIER = "HAS_IDENTIFIER"
    LINKED_TO_SOURCE = "LINKED_TO_SOURCE"


@dataclass
class TrustNode:
    """A canonical entity node in the trust graph."""

    id: str
    node_type: TrustNodeType
    label: str
    is_verified: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "node_type": self.node_type.value,
            "label": self.label,
            "is_verified": self.is_verified,
            "metadata": dict(self.metadata),
        }


@dataclass
class TrustEdge:
    """A directed edge between canonical entities with provenance."""

    source: str
    target: str
    edge_type: TrustEdgeType
    provenance: str = EvidenceProvenance.DERIVED.value
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type.value,
            "provenance": self.provenance,
            "metadata": dict(self.metadata),
        }


class AcademicTrustGraph:
    """
    Deterministic, in-memory property graph for academic trust and suspicious patterns.
    Guarantees sorted, deterministic order for all traversals and serialization.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, TrustNode] = {}
        self._edges: dict[tuple[str, str, str], TrustEdge] = {}
        self._adj: dict[str, set[str]] = {}
        self._out_edges: dict[str, list[TrustEdge]] = {}
        self._in_edges: dict[str, list[TrustEdge]] = {}

    def add_node(self, node: TrustNode) -> None:
        """Add a node or update existing node while preserving verified status."""
        if node.id not in self._nodes:
            self._nodes[node.id] = node
            self._adj[node.id] = set()
            self._out_edges[node.id] = []
            self._in_edges[node.id] = []
        else:
            existing = self._nodes[node.id]
            if node.is_verified:
                existing.is_verified = True
            existing.metadata.update(node.metadata)

    def add_edge(self, edge: TrustEdge) -> None:
        """Add a directed edge between nodes."""
        # Ensure endpoints exist
        if edge.source not in self._nodes or edge.target not in self._nodes:
            return

        key = (edge.source, edge.target, edge.edge_type.value)
        if key not in self._edges:
            self._edges[key] = edge
            self._adj.setdefault(edge.source, set()).add(edge.target)
            self._adj.setdefault(edge.target, set()).add(edge.source)
            self._out_edges.setdefault(edge.source, []).append(edge)
            self._in_edges.setdefault(edge.target, []).append(edge)

    def get_node(self, node_id: str) -> TrustNode | None:
        return self._nodes.get(node_id)

    def degree(self, node_id: str) -> int:
        return len(self._adj.get(node_id, set()))

    def neighbors(self, node_id: str) -> list[str]:
        return sorted(list(self._adj.get(node_id, set())))

    def nodes(self, node_type: TrustNodeType | None = None) -> list[TrustNode]:
        """Return deterministic list of nodes, sorted by canonical ID."""
        if node_type is None:
            return sorted(self._nodes.values(), key=lambda n: n.id)
        return sorted([n for n in self._nodes.values() if n.node_type == node_type], key=lambda n: n.id)

    def edges(self, edge_type: TrustEdgeType | None = None) -> list[TrustEdge]:
        """Return deterministic list of edges, sorted by (source, target, edge_type)."""
        if edge_type is None:
            return sorted(self._edges.values(), key=lambda e: (e.source, e.target, e.edge_type.value))
        return sorted(
            [e for e in self._edges.values() if e.edge_type == edge_type],
            key=lambda e: (e.source, e.target, e.edge_type.value),
        )

    def out_edges(self, node_id: str) -> list[TrustEdge]:
        return sorted(self._out_edges.get(node_id, []), key=lambda e: (e.target, e.edge_type.value))

    def in_edges(self, node_id: str) -> list[TrustEdge]:
        return sorted(self._in_edges.get(node_id, []), key=lambda e: (e.source, e.edge_type.value))

    def connected_components(self) -> list[list[str]]:
        """Compute connected components deterministically."""
        visited: set[str] = set()
        components: list[list[str]] = []

        for node_id in sorted(self._nodes.keys()):
            if node_id not in visited:
                comp: list[str] = []
                queue = [node_id]
                visited.add(node_id)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for nbr in sorted(self._adj.get(curr, set())):
                        if nbr not in visited:
                            visited.add(nbr)
                            queue.append(nbr)
                comp.sort()
                components.append(comp)

        return sorted(components, key=lambda c: c[0] if c else "")

    def to_dict(self) -> dict[str, Any]:
        """Convert graph to deterministic JSON-serializable snapshot."""
        return {
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
            "nodes": [n.to_dict() for n in self.nodes()],
            "edges": [e.to_dict() for e in self.edges()],
        }


# ── Canonical ID Helpers ──────────────────────────────────────────────────────


def make_opportunity_id(raw_id: Any) -> str:
    clean = str(raw_id).strip() if raw_id is not None else "unknown"
    return f"opp:{clean}"


def make_venue_id(raw_name: str | None = None, norm_issn: str | None = None) -> str:
    norm = normalize_venue_name(raw_name)
    if norm:
        clean = re.sub(r"[^\w\s-]", "", norm.lower()).strip()
        clean = re.sub(r"[\s-]+", "_", clean)
        return f"venue:name:{clean}"
    if norm_issn:
        return f"venue:issn:{norm_issn.strip().upper()}"
    return "venue:unknown"


def make_publisher_id(canonical_name: str | None) -> str:
    norm = (canonical_name or "unknown").strip().lower()
    norm = re.sub(r"\s+", "_", norm)
    return f"pub:{norm}"


def make_organizer_id(canonical_name: str | None) -> str:
    norm = (canonical_name or "unknown").strip().lower()
    norm = re.sub(r"\s+", "_", norm)
    return f"org:{norm}"


def make_domain_id(domain: str | None) -> str:
    clean = (domain or "unknown").strip().lower()
    return f"domain:{clean}"


def make_issn_id(issn: str | None) -> str:
    clean = (issn or "unknown").strip().upper()
    return f"issn:{clean}"


def make_source_id(openalex_id: str | None) -> str:
    clean = (openalex_id or "unknown").strip()
    return f"source:{clean}"


def is_domain_whitelisted(domain: str | None) -> bool:
    """Check if domain is a recognized academic publisher or verified platform."""
    if not domain:
        return False
    clean = domain.strip().lower()

    if clean in LEGITIMATE_SHARED_PLATFORMS:
        return True

    if clean in PUBLISHER_DOMAINS:
        return True

    # Check suffix matches (e.g. "subdomain.ieee.org" -> "ieee.org")
    for known in LEGITIMATE_SHARED_PLATFORMS:
        if clean == known or clean.endswith(f".{known}"):
            return True

    for known in PUBLISHER_DOMAINS:
        if clean == known or clean.endswith(f".{known}"):
            return True

    return False


# ── Graph Construction ────────────────────────────────────────────────────────


class GraphBuilder:
    """
    Constructs an AcademicTrustGraph deterministically from a batch of opportunities
    and their resolved academic entities.
    """

    def build_graph(
        self,
        opportunities: list[Any],
        resolved_entities: list[ResolvedAcademicEntity | None] | None = None,
    ) -> AcademicTrustGraph:
        """
        Build an AcademicTrustGraph in-memory from opportunities and resolved entities.
        """
        graph = AcademicTrustGraph()

        if not opportunities:
            return graph

        entities = resolved_entities or [None] * len(opportunities)

        for opp, entity in zip(opportunities, entities):
            raw_id = _get_field(opp, "id")
            opp_node_id = make_opportunity_id(raw_id)
            opp_title = _get_field(opp, "title") or "Untitled Opportunity"

            # 1. Opportunity Node
            graph.add_node(
                TrustNode(
                    id=opp_node_id,
                    node_type=TrustNodeType.OPPORTUNITY,
                    label=str(opp_title),
                    metadata={"opportunity_id": str(raw_id)},
                )
            )

            # Extract fields directly or from resolved entity
            venue_name = (
                (entity.canonical_name if entity else None)
                or _get_field(opp, "venue")
                or _get_field(opp, "publication_venue")
            )
            raw_issn = (entity.issn_l if entity else None) or (entity.issn if entity else None) or _get_field(opp, "issn")
            norm_issn = validate_issn(raw_issn) if raw_issn else None

            # 2. Venue Node
            venue_node_id: str | None = None
            if venue_name or norm_issn:
                canon_key = get_canonical_venue_key(name=venue_name, issn_l=norm_issn)
                venue_node_id = make_venue_id(raw_name=venue_name, norm_issn=norm_issn)
                is_venue_verified = False
                if entity and entity.resolution_status in (ResolutionStatus.RESOLVED, "RESOLVED"):
                    is_venue_verified = True

                graph.add_node(
                    TrustNode(
                        id=venue_node_id,
                        node_type=TrustNodeType.VENUE,
                        label=venue_name or (f"ISSN {norm_issn}" if norm_issn else "Unknown Venue"),
                        is_verified=is_venue_verified,
                        metadata={"canonical_key": canon_key, "raw_name": venue_name},
                    )
                )

                graph.add_edge(
                    TrustEdge(
                        source=opp_node_id,
                        target=venue_node_id,
                        edge_type=TrustEdgeType.OPPORTUNITY_IN_VENUE,
                        provenance=(
                            EvidenceProvenance.NORMALIZED_METADATA.value
                            if entity
                            else EvidenceProvenance.SCRAPED_METADATA.value
                        ),
                    )
                )

            # 3. Publisher Node
            publisher_name = (entity.publisher if entity else None) or _get_field(opp, "publisher")
            if publisher_name:
                is_pub_trusted, canon_pub = match_trusted_publisher(publisher_name)
                pub_label = canon_pub or publisher_name
                pub_node_id = make_publisher_id(pub_label)

                graph.add_node(
                    TrustNode(
                        id=pub_node_id,
                        node_type=TrustNodeType.PUBLISHER,
                        label=pub_label,
                        is_verified=is_pub_trusted,
                        metadata={"is_trusted": is_pub_trusted, "canonical_name": canon_pub},
                    )
                )

                if venue_node_id:
                    graph.add_edge(
                        TrustEdge(
                            source=venue_node_id,
                            target=pub_node_id,
                            edge_type=TrustEdgeType.VENUE_PUBLISHED_BY,
                            provenance=(
                                EvidenceProvenance.STATIC_TRUST_REGISTRY.value
                                if is_pub_trusted
                                else EvidenceProvenance.SCRAPED_METADATA.value
                            ),
                        )
                    )

            # 4. Organizer Node
            organizer_name = (entity.organizer if entity else None) or _get_field(opp, "organizer")
            if organizer_name:
                is_soc_trusted, canon_soc = match_trusted_society(organizer_name)
                # Also check if organizer matches trusted publisher (e.g. IEEE organizes conferences)
                is_org_pub_trusted, canon_org_pub = match_trusted_publisher(organizer_name)
                is_verified_org = is_soc_trusted or is_org_pub_trusted
                org_label = canon_soc or canon_org_pub or organizer_name
                org_node_id = make_organizer_id(org_label)

                graph.add_node(
                    TrustNode(
                        id=org_node_id,
                        node_type=TrustNodeType.ORGANIZER,
                        label=org_label,
                        is_verified=is_verified_org,
                        metadata={"is_trusted": is_verified_org},
                    )
                )

                graph.add_edge(
                    TrustEdge(
                        source=opp_node_id,
                        target=org_node_id,
                        edge_type=TrustEdgeType.OPPORTUNITY_ORGANIZED_BY,
                        provenance=(
                            EvidenceProvenance.STATIC_TRUST_REGISTRY.value
                            if is_verified_org
                            else EvidenceProvenance.SCRAPED_METADATA.value
                        ),
                    )
                )
                if venue_node_id:
                    graph.add_edge(
                        TrustEdge(
                            source=venue_node_id,
                            target=org_node_id,
                            edge_type=TrustEdgeType.VENUE_ORGANIZED_BY,
                            provenance=EvidenceProvenance.DERIVED.value,
                        )
                    )

            # 5. Domain Node (from website_url, submission_url, or entity)
            domain_str = (entity.domain if entity else None)
            if not domain_str:
                url_candidate = _get_field(opp, "website_url") or _get_field(opp, "submission_url")
                if url_candidate:
                    norm_u = normalize_url(url_candidate)
                    domain_str = norm_u.get("domain")

            if domain_str:
                dom_node_id = make_domain_id(domain_str)
                is_dom_trusted = is_domain_whitelisted(domain_str)

                graph.add_node(
                    TrustNode(
                        id=dom_node_id,
                        node_type=TrustNodeType.DOMAIN,
                        label=domain_str,
                        is_verified=is_dom_trusted,
                        metadata={"is_whitelisted": is_dom_trusted},
                    )
                )

                graph.add_edge(
                    TrustEdge(
                        source=opp_node_id,
                        target=dom_node_id,
                        edge_type=TrustEdgeType.HAS_DOMAIN,
                        provenance=EvidenceProvenance.NORMALIZED_METADATA.value,
                    )
                )
                if venue_node_id:
                    graph.add_edge(
                        TrustEdge(
                            source=venue_node_id,
                            target=dom_node_id,
                            edge_type=TrustEdgeType.HAS_DOMAIN,
                            provenance=EvidenceProvenance.DERIVED.value,
                        )
                    )

            # 6. ISSN Node
            if norm_issn and venue_node_id:
                issn_node_id = make_issn_id(norm_issn)
                graph.add_node(
                    TrustNode(
                        id=issn_node_id,
                        node_type=TrustNodeType.ISSN,
                        label=norm_issn,
                        is_verified=True,  # Normalized valid checksum format
                        metadata={"issn": norm_issn},
                    )
                )
                graph.add_edge(
                    TrustEdge(
                        source=venue_node_id,
                        target=issn_node_id,
                        edge_type=TrustEdgeType.HAS_IDENTIFIER,
                        provenance=EvidenceProvenance.NORMALIZED_METADATA.value,
                    )
                )

            # 7. Research Source Node (OpenAlex source linkage from 2.6D)
            openalex_id = entity.openalex_id if entity else None
            if openalex_id and venue_node_id:
                src_node_id = make_source_id(openalex_id)
                graph.add_node(
                    TrustNode(
                        id=src_node_id,
                        node_type=TrustNodeType.RESEARCH_SOURCE,
                        label=openalex_id,
                        is_verified=True,
                        metadata={"openalex_id": openalex_id},
                    )
                )
                graph.add_edge(
                    TrustEdge(
                        source=venue_node_id,
                        target=src_node_id,
                        edge_type=TrustEdgeType.LINKED_TO_SOURCE,
                        provenance=EvidenceProvenance.EXTERNAL_VERIFICATION.value,
                    )
                )

        return graph


# ── Suspicious Graph Analyzer ─────────────────────────────────────────────────


@dataclass
class DetectedGraphPattern:
    """A detected structural graph pattern with affected opportunities and provenance."""

    signal: EvidenceSignal
    node_id: str
    node_type: TrustNodeType
    affected_opp_ids: list[str]
    strength: EvidenceStrength
    confidence: EvidenceConfidence
    explanation: str
    pattern_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


class SuspiciousGraphAnalyzer:
    """
    Analyzes an AcademicTrustGraph for structural suspicious patterns and positive corroborations.
    Guarantees:
      - High degree alone NEVER produces risk.
      - Trusted entities are completely safeguarded.
      - Isolated nodes remain neutral.
      - Zero network calls and deterministic ordering.
    """

    def __init__(
        self,
        max_organizer_events: int = MAX_LEGITIMATE_UNVERIFIED_ORGANIZER_EVENTS,
        max_domain_entities: int = MAX_LEGITIMATE_UNVERIFIED_DOMAIN_ENTITIES,
        min_cluster_opps: int = MIN_CLUSTER_OPPORTUNITIES,
        min_cluster_suspicious: int = MIN_CLUSTER_SUSPICIOUS_OPPORTUNITIES,
    ) -> None:
        self.max_organizer_events = max_organizer_events
        self.max_domain_entities = max_domain_entities
        self.min_cluster_opps = min_cluster_opps
        self.min_cluster_suspicious = min_cluster_suspicious

    def analyze(
        self,
        graph: AcademicTrustGraph,
        existing_collections: dict[str, RiskEvidenceCollection] | None = None,
    ) -> list[DetectedGraphPattern]:
        """
        Detect all structural patterns across the graph.

        Parameters
        ----------
        graph:
            The AcademicTrustGraph built from the batch.
        existing_collections:
            Map of opp_id -> RiskEvidenceCollection containing observable evidence from 2.6B/2.6D.
            Required for cluster correlation.

        Returns
        -------
        list[DetectedGraphPattern]
            Sorted, deterministic list of detected patterns.
        """
        patterns: list[DetectedGraphPattern] = []
        collections = existing_collections or {}

        # 1. Pattern: HIGH_ORGANIZER_REUSE
        patterns.extend(self._detect_organizer_reuse(graph))

        # 2. Pattern: HIGH_DOMAIN_REUSE
        patterns.extend(self._detect_domain_reuse(graph))

        # 3. Pattern: GRAPH_IDENTITY_CONFLICT
        patterns.extend(self._detect_identity_conflicts(graph))

        # 4. Pattern: SUSPICIOUS_ORGANIZER_CLUSTER
        patterns.extend(self._detect_organizer_clusters(graph, collections))

        # 5. Pattern: SUSPICIOUS_PUBLISHER_CLUSTER
        patterns.extend(self._detect_publisher_clusters(graph, collections))

        # 6. Pattern: CONSISTENT_GRAPH_IDENTITY (Positive trust)
        patterns.extend(self._detect_consistent_graph_identities(graph))

        # Sort patterns deterministically by (signal, node_id)
        return sorted(patterns, key=lambda p: (p.signal.value, p.node_id))

    def _get_connected_opportunities(self, graph: AcademicTrustGraph, node_id: str) -> list[str]:
        """Find all opportunity IDs connected to a given entity node."""
        opp_ids: set[str] = set()

        # Direct inbound edges from opportunities
        for edge in graph.in_edges(node_id):
            if edge.source.startswith("opp:"):
                opp_ids.add(edge.source)

        # Via venue nodes (e.g. opp -> venue -> publisher/organizer/domain/issn)
        for edge in graph.in_edges(node_id):
            if edge.source.startswith("venue:"):
                venue_id = edge.source
                for v_edge in graph.in_edges(venue_id):
                    if v_edge.source.startswith("opp:"):
                        opp_ids.add(v_edge.source)

        return sorted(list(opp_ids))

    def _detect_organizer_reuse(self, graph: AcademicTrustGraph) -> list[DetectedGraphPattern]:
        """Detect unverified organizers linked to unusually high numbers of opportunities/venues."""
        results: list[DetectedGraphPattern] = []

        for node in graph.nodes(TrustNodeType.ORGANIZER):
            # SAFEGUARD: Trusted academic societies and publishers are NEVER flagged
            if node.is_verified:
                continue

            connected_opps = self._get_connected_opportunities(graph, node.id)
            # Distinct venues connected to this organizer
            connected_venues = {
                edge.source for edge in graph.in_edges(node.id) if edge.source.startswith("venue:")
            }

            total_events = len(connected_opps)
            if total_events >= self.max_organizer_events:
                venue_count = len(connected_venues)
                results.append(
                    DetectedGraphPattern(
                        signal=EvidenceSignal.HIGH_ORGANIZER_REUSE,
                        node_id=node.id,
                        node_type=TrustNodeType.ORGANIZER,
                        affected_opp_ids=connected_opps,
                        strength=EvidenceStrength.MODERATE,
                        confidence=EvidenceConfidence.HIGH if venue_count >= 3 else EvidenceConfidence.MEDIUM,
                        explanation=(
                            f"Unverified organizer '{node.label}' is linked to {total_events} opportunities "
                            f"across {venue_count} venues, exceeding legitimate reuse thresholds."
                        ),
                        pattern_count=total_events,
                        metadata={"distinct_venues": venue_count, "opportunity_count": total_events},
                    )
                )

        return results

    def _detect_domain_reuse(self, graph: AcademicTrustGraph) -> list[DetectedGraphPattern]:
        """Detect unverified domains hosting many seemingly unrelated venues/opportunities."""
        results: list[DetectedGraphPattern] = []

        for node in graph.nodes(TrustNodeType.DOMAIN):
            # SAFEGUARD: Whitelisted publisher domains and conference platforms are NEVER flagged
            if node.is_verified or is_domain_whitelisted(node.label):
                continue

            connected_opps = self._get_connected_opportunities(graph, node.id)
            connected_venues = {
                edge.source for edge in graph.in_edges(node.id) if edge.source.startswith("venue:")
            }

            distinct_entities = len(connected_opps) + len(connected_venues)
            if distinct_entities >= self.max_domain_entities:
                results.append(
                    DetectedGraphPattern(
                        signal=EvidenceSignal.HIGH_DOMAIN_REUSE,
                        node_id=node.id,
                        node_type=TrustNodeType.DOMAIN,
                        affected_opp_ids=connected_opps,
                        strength=EvidenceStrength.MODERATE,
                        confidence=EvidenceConfidence.MEDIUM,
                        explanation=(
                            f"Unverified domain '{node.label}' is reused across {distinct_entities} distinct "
                            f"venues and opportunities, indicating potential mass paper-mill or syndication."
                        ),
                        pattern_count=distinct_entities,
                        metadata={"connected_venues": len(connected_venues), "connected_opps": len(connected_opps)},
                    )
                )

        return results

    def _detect_identity_conflicts(self, graph: AcademicTrustGraph) -> list[DetectedGraphPattern]:
        """
        Detect identity collisions, e.g.:
          - Same ISSN claimed by multiple incompatible venues
          - Same unverified domain claimed by contradictory publishers
        """
        results: list[DetectedGraphPattern] = []

        # 1. ISSN collision across distinct venues
        for node in graph.nodes(TrustNodeType.ISSN):
            venue_edges = graph.in_edges(node.id)
            venues: list[TrustNode] = []
            for edge in venue_edges:
                if edge.source.startswith("venue:"):
                    v_node = graph.get_node(edge.source)
                    if v_node:
                        venues.append(v_node)

            if len(venues) >= 2:
                # Check if venues have contradictory labels (not just minor aliases)
                labels = {v.label.strip().lower() for v in venues}
                if len(labels) >= 2:
                    # Collect all affected opportunities
                    affected: set[str] = set()
                    for v in venues:
                        affected.update(self._get_connected_opportunities(graph, v.id))

                    if affected:
                        sorted_affected = sorted(list(affected))
                        venues_str = ", ".join(sorted([v.label for v in venues]))
                        results.append(
                            DetectedGraphPattern(
                                signal=EvidenceSignal.GRAPH_IDENTITY_CONFLICT,
                                node_id=node.id,
                                node_type=TrustNodeType.ISSN,
                                affected_opp_ids=sorted_affected,
                                strength=EvidenceStrength.WEAK,
                                confidence=EvidenceConfidence.MEDIUM,
                                explanation=(
                                    f"ISSN identifier '{node.label}' is claimed by multiple conflicting venues: {venues_str}."
                                ),
                                pattern_count=len(venues),
                                metadata={"conflicting_venues": sorted([v.label for v in venues])},
                            )
                        )

        # 2. Unverified domain claimed by multiple contradictory publishers
        for node in graph.nodes(TrustNodeType.DOMAIN):
            if node.is_verified or is_domain_whitelisted(node.label):
                continue

            # Check all opportunities connected to this domain
            connected_opps = self._get_connected_opportunities(graph, node.id)
            publishers_on_domain: set[str] = set()
            for opp_id in connected_opps:
                # Find publishers linked to this opp
                for nbr in graph.neighbors(opp_id):
                    if nbr.startswith("pub:"):
                        p_node = graph.get_node(nbr)
                        if p_node:
                            publishers_on_domain.add(p_node.label)
                    elif nbr.startswith("venue:"):
                        for v_nbr in graph.neighbors(nbr):
                            if v_nbr.startswith("pub:"):
                                p_node = graph.get_node(v_nbr)
                                if p_node:
                                    publishers_on_domain.add(p_node.label)

            if len(publishers_on_domain) >= 2:
                results.append(
                    DetectedGraphPattern(
                        signal=EvidenceSignal.GRAPH_IDENTITY_CONFLICT,
                        node_id=node.id,
                        node_type=TrustNodeType.DOMAIN,
                        affected_opp_ids=connected_opps,
                        strength=EvidenceStrength.WEAK,
                        confidence=EvidenceConfidence.MEDIUM,
                        explanation=(
                            f"Domain '{node.label}' is associated with conflicting publisher identities: "
                            f"{', '.join(sorted(publishers_on_domain))}."
                        ),
                        pattern_count=len(publishers_on_domain),
                        metadata={"conflicting_publishers": sorted(list(publishers_on_domain))},
                    )
                )

        return results

    def _has_affirmative_suspicious_evidence(self, collection: RiskEvidenceCollection | None) -> bool:
        """Check if an opportunity exhibits affirmative negative suspicious evidence."""
        if not collection:
            return False
        affirmative_signals = {
            EvidenceSignal.SUSPICIOUS_PAYMENT_LANGUAGE.value,
            EvidenceSignal.SUSPICIOUS_REVIEW_CLAIM.value,
            EvidenceSignal.SUSPICIOUS_EDITORIAL_CLAIM.value,
            EvidenceSignal.SUSPICIOUS_DOMAIN.value,
            EvidenceSignal.SUSPICIOUS_PUBLISHER_PATTERN.value,
            EvidenceSignal.SUSPICIOUS_CONTACT_PATTERN.value,
            EvidenceSignal.UNVERIFIABLE_CLAIM.value,
        }
        for item in collection.negative_evidence:
            if item.signal in affirmative_signals:
                return True
        return False

    def _detect_organizer_clusters(
        self,
        graph: AcademicTrustGraph,
        collections: dict[str, RiskEvidenceCollection],
    ) -> list[DetectedGraphPattern]:
        """Detect organizer clusters where multiple connected opportunities have affirmative negative signals."""
        results: list[DetectedGraphPattern] = []

        for node in graph.nodes(TrustNodeType.ORGANIZER):
            if node.is_verified:
                continue

            connected_opps = self._get_connected_opportunities(graph, node.id)
            if len(connected_opps) < self.min_cluster_opps:
                continue

            # Count how many connected opps have affirmative suspicious evidence
            suspicious_opps = [
                opp_id for opp_id in connected_opps
                if self._has_affirmative_suspicious_evidence(collections.get(opp_id.replace("opp:", "")))
            ]

            if len(suspicious_opps) >= self.min_cluster_suspicious:
                results.append(
                    DetectedGraphPattern(
                        signal=EvidenceSignal.SUSPICIOUS_ORGANIZER_CLUSTER,
                        node_id=node.id,
                        node_type=TrustNodeType.ORGANIZER,
                        affected_opp_ids=connected_opps,
                        strength=EvidenceStrength.STRONG,
                        confidence=EvidenceConfidence.HIGH,
                        explanation=(
                            f"Organizer '{node.label}' forms a suspicious cluster across {len(connected_opps)} "
                            f"opportunities, where {len(suspicious_opps)} exhibit verified negative risk signals."
                        ),
                        pattern_count=len(connected_opps),
                        metadata={
                            "cluster_size": len(connected_opps),
                            "suspicious_count": len(suspicious_opps),
                        },
                    )
                )

        return results

    def _detect_publisher_clusters(
        self,
        graph: AcademicTrustGraph,
        collections: dict[str, RiskEvidenceCollection],
    ) -> list[DetectedGraphPattern]:
        """Detect unverified publisher clusters with corroborated affirmative negative signals."""
        results: list[DetectedGraphPattern] = []

        for node in graph.nodes(TrustNodeType.PUBLISHER):
            if node.is_verified:
                continue

            connected_opps = self._get_connected_opportunities(graph, node.id)
            if len(connected_opps) < self.min_cluster_opps:
                continue

            suspicious_opps = [
                opp_id for opp_id in connected_opps
                if self._has_affirmative_suspicious_evidence(collections.get(opp_id.replace("opp:", "")))
            ]

            if len(suspicious_opps) >= self.min_cluster_suspicious:
                results.append(
                    DetectedGraphPattern(
                        signal=EvidenceSignal.SUSPICIOUS_PUBLISHER_CLUSTER,
                        node_id=node.id,
                        node_type=TrustNodeType.PUBLISHER,
                        affected_opp_ids=connected_opps,
                        strength=EvidenceStrength.STRONG,
                        confidence=EvidenceConfidence.HIGH,
                        explanation=(
                            f"Publisher '{node.label}' is linked to {len(connected_opps)} opportunities, "
                            f"where {len(suspicious_opps)} exhibit corroborated suspicious evidence."
                        ),
                        pattern_count=len(connected_opps),
                        metadata={
                            "cluster_size": len(connected_opps),
                            "suspicious_count": len(suspicious_opps),
                        },
                    )
                )

        return results

    def _detect_consistent_graph_identities(self, graph: AcademicTrustGraph) -> list[DetectedGraphPattern]:
        """
        Detect multi-source triangular trust agreement for opportunities:
        Venue -> Verified Publisher + Valid ISSN / Verified Society / OpenAlex Source.
        """
        results: list[DetectedGraphPattern] = []

        for opp_node in graph.nodes(TrustNodeType.OPPORTUNITY):
            # Find connected venues
            venues = [
                graph.get_node(edge.target)
                for edge in graph.out_edges(opp_node.id)
                if edge.edge_type == TrustEdgeType.OPPORTUNITY_IN_VENUE
            ]

            for v in venues:
                if not v:
                    continue

                # Check if venue connects to verified publisher
                has_verified_pub = False
                has_corroborating_source = False

                for v_edge in graph.out_edges(v.id):
                    target_node = graph.get_node(v_edge.target)
                    if not target_node:
                        continue
                    if target_node.node_type == TrustNodeType.PUBLISHER and target_node.is_verified:
                        has_verified_pub = True
                    if target_node.node_type in (TrustNodeType.ISSN, TrustNodeType.RESEARCH_SOURCE) and target_node.is_verified:
                        has_corroborating_source = True
                    if target_node.node_type == TrustNodeType.ORGANIZER and target_node.is_verified:
                        has_corroborating_source = True

                if has_verified_pub and has_corroborating_source:
                    results.append(
                        DetectedGraphPattern(
                            signal=EvidenceSignal.CONSISTENT_GRAPH_IDENTITY,
                            node_id=opp_node.id,
                            node_type=TrustNodeType.OPPORTUNITY,
                            affected_opp_ids=[opp_node.id],
                            strength=EvidenceStrength.MODERATE,
                            confidence=EvidenceConfidence.HIGH,
                            explanation=(
                                f"Multi-source structural trust corroboration: venue '{v.label}' is confirmed "
                                f"by verified publisher and independent academic source."
                            ),
                            pattern_count=1,
                            metadata={"venue_id": v.id, "venue_label": v.label},
                        )
                    )

        return results


# ── Opportunity-Level Projection & Deduplication ──────────────────────────────


def project_graph_evidence(
    patterns: list[DetectedGraphPattern],
    opportunities: list[Any],
) -> dict[str, list[RiskEvidence]]:
    """
    Project detected graph patterns onto opportunity-level RiskEvidence items.

    Guarantees:
      - Correlated Evidence Protection: Deduplicates multiple paths to the same conceptual pattern.
      - Bounded metadata: Only compact, relevant structural attributes stored.
      - Preserves exact opportunity mapping.

    Returns
    -------
    dict[str, list[RiskEvidence]]
        Map of opp_id (e.g. "123") -> list of projected RiskEvidence items.
    """
    projected: dict[str, list[RiskEvidence]] = {}

    # Initialize keys for all opportunities in batch
    for opp in opportunities:
        raw_id = _get_field(opp, "id")
        clean_id = str(raw_id).strip() if raw_id is not None else "unknown"
        projected[clean_id] = []

    # Map of (opp_id, signal, matched_value) -> RiskEvidence for strict deduplication
    seen: set[tuple[str, str, str | None]] = set()

    for pattern in patterns:
        is_positive = pattern.signal == EvidenceSignal.CONSISTENT_GRAPH_IDENTITY
        category = EvidenceCategory.POSITIVE_TRUST if is_positive else EvidenceCategory.NEGATIVE_SUSPICIOUS

        for opp_node_id in pattern.affected_opp_ids:
            clean_opp_id = opp_node_id.replace("opp:", "")
            if clean_opp_id not in projected:
                continue

            dedup_key = (clean_opp_id, pattern.signal.value, pattern.node_id)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            evidence_item = RiskEvidence(
                signal=pattern.signal.value,
                category=category,
                strength=pattern.strength,
                confidence=pattern.confidence,
                provenance=EvidenceProvenance.GRAPH_ANALYSIS,
                source_field=f"graph:{pattern.node_type.value.lower()}",
                matched_value=pattern.node_id,
                explanation=pattern.explanation,
                is_present=True,
                metadata={
                    "pattern_node_id": pattern.node_id,
                    "pattern_node_type": pattern.node_type.value,
                    "pattern_count": pattern.pattern_count,
                    **pattern.metadata,
                },
            )
            projected[clean_opp_id].append(evidence_item)

    return projected


# ── Suspicious Graph Service Facade ───────────────────────────────────────────


class SuspiciousGraphService:
    """
    High-level facade orchestrating graph construction, pattern analysis,
    and opportunity projection for Phase 2.6E.
    """

    def __init__(self) -> None:
        self.builder = GraphBuilder()
        self.analyzer = SuspiciousGraphAnalyzer()

    def analyze_batch(
        self,
        opportunities: list[Any],
        resolved_entities: list[ResolvedAcademicEntity | None] | None = None,
        existing_collections: list[RiskEvidenceCollection] | None = None,
    ) -> tuple[AcademicTrustGraph, dict[str, list[RiskEvidence]]]:
        """
        Build batch graph, detect patterns, and project evidence onto opportunities.

        Parameters
        ----------
        opportunities:
            List of opportunities in the current evaluation batch.
        resolved_entities:
            Pre-resolved 2.6D academic entities.
        existing_collections:
            Extracted 2.6B/2.6D collections for cluster negative signal correlation.

        Returns
        -------
        tuple[AcademicTrustGraph, dict[str, list[RiskEvidence]]]
            Constructed graph and map of opp_id -> projected RiskEvidence items.
        """
        if not opportunities:
            return AcademicTrustGraph(), {}

        # 1. Build Graph
        graph = self.builder.build_graph(opportunities, resolved_entities=resolved_entities)

        # 2. Index collections by clean opp_id
        col_map: dict[str, RiskEvidenceCollection] = {}
        if existing_collections:
            for c in existing_collections:
                if c.opportunity_id:
                    col_map[str(c.opportunity_id)] = c

        # 3. Analyze patterns
        patterns = self.analyzer.analyze(graph, existing_collections=col_map)

        # 4. Project onto opportunities
        projected_evidence = project_graph_evidence(patterns, opportunities)

        return graph, projected_evidence


# Global singleton
suspicious_graph_service = SuspiciousGraphService()
