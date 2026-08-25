"""
Taxonomy service and canonical research topic hierarchy.

Defines the core ResearchConnect AI academic taxonomy tree, supports DAG traversal,
cycle prevention, ancestor/descendant resolution, and database synchronization.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class TaxonomyNode:
    """Represents a canonical topic in the taxonomy tree."""
    name: str
    slug: str
    description: str | None = None
    parent_slug: str | None = None
    aliases: list[str] = field(default_factory=list)


# ── Canonical Seed Taxonomy ───────────────────────────────────────────────────

SEED_TAXONOMY: list[TaxonomyNode] = [
    # Top-level Academic Domains
    TaxonomyNode(name="Computer Science", slug="computer-science", description="The study of computation, information, and automation.", aliases=["CS", "Computing", "Computer Sciences"]),
    TaxonomyNode(name="Medicine", slug="medicine", description="The science and practice of caring for patients and treating disease.", aliases=["Medical Sciences", "Healthcare", "Biomedicine"]),
    TaxonomyNode(name="Biology", slug="biology", description="The scientific study of life and living organisms.", aliases=["Biological Sciences", "Life Sciences"]),
    TaxonomyNode(name="Mathematics", slug="mathematics", description="The science of numbers, quantities, space, and structures.", aliases=["Math", "Mathematical Sciences"]),
    TaxonomyNode(name="Physics", slug="physics", description="The study of matter, motion, energy, and force.", aliases=["Physical Sciences"]),
    TaxonomyNode(name="Engineering", slug="engineering", description="The application of science and math to design and build structures, machines, and systems.", aliases=["Engineering Sciences"]),
    TaxonomyNode(name="Social Sciences", slug="social-sciences", description="The scientific study of human society and social relationships.", aliases=["Social Science"]),
    TaxonomyNode(name="Economics", slug="economics", description="The study of production, distribution, and consumption of goods and services.", aliases=["Economic Sciences"]),
    TaxonomyNode(name="Environmental Science", slug="environmental-science", description="The interdisciplinary study of the environment and solutions to environmental problems.", aliases=["Ecology", "Environmental Sciences"]),

    # Computer Science -> Major Sub-fields
    TaxonomyNode(name="Artificial Intelligence", slug="artificial-intelligence", parent_slug="computer-science", description="Simulating human intelligence in machines.", aliases=["AI", "Computational Intelligence"]),
    TaxonomyNode(name="Data Science", slug="data-science", parent_slug="computer-science", description="Extracting insights and knowledge from structured and unstructured data.", aliases=["Data Analytics", "Big Data Analytics"]),
    TaxonomyNode(name="Software Engineering", slug="software-engineering", parent_slug="computer-science", description="The systematic engineering approach to software development.", aliases=["SE", "Software Development"]),
    TaxonomyNode(name="Cybersecurity", slug="cybersecurity", parent_slug="computer-science", description="Protecting computer systems and networks from information disclosure and attack.", aliases=["Information Security", "InfoSec", "Cyber Security"]),
    TaxonomyNode(name="Databases", slug="databases", parent_slug="computer-science", description="Organization, storage, and retrieval of electronic data.", aliases=["Database Systems", "DBMS", "Data Management"]),
    TaxonomyNode(name="Distributed Systems", slug="distributed-systems", parent_slug="computer-science", description="Computing systems whose components are located on different networked computers.", aliases=["Distributed Computing", "Cloud Infrastructure"]),
    TaxonomyNode(name="Human-Computer Interaction", slug="human-computer-interaction", parent_slug="computer-science", description="The design and use of computer technology focused on the interfaces between people and computers.", aliases=["HCI", "User Experience", "UX"]),
    TaxonomyNode(name="Computer Networks", slug="computer-networks", parent_slug="computer-science", description="Telecommunications networks allowing computers to exchange data.", aliases=["Networking", "Network Systems"]),

    # Artificial Intelligence -> Core Areas
    TaxonomyNode(name="Machine Learning", slug="machine-learning", parent_slug="artificial-intelligence", description="Algorithms that improve automatically through experience and data.", aliases=["ML", "Statistical Learning", "Machine Learning Algorithms"]),
    TaxonomyNode(name="Natural Language Processing", slug="natural-language-processing", parent_slug="artificial-intelligence", description="Interaction between computers and human language.", aliases=["NLP", "Computational Linguistics", "Language Technologies"]),
    TaxonomyNode(name="Computer Vision", slug="computer-vision", parent_slug="artificial-intelligence", description="Enabling computers to derive high-level understanding from digital images or videos.", aliases=["CV", "Visual Recognition", "Image Processing"]),
    TaxonomyNode(name="Robotics", slug="robotics", parent_slug="artificial-intelligence", description="Design, construction, operation, and use of robots.", aliases=["Autonomous Systems", "Robot Control"]),
    TaxonomyNode(name="Knowledge Representation", slug="knowledge-representation", parent_slug="artificial-intelligence", description="Representing information about the world in a form that a computer can use.", aliases=["Knowledge Graphs", "Ontology", "Semantic Web"]),

    # Machine Learning -> Specialized Topics
    TaxonomyNode(name="Deep Learning", slug="deep-learning", parent_slug="machine-learning", description="Neural networks with multiple layers capable of learning hierarchical features.", aliases=["DL", "Neural Networks", "Deep Neural Networks", "DNN"]),
    TaxonomyNode(name="Reinforcement Learning", slug="reinforcement-learning", parent_slug="machine-learning", description="Training machine learning models to make a sequence of decisions.", aliases=["RL", "Deep Reinforcement Learning", "DRL"]),
    TaxonomyNode(name="Generative AI", slug="generative-ai", parent_slug="deep-learning", description="Artificial intelligence capable of generating text, images, or other media.", aliases=["GenAI", "Generative Models", "Diffusion Models", "GANs"]),
    TaxonomyNode(name="Large Language Models", slug="large-language-models", parent_slug="natural-language-processing", description="Language models with massive parameter counts trained on vast text corpora.", aliases=["LLM", "LLMs", "Large Language Model", "Foundation Models", "GPT", "BERT"]),
    TaxonomyNode(name="Transformers", slug="transformers", parent_slug="deep-learning", description="Self-attention based neural network architectures.", aliases=["Transformer Architecture", "Self-Attention"]),

    # Natural Language Processing -> Specialized Topics
    TaxonomyNode(name="Information Retrieval", slug="information-retrieval", parent_slug="natural-language-processing", description="Obtaining information system resources relevant to an information need.", aliases=["IR", "Search Engines", "Text Retrieval"]),
    TaxonomyNode(name="Text Classification", slug="text-classification", parent_slug="natural-language-processing", description="Assigning predefined categories to text documents.", aliases=["Document Classification", "Sentiment Analysis", "Topic Modeling"]),
    TaxonomyNode(name="Question Answering", slug="question-answering", parent_slug="natural-language-processing", description="Building systems that automatically answer questions posed by humans in natural language.", aliases=["QA", "RAG", "Retrieval-Augmented Generation"]),
    TaxonomyNode(name="Machine Translation", slug="machine-translation", parent_slug="natural-language-processing", description="Translating text from one natural language to another using software.", aliases=["MT", "Neural Machine Translation", "NMT"]),

    # Computer Vision -> Specialized Topics
    TaxonomyNode(name="Object Detection", slug="object-detection", parent_slug="computer-vision", description="Computer vision technique for locating instances of objects in images or videos.", aliases=["Object Recognition", "YOLO"]),
    TaxonomyNode(name="Image Segmentation", slug="image-segmentation", parent_slug="computer-vision", description="Partitioning a digital image into multiple image segments.", aliases=["Semantic Segmentation", "Instance Segmentation"]),

    # Data Science & Databases
    TaxonomyNode(name="Data Mining", slug="data-mining", parent_slug="data-science", description="Discovering patterns in large data sets.", aliases=["Pattern Mining", "Knowledge Discovery"]),
    TaxonomyNode(name="Vector Databases", slug="vector-databases", parent_slug="databases", description="Databases designed to store and query high-dimensional vector embeddings.", aliases=["Vector DB", "Vector Search", "ANN Search"]),

    # Interdisciplinary Domains
    TaxonomyNode(name="Bioinformatics", slug="bioinformatics", parent_slug="biology", description="Computational methods for analyzing biological data such as genetic sequences.", aliases=["Computational Biology", "Genomics"]),
    TaxonomyNode(name="Medical Informatics", slug="medical-informatics", parent_slug="medicine", description="Informatics in healthcare, medical research, and health technology.", aliases=["Healthcare AI", "Health Informatics", "Clinical Informatics"]),
    TaxonomyNode(name="Quantum Computing", slug="quantum-computing", parent_slug="physics", description="Computing utilizing quantum mechanical phenomena such as superposition and entanglement.", aliases=["Quantum Information", "Quantum Algorithms"]),
]


# ── Taxonomy Service ──────────────────────────────────────────────────────────


class TaxonomyService:
    """
    Manages the canonical topic taxonomy tree, aliases, DAG hierarchy, and database synchronization.
    """

    def __init__(self, nodes: list[TaxonomyNode] | None = None) -> None:
        self._nodes_list = list(nodes if nodes is not None else SEED_TAXONOMY)
        self._by_slug: dict[str, TaxonomyNode] = {}
        self._by_name_lower: dict[str, TaxonomyNode] = {}
        self._by_alias_lower: dict[str, TaxonomyNode] = {}
        self._children_map: dict[str, list[str]] = {}

        self._build_indexes()
        self.validate_no_cycles()

    def _build_indexes(self) -> None:
        """Construct fast lookup maps from the registered nodes."""
        self._by_slug.clear()
        self._by_name_lower.clear()
        self._by_alias_lower.clear()
        self._children_map.clear()

        for node in self._nodes_list:
            self._by_slug[node.slug] = node
            self._by_name_lower[node.name.strip().lower()] = node

            # Map all aliases
            for alias in node.aliases:
                cleaned_alias = alias.strip().lower()
                if cleaned_alias:
                    self._by_alias_lower[cleaned_alias] = node

            # Build children hierarchy
            if node.parent_slug:
                self._children_map.setdefault(node.parent_slug, []).append(node.slug)

    def add_node(self, node: TaxonomyNode) -> None:
        """Add a new node to the taxonomy and validate cycle freedom."""
        if node.slug in self._by_slug:
            # Replace existing node
            self._nodes_list = [n for n in self._nodes_list if n.slug != node.slug]
        self._nodes_list.append(node)
        self._build_indexes()
        self.validate_no_cycles()

    def validate_no_cycles(self) -> bool:
        """
        Validate that parent relationships form a valid DAG (Directed Acyclic Graph)
        with no circular dependencies.

        Raises:
            ValueError: If a cycle is detected.
        """
        for slug in self._by_slug:
            visited: set[str] = set()
            curr: str | None = slug
            while curr:
                if curr in visited:
                    raise ValueError(f"Taxonomy cycle detected involving topic slug {curr!r}")
                visited.add(curr)
                node = self._by_slug.get(curr)
                curr = node.parent_slug if node else None
        return True

    def get_node(self, slug: str) -> TaxonomyNode | None:
        """Lookup node by canonical slug."""
        return self._by_slug.get(slug)

    def get_all_nodes(self) -> list[TaxonomyNode]:
        """Return all registered taxonomy nodes."""
        return list(self._nodes_list)

    def get_ancestors(self, slug: str) -> list[str]:
        """
        Return ordered list of ancestor slugs from immediate parent to root.

        Example:
            get_ancestors('transformers') -> ['deep-learning', 'machine-learning', 'artificial-intelligence', 'computer-science']
        """
        ancestors: list[str] = []
        visited: set[str] = {slug}
        node = self._by_slug.get(slug)
        curr = node.parent_slug if node else None

        while curr and curr in self._by_slug and curr not in visited:
            ancestors.append(curr)
            visited.add(curr)
            node = self._by_slug.get(curr)
            curr = node.parent_slug if node else None

        return ancestors

    def get_descendants(self, slug: str) -> list[str]:
        """
        Return all descendant slugs in depth-first order.

        Example:
            get_descendants('machine-learning') -> ['deep-learning', 'generative-ai', 'transformers', 'reinforcement-learning']
        """
        descendants: list[str] = []
        stack = list(self._children_map.get(slug, []))
        visited: set[str] = set(stack)

        while stack:
            curr = stack.pop()
            descendants.append(curr)
            for child in self._children_map.get(curr, []):
                if child not in visited:
                    visited.add(child)
                    stack.append(child)

        return descendants

    def get_depth(self, slug: str) -> int:
        """Return depth of node in the hierarchy (Root = 0)."""
        return len(self.get_ancestors(slug))

    def sync_to_db(self, session: Session) -> dict[str, int]:
        """
        Synchronize seed taxonomy into database `topics` and `topic_aliases` tables.
        Idempotent: updates existing topics and aliases, adds missing ones.
        """
        from app.models.topic import TopicAliasModel, TopicModel

        created_topics = 0
        updated_topics = 0
        created_aliases = 0

        # Pass 1: Insert or update topic records without parent_id (to avoid FK errors)
        db_topics_by_slug: dict[str, TopicModel] = {}
        for node in self._nodes_list:
            stmt = select(TopicModel).where(TopicModel.slug == node.slug)
            topic = session.execute(stmt).scalar_one_or_none()

            if topic is None:
                topic = TopicModel(
                    id=uuid.uuid4(),
                    name=node.name,
                    slug=node.slug,
                    description=node.description,
                    parent_id=None,
                )
                session.add(topic)
                session.flush()
                created_topics += 1
            else:
                if topic.name != node.name or topic.description != node.description:
                    topic.name = node.name
                    topic.description = node.description
                    session.flush()
                    updated_topics += 1

            db_topics_by_slug[node.slug] = topic

        # Pass 2: Set parent_id relationships
        for node in self._nodes_list:
            if node.parent_slug and node.parent_slug in db_topics_by_slug:
                topic = db_topics_by_slug[node.slug]
                parent_topic = db_topics_by_slug[node.parent_slug]
                if topic.parent_id != parent_topic.id:
                    topic.parent_id = parent_topic.id
                    session.flush()

        # Pass 3: Sync aliases
        for node in self._nodes_list:
            topic = db_topics_by_slug[node.slug]
            for alias in node.aliases:
                clean_alias = alias.strip()
                normalized_alias = clean_alias.lower()
                if not clean_alias:
                    continue

                stmt = select(TopicAliasModel).where(
                    TopicAliasModel.topic_id == topic.id,
                    TopicAliasModel.normalized_alias == normalized_alias,
                )
                existing_alias = session.execute(stmt).scalar_one_or_none()

                if existing_alias is None:
                    new_alias = TopicAliasModel(
                        id=uuid.uuid4(),
                        topic_id=topic.id,
                        alias=clean_alias,
                        normalized_alias=normalized_alias,
                        source="SEED_TAXONOMY",
                    )
                    session.add(new_alias)
                    session.flush()
                    created_aliases += 1

        session.commit()
        logger.info(
            "Taxonomy sync complete: created_topics=%d updated_topics=%d created_aliases=%d",
            created_topics,
            updated_topics,
            created_aliases,
        )
        return {
            "created_topics": created_topics,
            "updated_topics": updated_topics,
            "created_aliases": created_aliases,
        }
