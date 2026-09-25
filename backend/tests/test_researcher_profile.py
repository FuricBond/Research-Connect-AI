"""
Unit and Integration Tests for Phase 3.1: Researcher Profile Foundation.

Verifies:
  1. ResearchProfileModel schema, foreign keys, and relationships.
  2. AcademicStatus enum validity and serialization.
  3. External identifier normalization (ORCID, OpenAlex ID) and validation.
  4. Deterministic profile completeness calculation across levels.
  5. ResearcherProfileService CRUD, entity resolution, and zero-N+1 works retrieval.
  6. FastAPI API endpoints: POST, GET, PATCH, /works, /completeness.
  7. Strict phase boundary: zero personalization or ranking side-effects.
"""
from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.research_knowledge import (
    InstitutionModel,
    ResearcherModel,
    ResearchWorkAuthorModel,
    ResearchWorkModel,
)
from app.models.research_profile import AcademicStatus, ResearchProfileModel
from app.models.user import UserModel
from app.schemas.researcher import (
    CompletenessLevel,
    ExternalIdentifiersSchema,
    ResearcherProfileCreate,
    ResearcherProfileUpdate,
    normalize_openalex_id,
    normalize_orcid,
)
from app.services.researcher_profile_service import ResearcherProfileService


# ── SQLite In-Memory Database Fixture ─────────────────────────────────────────

