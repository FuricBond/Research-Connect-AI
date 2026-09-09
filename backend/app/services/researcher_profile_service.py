from __future__ import annotations

import logging
from typing import Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

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
    InstitutionSummarySchema,
    ProfileCompletenessSchema,
    ResearcherProfileCreate,
    ResearcherProfileRead,
    ResearcherProfileUpdate,
    ResearcherWorkSummarySchema,
)

logger = logging.getLogger(__name__)


class ResearcherProfileService:
    """
    Canonical Researcher Profile Service for ResearchConnect AI (Phase 3.1).

    Responsibilities:
      - CRUD lifecycle for canonical researcher profiles
      - Deterministic profile completeness calculation
      - Resolution of institutions and canonical scholarly entities
      - Eager-loaded retrieval of author publications (zero N+1)
      - Pure data foundation: NO personalization, NO ranking alteration
    """

    @classmethod
    def get_profile(
        cls, db: Session, profile_id: uuid.UUID
    ) -> ResearchProfileModel | None:
        """Retrieve a profile by its ID with eager loaded relationships."""
        stmt = (
            select(ResearchProfileModel)
            .options(
                joinedload(ResearchProfileModel.user),
                joinedload(ResearchProfileModel.institution_rel),
                joinedload(ResearchProfileModel.canonical_researcher),
            )
            .where(ResearchProfileModel.id == profile_id)
        )
        return db.execute(stmt).scalars().first()

    @classmethod
    def get_profile_by_user_id(
        cls, db: Session, user_id: uuid.UUID
    ) -> ResearchProfileModel | None:
        """Retrieve a profile by associated user ID."""
        stmt = (
            select(ResearchProfileModel)
            .options(
                joinedload(ResearchProfileModel.user),
                joinedload(ResearchProfileModel.institution_rel),
                joinedload(ResearchProfileModel.canonical_researcher),
            )
            .where(ResearchProfileModel.user_id == user_id)
        )
        return db.execute(stmt).scalars().first()

    @classmethod
    def resolve_institution(
        cls,
        db: Session,
        institution_id: uuid.UUID | None = None,
        institution_name: str | None = None,
    ) -> InstitutionModel | None:
        """Resolve an institution by foreign key ID or by display name."""
        if institution_id:
            inst = db.get(InstitutionModel, institution_id)
            if inst:
                return inst
        if institution_name and institution_name.strip():
            cleaned = institution_name.strip()
            stmt = select(InstitutionModel).where(
                func.lower(InstitutionModel.display_name) == cleaned.lower()
            )
            return db.execute(stmt).scalars().first()
        return None

    @classmethod
    def resolve_canonical_researcher(
        cls,
        db: Session,
        orcid: str | None = None,
        openalex_id: str | None = None,
    ) -> ResearcherModel | None:
        """Resolve a canonical ResearcherModel from OpenAlex ID or ORCID."""
        if openalex_id and openalex_id.strip():
            stmt = select(ResearcherModel).where(
                ResearcherModel.openalex_id == openalex_id.strip()
            )
            found = db.execute(stmt).scalars().first()
            if found:
                return found
        if orcid and orcid.strip():
            stmt = select(ResearcherModel).where(
                ResearcherModel.orcid == orcid.strip()
            )
            found = db.execute(stmt).scalars().first()
            if found:
                return found
        return None

    @classmethod
    def create_profile(
        cls,
        db: Session,
        payload: ResearcherProfileCreate,
        user_id: uuid.UUID | None = None,
    ) -> ResearchProfileModel:
        """
        Create a canonical researcher profile and connect it to a user account.
        Resolves canonical institution and OpenAlex/Crossref researcher identities.
        """
        user: UserModel | None = None
        if user_id:
            user = db.get(UserModel, user_id)
            if not user:
                raise ValueError(f"User with ID {user_id} does not exist.")
        else:
            # Check if user exists by email
            stmt = select(UserModel).where(UserModel.email == payload.email)
            user = db.execute(stmt).scalars().first()
            if not user:
                # Map academic status to platform role
                role = "FACULTY" if payload.academic_status == AcademicStatus.FACULTY else "STUDENT"
                user = UserModel(
                    id=uuid.uuid4(),
                    email=payload.email,
                    full_name=payload.full_name,
                    hashed_password="auth_placeholder",  # Replaced when auth module is activated
                    role=role,
                    is_active=True,
                    is_verified=False,
                )
                db.add(user)
                db.flush()

        # Verify whether user already has a research profile
        existing_profile = cls.get_profile_by_user_id(db, user.id)
        if existing_profile:
            raise ValueError(f"User {user.id} already has a research profile.")

        # Resolve institution
        inst = cls.resolve_institution(
            db, payload.institution_id, payload.institution_name
        )
        resolved_inst_id = inst.id if inst else payload.institution_id
        resolved_inst_name = inst.display_name if inst else payload.institution_name

        # Resolve canonical researcher entity (OpenAlex / Crossref)
        canonical_researcher = cls.resolve_canonical_researcher(
            db, payload.orcid, payload.openalex_id
        )
        canonical_researcher_id = canonical_researcher.id if canonical_researcher else None

        profile = ResearchProfileModel(
            id=uuid.uuid4(),
            user_id=user.id,
            institution_id=resolved_inst_id,
            institution=resolved_inst_name,
            department=payload.department,
            academic_status=(
                payload.academic_status.value
                if isinstance(payload.academic_status, AcademicStatus)
                else payload.academic_status
            ),
            academic_level=payload.academic_level,
            bio=payload.bio,
            canonical_researcher_id=canonical_researcher_id,
            orcid=payload.orcid,
            openalex_id=payload.openalex_id,
            external_identifiers=payload.external_identifiers or {},
            keywords=payload.keywords or [],
            target_opportunity_types=payload.target_opportunity_types or [],
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile

    @classmethod
    def update_profile(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        payload: ResearcherProfileUpdate,
    ) -> ResearchProfileModel | None:
        """Partially update an existing researcher profile."""
        profile = cls.get_profile(db, profile_id)
        if not profile:
            return None

        # Update user full name if supplied
        if payload.full_name is not None and profile.user:
            profile.user.full_name = payload.full_name

        if payload.academic_status is not None:
            profile.academic_status = (
                payload.academic_status.value
                if isinstance(payload.academic_status, AcademicStatus)
                else payload.academic_status
            )
        if payload.academic_level is not None:
            profile.academic_level = payload.academic_level
        if payload.department is not None:
            profile.department = payload.department
        if payload.bio is not None:
            profile.bio = payload.bio
        if payload.keywords is not None:
            profile.keywords = payload.keywords
        if payload.target_opportunity_types is not None:
            profile.target_opportunity_types = payload.target_opportunity_types
        if payload.external_identifiers is not None:
            profile.external_identifiers = payload.external_identifiers

        # Institution update
        if payload.institution_id is not None or payload.institution_name is not None:
            inst = cls.resolve_institution(
                db, payload.institution_id, payload.institution_name
            )
            if inst:
                profile.institution_id = inst.id
                profile.institution = inst.display_name
            else:
                if payload.institution_id is not None:
                    profile.institution_id = payload.institution_id
                if payload.institution_name is not None:
                    profile.institution = payload.institution_name

        # External IDs & canonical entity resolution
        recheck_canonical = False
        if payload.orcid is not None:
            profile.orcid = payload.orcid
            recheck_canonical = True
        if payload.openalex_id is not None:
            profile.openalex_id = payload.openalex_id
            recheck_canonical = True

        if recheck_canonical:
            canonical = cls.resolve_canonical_researcher(
                db, profile.orcid, profile.openalex_id
            )
            profile.canonical_researcher_id = canonical.id if canonical else None

        db.commit()
        db.refresh(profile)
        return profile

    @classmethod
    def compute_profile_completeness(
        cls, profile: ResearchProfileModel, user: UserModel | None = None
    ) -> ProfileCompletenessSchema:
        """
        Calculate deterministic profile completeness metadata.

        Criteria and weights:
          - Full Name: 15%
          - Email: 10%
          - Academic Status (valid and not UNKNOWN): 15%
          - Institution (canonical ID or non-empty string): 15%
          - Department: 10%
          - Bio: 10%
          - External Scholarly Identity (ORCID or OpenAlex ID): 15%
          - Research Keywords: 10%
        Total = 100%.

        This score is metadata only — it does NOT influence recommendation ranking.
        """
        effective_user = user or profile.user
        has_full_name = bool(effective_user and effective_user.full_name and effective_user.full_name.strip())
        has_email = bool(effective_user and effective_user.email and effective_user.email.strip())

        status_val = profile.academic_status or "UNKNOWN"
        has_status = bool(status_val and status_val != "UNKNOWN" and status_val in AcademicStatus.__members__)
        has_institution = bool(profile.institution_id or (profile.institution and profile.institution.strip()))
        has_department = bool(profile.department and profile.department.strip())
        has_bio = bool(profile.bio and profile.bio.strip())
        has_external_id = bool(
            profile.orcid
            or profile.openalex_id
            or profile.canonical_researcher_id
            or (profile.external_identifiers and len(profile.external_identifiers) > 0)
        )
        has_keywords = bool(profile.keywords and len(profile.keywords) > 0)

        weights = {
            "full_name": (has_full_name, 0.15),
            "email": (has_email, 0.10),
            "academic_status": (has_status, 0.15),
            "institution": (has_institution, 0.15),
            "department": (has_department, 0.10),
            "bio": (has_bio, 0.10),
            "external_identity": (has_external_id, 0.15),
            "keywords": (has_keywords, 0.10),
        }

        score = sum(w for present, w in weights.values() if present)
        score = round(min(1.0, max(0.0, score)), 2)
        percentage = int(score * 100)

        missing = [field for field, (present, _) in weights.items() if not present]
        field_breakdown = {field: present for field, (present, _) in weights.items()}

        if score >= 0.85:
            level = CompletenessLevel.COMPLETE
        elif score >= 0.50:
            level = CompletenessLevel.INTERMEDIATE
        elif score >= 0.20:
            level = CompletenessLevel.BASIC
        else:
            level = CompletenessLevel.INCOMPLETE

        return ProfileCompletenessSchema(
            score=score,
            percentage=percentage,
            level=level,
            is_complete=(level == CompletenessLevel.COMPLETE),
            missing_fields=missing,
            field_breakdown=field_breakdown,
        )

    @classmethod
    def get_researcher_works(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ResearcherWorkSummarySchema]:
        """
        Retrieve publications authored by this researcher via canonical knowledge relations.
        Uses eager joined loading to avoid N+1 queries.
        """
        profile = cls.get_profile(db, profile_id)
        if not profile or not profile.canonical_researcher_id:
            return []

        stmt = (
            select(ResearchWorkAuthorModel)
            .join(ResearchWorkModel, ResearchWorkAuthorModel.work_id == ResearchWorkModel.id)
            .options(joinedload(ResearchWorkAuthorModel.work))
            .where(
                ResearchWorkAuthorModel.researcher_id
                == profile.canonical_researcher_id
            )
            .order_by(ResearchWorkModel.publication_year.desc().nulls_last())
            .limit(limit)
            .offset(offset)
        )
        author_links = db.execute(stmt).scalars().all()

        results: list[ResearcherWorkSummarySchema] = []
        for link in author_links:
            work = link.work
            if not work:
                continue
            results.append(
                ResearcherWorkSummarySchema(
                    id=work.id,
                    title=work.title,
                    doi=work.doi,
                    publication_year=work.publication_year,
                    work_type=work.work_type,
                    author_position=link.author_position,
                    is_corresponding=link.is_corresponding,
                    cited_by_count=work.cited_by_count or 0,
                )
            )
        return results

    @classmethod
    def build_profile_read(
        cls, profile: ResearchProfileModel
    ) -> ResearcherProfileRead:
        """Convert a ResearchProfileModel into the canonical API read schema."""
        completeness = cls.compute_profile_completeness(profile)

        institution_summary: InstitutionSummarySchema | None = None
        if profile.institution_rel:
            inst = profile.institution_rel
            institution_summary = InstitutionSummarySchema(
                id=inst.id,
                display_name=inst.display_name,
                ror=inst.ror,
                country_code=inst.country_code,
                institution_type=inst.institution_type,
                homepage_url=inst.homepage_url,
            )

        status_enum = AcademicStatus.UNKNOWN
        if profile.academic_status:
            try:
                status_enum = AcademicStatus(profile.academic_status)
            except ValueError:
                status_enum = AcademicStatus.UNKNOWN

        works_count = 0
        if profile.canonical_researcher:
            works_count = profile.canonical_researcher.works_count or 0

        return ResearcherProfileRead(
            id=profile.id,
            user_id=profile.user_id,
            full_name=profile.user.full_name if profile.user else "Unknown Researcher",
            email=profile.user.email if profile.user else None,
            academic_status=status_enum,
            academic_level=profile.academic_level,
            department=profile.department,
            bio=profile.bio,
            institution_id=profile.institution_id,
            institution_name=profile.institution,
            institution=institution_summary,
            canonical_researcher_id=profile.canonical_researcher_id,
            orcid=profile.orcid,
            openalex_id=profile.openalex_id,
            external_identifiers=profile.external_identifiers or {},
            keywords=profile.keywords or [],
            target_opportunity_types=profile.target_opportunity_types or [],
            completeness=completeness,
            works_count=works_count,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )
