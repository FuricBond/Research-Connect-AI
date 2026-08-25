"""
In-memory persistence tests for topic taxonomy, aliases, research_work_topics, and opportunity_topics.
"""
import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from ml.topic_analysis.assignment import TopicAssigner
from ml.topic_analysis.taxonomy import TaxonomyNode, TaxonomyService


# ── SQLite Models ─────────────────────────────────────────────────────────────


class SqBase(DeclarativeBase):
    pass


class SqTopic(SqBase):
    __tablename__ = "topics"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))


class SqTopicAlias(SqBase):
    __tablename__ = "topic_aliases"
    __table_args__ = (
        UniqueConstraint("topic_id", "normalized_alias", name="uq_topic_aliases_topic_normalized"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    alias: Mapped[str] = mapped_column(String(150), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(150), nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="MANUAL", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))


class SqResearchWork(SqBase):
    __tablename__ = "research_works"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))


class SqResearchWorkTopic(SqBase):
    __tablename__ = "research_work_topics"
    __table_args__ = (
        UniqueConstraint("work_id", "topic_id", name="uq_research_work_topics_work_topic"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    work_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_works.id", ondelete="CASCADE"), nullable=False)
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.00, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    assignment_method: Mapped[str] = mapped_column(String(50), default="RULE_INFERRED", nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="System", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))


class SqOpportunity(SqBase):
    __tablename__ = "opportunities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))


class SqOpportunityTopic(SqBase):
    __tablename__ = "opportunity_topics"
    opportunity_id: Mapped[str] = mapped_column(String(36), ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True)
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.00, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))


# ── Pytest Fixture ────────────────────────────────────────────────────────────


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SqBase.metadata.create_all(engine)
    SessionMaker = sessionmaker(bind=engine)
    sess = SessionMaker()
    yield sess
    sess.close()
    engine.dispose()


class TestTopicPersistence:
    def test_sync_taxonomy_seed_to_sqlite(self, session):
        taxonomy_service = TaxonomyService()
        # Insert topics into SQLite
        db_topics: dict[str, SqTopic] = {}
        for node in taxonomy_service.get_all_nodes():
            topic = SqTopic(
                id=str(uuid.uuid4()),
                name=node.name,
                slug=node.slug,
                description=node.description,
            )
            session.add(topic)
            session.flush()
            db_topics[node.slug] = topic

        # Set parent_ids
        for node in taxonomy_service.get_all_nodes():
            if node.parent_slug and node.parent_slug in db_topics:
                db_topics[node.slug].parent_id = db_topics[node.parent_slug].id
                session.flush()

        # Insert aliases
        for node in taxonomy_service.get_all_nodes():
            topic = db_topics[node.slug]
            for alias in node.aliases:
                alias_obj = SqTopicAlias(
                    id=str(uuid.uuid4()),
                    topic_id=topic.id,
                    alias=alias,
                    normalized_alias=alias.strip().lower(),
                    source="SEED",
                )
                session.add(alias_obj)

        session.commit()

        # Verify insertion
        topics_count = len(session.execute(select(SqTopic)).scalars().all())
        aliases_count = len(session.execute(select(SqTopicAlias)).scalars().all())
        assert topics_count >= 20
        assert aliases_count >= 30

    def test_persist_research_work_topics(self, session):
        # 1. Setup taxonomy
        topic_ai = SqTopic(id=str(uuid.uuid4()), name="Artificial Intelligence", slug="artificial-intelligence")
        topic_nlp = SqTopic(id=str(uuid.uuid4()), name="Natural Language Processing", slug="natural-language-processing")
        session.add_all([topic_ai, topic_nlp])
        session.commit()

        # 2. Add research work
        work = SqResearchWork(
            id=str(uuid.uuid4()),
            doi="10.1234/test-paper",
            title="Advances in Natural Language Processing and AI",
            abstract="We present new architectures for NLP.",
        )
        session.add(work)
        session.commit()

        # 3. Assign topics
        assigner = TopicAssigner()
        result = assigner.assign_topics(title=work.title, abstract=work.abstract)

        slug_to_id = {
            "artificial-intelligence": topic_ai.id,
            "natural-language-processing": topic_nlp.id,
        }

        for at in result.assigned_topics:
            t_id = slug_to_id.get(at.topic_slug)
            if t_id:
                assoc = SqResearchWorkTopic(
                    id=str(uuid.uuid4()),
                    work_id=work.id,
                    topic_id=t_id,
                    confidence_score=at.confidence_score,
                    is_primary=at.is_primary,
                    assignment_method=at.assignment_method,
                    source=at.source,
                )
                session.add(assoc)
        session.commit()

        # 4. Verify junction rows
        work_topics = session.execute(select(SqResearchWorkTopic).where(SqResearchWorkTopic.work_id == work.id)).scalars().all()
        assert len(work_topics) >= 1
        assert any(wt.is_primary for wt in work_topics)

    def test_idempotent_reprocessing(self, session):
        topic_nlp = SqTopic(id=str(uuid.uuid4()), name="Natural Language Processing", slug="natural-language-processing")
        session.add(topic_nlp)
        session.commit()

        work = SqResearchWork(
            id=str(uuid.uuid4()),
            title="NLP Methods",
        )
        session.add(work)
        session.commit()

        # Run 1: initial assignment
        assoc1 = SqResearchWorkTopic(
            id=str(uuid.uuid4()),
            work_id=work.id,
            topic_id=topic_nlp.id,
            confidence_score=0.85,
            is_primary=True,
        )
        session.add(assoc1)
        session.commit()

        # Run 2: reprocessing with clean delete + re-insert
        session.execute(delete(SqResearchWorkTopic).where(SqResearchWorkTopic.work_id == work.id))
        assoc2 = SqResearchWorkTopic(
            id=str(uuid.uuid4()),
            work_id=work.id,
            topic_id=topic_nlp.id,
            confidence_score=0.90,
            is_primary=True,
        )
        session.add(assoc2)
        session.commit()

        work_topics = session.execute(select(SqResearchWorkTopic).where(SqResearchWorkTopic.work_id == work.id)).scalars().all()
        assert len(work_topics) == 1
        assert work_topics[0].confidence_score == 0.90
