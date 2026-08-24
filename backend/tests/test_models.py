from datetime import datetime, timezone
import uuid

from app.models import (
    Base,
    IngestionRunModel,
    OpportunityModel,
    OpportunityTopicModel,
    ResearchProfileModel,
    SavedOpportunityModel,
    SourceModel,
    TopicModel,
    UserModel,
)


def test_models_registered_in_metadata() -> None:
    """Verify all Phase 1 and Phase 2.1 tables are registered in SQLAlchemy Base.metadata."""
    table_names = Base.metadata.tables.keys()

    expected_tables = {
        "users",
        "research_profiles",
        "sources",
        "topics",
        "opportunities",
        "opportunity_topics",
        "saved_opportunities",
        "ingestion_runs",
    }

    assert expected_tables.issubset(table_names), f"Missing tables in metadata: {expected_tables - set(table_names)}"


def test_user_and_profile_instantiation() -> None:
    """Verify UserModel and ResearchProfileModel instantiation and fields."""
    user = UserModel(
        id=uuid.uuid4(),
        email="researcher@university.edu",
        hashed_password="secure_hash_placeholder",
        full_name="Dr. Alex Rivera",
        role="FACULTY",
        is_active=True,
    )
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        institution="Tech University",
        department="Computer Science",
        academic_level="FACULTY",
        keywords=["natural language processing", "information retrieval"],
        target_opportunity_types=["CONFERENCE", "JOURNAL"],
    )

    assert user.email == "researcher@university.edu"
    assert user.role == "FACULTY"
    assert user.is_active is True
    assert profile.institution == "Tech University"
    assert "natural language processing" in profile.keywords


def test_opportunity_and_vector_instantiation() -> None:
    """Verify OpportunityModel with 384-dimensional embedding column and last_seen_at."""
    opp_id = uuid.uuid4()
    dummy_vector = [0.05] * 384
    now = datetime.now(tz=timezone.utc)

    opportunity = OpportunityModel(
        id=opp_id,
        title="International Conference on Machine Learning",
        opportunity_type="CONFERENCE",
        delivery_mode="HYBRID",
        status="ACTIVE",
        location="Vienna, Austria",
        indexing=["Scopus", "IEEE Xplore"],
        embedding=dummy_vector,
        last_seen_at=now,
    )

    assert opportunity.title == "International Conference on Machine Learning"
    assert opportunity.opportunity_type == "CONFERENCE"
    assert opportunity.delivery_mode == "HYBRID"
    assert opportunity.status == "ACTIVE"
    assert opportunity.last_seen_at == now
    assert len(opportunity.embedding) == 384


def test_topic_hierarchy_instantiation() -> None:
    """Verify TopicModel hierarchical structure."""
    parent_topic = TopicModel(
        id=uuid.uuid4(),
        name="Computer Science",
        slug="computer-science",
    )
    child_topic = TopicModel(
        id=uuid.uuid4(),
        name="Natural Language Processing",
        slug="natural-language-processing",
        parent_id=parent_topic.id,
    )

    assert parent_topic.name == "Computer Science"
    assert child_topic.parent_id == parent_topic.id


def test_saved_opportunity_instantiation() -> None:
    """Verify SavedOpportunityModel structure."""
    user_id = uuid.uuid4()
    opp_id = uuid.uuid4()

    saved = SavedOpportunityModel(
        id=uuid.uuid4(),
        user_id=user_id,
        opportunity_id=opp_id,
        notes="Target for abstract submission deadline",
    )

    assert saved.user_id == user_id
    assert saved.opportunity_id == opp_id
    assert saved.notes == "Target for abstract submission deadline"


def test_ingestion_run_instantiation() -> None:
    """Verify IngestionRunModel instantiation and metric tracking."""
    source_id = uuid.uuid4()
    run_id = uuid.uuid4()

    run = IngestionRunModel(
        id=run_id,
        source_id=source_id,
        status="COMPLETED",
        topic="artificial intelligence",
        pages_fetched=2,
        records_parsed=40,
        records_valid=38,
        records_invalid=2,
        records_inserted=30,
        records_updated=5,
        records_unchanged=3,
        duplicates_detected=2,
        potential_duplicates_detected=1,
        records_expired=4,
    )

    assert run.id == run_id
    assert run.source_id == source_id
    assert run.status == "COMPLETED"
    assert run.records_inserted == 30
    assert run.records_updated == 5
    assert run.records_unchanged == 3