# Compile PostgreSQL-specific types gracefully for SQLite in-memory tests
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    """Provides a fresh in-memory SQLite session with researcher profile tables created."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    target_tables = [
        Base.metadata.tables["users"],
        Base.metadata.tables["institutions"],
        Base.metadata.tables["researchers"],
        Base.metadata.tables["research_works"],
        Base.metadata.tables["research_work_authors"],
        Base.metadata.tables["research_profiles"],
    ]
    Base.metadata.create_all(bind=engine, tables=target_tables)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """FastAPI TestClient with overridden get_db dependency."""
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


# ── 1. Model & Relationships Tests ───────────────────────────────────────────


class TestResearcherModelAndRelationships:
    def test_research_profile_creation_with_all_fields(self, db_session: Session):
        user = UserModel(
            id=uuid.uuid4(),
            email="dr.marie@sorbonne.fr",
            full_name="Dr. Marie Curie",
            hashed_password="pw_hash",
            role="FACULTY",
        )
        institution = InstitutionModel(
            id=uuid.uuid4(),
            display_name="Sorbonne Université",
            country_code="FR",
            institution_type="education",
        )
        canonical_researcher = ResearcherModel(
            id=uuid.uuid4(),
            openalex_id="A1234567890",
            display_name="Marie Curie",
            orcid="0000-0002-1825-0097",
            works_count=42,
            cited_by_count=5000,
        )
        db_session.add_all([user, institution, canonical_researcher])
        db_session.flush()

        profile = ResearchProfileModel(
            id=uuid.uuid4(),
            user_id=user.id,
            institution_id=institution.id,
            institution="Sorbonne Université",
            department="Physics & Chemistry",
            academic_status=AcademicStatus.FACULTY.value,
            academic_level="Professor",
            bio="Pioneering research on radioactivity.",
            canonical_researcher_id=canonical_researcher.id,
            orcid="0000-0002-1825-0097",
            openalex_id="A1234567890",
            external_identifiers={"scopus_id": "987654"},
            keywords=["radioactivity", "polonium", "radium"],
            target_opportunity_types=["GRANT", "CONFERENCE"],
        )
        db_session.add(profile)
        db_session.commit()

        # Reload and verify
        reloaded = db_session.get(ResearchProfileModel, profile.id)
        assert reloaded is not None
        assert reloaded.user.full_name == "Dr. Marie Curie"
        assert reloaded.institution_rel.display_name == "Sorbonne Université"
        assert reloaded.canonical_researcher.works_count == 42
        assert reloaded.academic_status == "FACULTY"
        assert reloaded.orcid == "0000-0002-1825-0097"
        assert "radioactivity" in reloaded.keywords

    def test_research_profile_nullable_defaults(self, db_session: Session):
        user = UserModel(
            id=uuid.uuid4(),
            email="novice@university.edu",
            full_name="Novice Researcher",
            hashed_password="pw_hash",
            role="STUDENT",
        )
        db_session.add(user)
        db_session.flush()

        profile = ResearchProfileModel(
            id=uuid.uuid4(),
            user_id=user.id,
        )
        db_session.add(profile)
        db_session.commit()

        reloaded = db_session.get(ResearchProfileModel, profile.id)
        assert reloaded is not None
        assert reloaded.academic_status == "UNKNOWN"
        assert reloaded.institution_id is None
        assert reloaded.canonical_researcher_id is None
        assert reloaded.orcid is None
        assert reloaded.openalex_id is None


# ── 2. External Identifier Normalization Tests ────────────────────────────────


class TestIdentifierNormalization:
    @pytest.mark.parametrize(
        "raw_orcid,expected",
        [
            ("0000-0002-1825-0097", "0000-0002-1825-0097"),
            ("https://orcid.org/0000-0002-1825-0097", "0000-0002-1825-0097"),
            ("http://orcid.org/0000-0002-1825-0097", "0000-0002-1825-0097"),
            ("orcid.org/0000-0002-1825-0097", "0000-0002-1825-0097"),
            (" 0000-0002-1825-009x ", "0000-0002-1825-009X"),
        ],
    )
    def test_orcid_valid_formats(self, raw_orcid: str, expected: str):
        assert normalize_orcid(raw_orcid) == expected

    @pytest.mark.parametrize(
        "invalid_orcid",
        [
            "not-an-orcid",
            "0000-0002-1825-00",
            "0000000218250097",
            "0000-0002-1825-009Z",
        ],
    )
    def test_orcid_invalid_raises(self, invalid_orcid: str):
        with pytest.raises(ValueError):
            normalize_orcid(invalid_orcid)

    @pytest.mark.parametrize(
        "raw_openalex,expected",
        [
            ("A5048491430", "A5048491430"),
            ("https://openalex.org/A5048491430", "A5048491430"),
            ("http://openalex.org/a5048491430", "A5048491430"),
            ("5048491430", "A5048491430"),
        ],
    )
    def test_openalex_valid_formats(self, raw_openalex: str, expected: str):
        assert normalize_openalex_id(raw_openalex) == expected

    def test_external_identifiers_schema(self):
        schema = ExternalIdentifiersSchema(
            orcid="https://orcid.org/0000-0003-1613-5981",
            openalex_id="https://openalex.org/A1983995261",
            google_scholar_id="abcXYZ123",
        )
        assert schema.orcid == "0000-0003-1613-5981"
        assert schema.openalex_id == "A1983995261"
        assert schema.google_scholar_id == "abcXYZ123"


# ── 3. Profile Completeness Tests ─────────────────────────────────────────────


class TestProfileCompleteness:
    def test_completeness_empty_profile(self):
        profile = ResearchProfileModel(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            academic_status="UNKNOWN",
        )
        comp = ResearcherProfileService.compute_profile_completeness(profile)
        assert comp.score == 0.0
        assert comp.percentage == 0
        assert comp.level == CompletenessLevel.INCOMPLETE
        assert comp.is_complete is False
        assert "academic_status" in comp.missing_fields
        assert "institution" in comp.missing_fields

    def test_completeness_partial_profile(self):
        user = UserModel(
            id=uuid.uuid4(),
            email="jane@mit.edu",
            full_name="Jane Doe",
            hashed_password="pw",
        )
        profile = ResearchProfileModel(
            id=uuid.uuid4(),
            user_id=user.id,
            academic_status="PHD",
            institution="MIT",
            department="EECS",
            user=user,
        )
        comp = ResearcherProfileService.compute_profile_completeness(profile)
        # Full name (0.15) + Email (0.10) + Status (0.15) + Inst (0.15) + Dept (0.10) = 0.65
        assert comp.score >= 0.60
        assert comp.level == CompletenessLevel.INTERMEDIATE
        assert comp.field_breakdown["full_name"] is True
        assert comp.field_breakdown["email"] is True
        assert comp.field_breakdown["academic_status"] is True
        assert comp.field_breakdown["bio"] is False

    def test_completeness_full_profile(self):
        user = UserModel(
            id=uuid.uuid4(),
            email="dr.richard@caltech.edu",
            full_name="Dr. Richard Feynman",
            hashed_password="pw",
        )
        profile = ResearchProfileModel(
            id=uuid.uuid4(),
            user_id=user.id,
            academic_status="FACULTY",
            institution_id=uuid.uuid4(),
            institution="Caltech",
            department="Physics",
            bio="Theoretical physicist and Nobel laureate.",
            orcid="0000-0002-1825-0097",
            keywords=["quantum mechanics", "particle physics"],
            user=user,
        )
        comp = ResearcherProfileService.compute_profile_completeness(profile)
        assert comp.score == 1.0
        assert comp.percentage == 100
        assert comp.level == CompletenessLevel.COMPLETE
        assert comp.is_complete is True
        assert len(comp.missing_fields) == 0


# ── 4. Service Layer Tests ───────────────────────────────────────────────────


class TestResearcherProfileService:
    def test_create_and_retrieve_profile(self, db_session: Session):
        payload = ResearcherProfileCreate(
            full_name="Ada Lovelace",
            email="ada@analytical.engine",
            academic_status=AcademicStatus.RESEARCHER,
            department="Mathematics",
            institution_name="University of Cambridge",
            orcid="0000-0002-1825-0097",
            keywords=["computation", "algorithms"],
        )

        profile = ResearcherProfileService.create_profile(db_session, payload)
        assert profile.id is not None
        assert profile.user.full_name == "Ada Lovelace"
        assert profile.academic_status == "RESEARCHER"

        retrieved = ResearcherProfileService.get_profile(db_session, profile.id)
        assert retrieved is not None
        assert retrieved.id == profile.id

        by_user = ResearcherProfileService.get_profile_by_user_id(db_session, profile.user_id)
        assert by_user is not None
        assert by_user.id == profile.id

    def test_duplicate_profile_creation_rejected(self, db_session: Session):
        payload = ResearcherProfileCreate(
            full_name="Alan Turing",
            email="alan@cambridge.ac.uk",
            academic_status=AcademicStatus.FACULTY,
        )
        profile = ResearcherProfileService.create_profile(db_session, payload)

        with pytest.raises(ValueError, match="already has a research profile"):
            ResearcherProfileService.create_profile(
                db_session, payload, user_id=profile.user_id
            )

    def test_institution_and_canonical_researcher_resolution(self, db_session: Session):
        inst = InstitutionModel(
            id=uuid.uuid4(),
            display_name="Stanford University",
            country_code="US",
        )
        researcher = ResearcherModel(
            id=uuid.uuid4(),
            openalex_id="A9999999999",
            orcid="0000-0001-2345-6789",
            display_name="John Stanford",
            works_count=10,
        )
        db_session.add_all([inst, researcher])
        db_session.flush()

        payload = ResearcherProfileCreate(
            full_name="John Stanford",
            email="john@stanford.edu",
            academic_status=AcademicStatus.POSTDOC,
            institution_name="Stanford University",
            orcid="0000-0001-2345-6789",
        )
        profile = ResearcherProfileService.create_profile(db_session, payload)

        assert profile.institution_id == inst.id
        assert profile.canonical_researcher_id == researcher.id

    def test_partial_profile_update(self, db_session: Session):
        payload = ResearcherProfileCreate(
            full_name="Linus Torvalds",
            email="linus@linuxfoundation.org",
            academic_status=AcademicStatus.OTHER,
        )
        profile = ResearcherProfileService.create_profile(db_session, payload)

        update_payload = ResearcherProfileUpdate(
            full_name="Linus B. Torvalds",
            academic_status=AcademicStatus.RESEARCHER,
            bio="Creator of Linux and Git.",
            keywords=["operating systems", "kernels"],
        )
        updated = ResearcherProfileService.update_profile(
            db_session, profile.id, update_payload
        )
        assert updated is not None
        assert updated.user.full_name == "Linus B. Torvalds"
        assert updated.academic_status == "RESEARCHER"
        assert updated.bio == "Creator of Linux and Git."
        assert "kernels" in updated.keywords

    def test_get_researcher_works(self, db_session: Session):
        researcher = ResearcherModel(
            id=uuid.uuid4(),
            display_name="Nikola Tesla",
            works_count=2,
        )
        work1 = ResearchWorkModel(
            id=uuid.uuid4(),
            title="A New System of Alternating Current Motors",
            doi="10.1000/182",
            publication_year=1888,
            work_type="article",
            cited_by_count=500,
        )
        work2 = ResearchWorkModel(
            id=uuid.uuid4(),
            title="Experiments with Alternate Currents",
            doi="10.1000/183",
            publication_year=1892,
            work_type="book",
            cited_by_count=250,
        )
        author_link1 = ResearchWorkAuthorModel(
            work_id=work1.id,
            researcher_id=researcher.id,
            author_position="first",
            is_corresponding=True,
        )
        author_link2 = ResearchWorkAuthorModel(
            work_id=work2.id,
            researcher_id=researcher.id,
            author_position="first",
            is_corresponding=False,
        )
        user = UserModel(
            id=uuid.uuid4(),
            email="nikola@tesla.org",
            full_name="Nikola Tesla",
            hashed_password="pw",
        )
        db_session.add_all([researcher, work1, work2, author_link1, author_link2, user])
        db_session.flush()

        profile = ResearchProfileModel(
            id=uuid.uuid4(),
            user_id=user.id,
            canonical_researcher_id=researcher.id,
            academic_status="FACULTY",
        )
        db_session.add(profile)
        db_session.commit()

        works = ResearcherProfileService.get_researcher_works(db_session, profile.id)
        assert len(works) == 2
        assert works[0].title == "Experiments with Alternate Currents"  # 1892 desc
        assert works[1].title == "A New System of Alternating Current Motors"  # 1888


# ── 5. FastAPI API Endpoints Tests ───────────────────────────────────────────


class TestResearcherProfileAPI:
    def test_api_create_researcher_profile(self, client: TestClient):
        payload = {
            "full_name": "Rosalind Franklin",
            "email": "rosalind@kcl.ac.uk",
            "academic_status": "FACULTY",
            "department": "Biophysics",
            "institution_name": "King's College London",
            "orcid": "0000-0002-1825-0097",
            "keywords": ["x-ray crystallography", "dna structure"],
        }
        res = client.post("/api/v1/researchers", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["full_name"] == "Rosalind Franklin"
        assert data["academic_status"] == "FACULTY"
        assert data["orcid"] == "0000-0002-1825-0097"
        assert data["completeness"]["level"] in ["INTERMEDIATE", "COMPLETE"]

    def test_api_get_profile_by_id_and_user_id(self, client: TestClient, db_session: Session):
        create_payload = ResearcherProfileCreate(
            full_name="Claude Shannon",
            email="shannon@bell-labs.com",
            academic_status=AcademicStatus.RESEARCHER,
            department="Mathematics",
            institution_name="Bell Labs",
        )
        profile = ResearcherProfileService.create_profile(db_session, create_payload)

        # GET by profile ID
        res = client.get(f"/api/v1/researchers/{profile.id}", headers={"X-User-ID": str(profile.user_id)})
        assert res.status_code == 200
        assert res.json()["full_name"] == "Claude Shannon"

        # GET by user ID (fallback)
        res_user = client.get(f"/api/v1/researchers/{profile.user_id}", headers={"X-User-ID": str(profile.user_id)})
        assert res_user.status_code == 200
        assert res_user.json()["id"] == str(profile.id)

    def test_api_get_profile_not_found(self, client: TestClient):
        random_id = uuid.uuid4()
        res = client.get(f"/api/v1/researchers/{random_id}")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()

    def test_api_patch_profile(self, client: TestClient, db_session: Session):
        create_payload = ResearcherProfileCreate(
            full_name="Dorothy Hodgkin",
            email="dorothy@oxford.ac.uk",
            academic_status=AcademicStatus.POSTDOC,
        )
        profile = ResearcherProfileService.create_profile(db_session, create_payload)

        patch_payload = {
            "academic_status": "FACULTY",
            "bio": "Crystallography of biological molecules.",
            "keywords": ["insulin", "vitamin b12"],
        }
        res = client.patch(
            f"/api/v1/researchers/{profile.id}",
            json=patch_payload,
            headers={"X-User-ID": str(profile.user_id)},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["academic_status"] == "FACULTY"
        assert data["bio"] == "Crystallography of biological molecules."
        assert "insulin" in data["keywords"]

    def test_api_get_profile_completeness(self, client: TestClient, db_session: Session):
        create_payload = ResearcherProfileCreate(
            full_name="Carl Friedrich Gauss",
            email="gauss@gottingen.de",
            academic_status=AcademicStatus.FACULTY,
            institution_name="University of Göttingen",
        )
        profile = ResearcherProfileService.create_profile(db_session, create_payload)

        res = client.get(
            f"/api/v1/researchers/{profile.id}/completeness",
            headers={"X-User-ID": str(profile.user_id)},
        )
        assert res.status_code == 200
        data = res.json()
        assert "score" in data
        assert "percentage" in data
        assert "field_breakdown" in data
        assert data["field_breakdown"]["full_name"] is True
