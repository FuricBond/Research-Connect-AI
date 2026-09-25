"""
Phase 5.10 — Faculty Research Posting Service.

Owns the posting lifecycle, authorship authorization, and taxonomy-aware discovery queries.

Guarantees:
  - Deterministic state machine: every transition is explicitly enumerated, so a posting can
    never reach a state by accident and the set of legal next states is inspectable.
  - Authorship enforcement: writes require the owning account, or an administrator.
  - Visibility: only OPEN postings are publicly discoverable; an author always sees their own.
  - Zero N+1: list and summary paths eagerly load authors and topics in bounded queries.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Sequence
import uuid

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.research_posting import (
    PostingStatus,
    PostingType,
    ResearchPostingModel,
    ResearchPostingTopicModel,
)
from app.models.research_profile import ResearchProfileModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from app.schemas.research_posting import (
    PostingSummaryResponse,
    PostingTopicSchema,
    ResearchPostingAuthorSchema,
    ResearchPostingCreate,
    ResearchPostingListResponse,
    ResearchPostingRead,
    ResearchPostingUpdate,
)

logger = logging.getLogger(__name__)

# Roles permitted to author postings. Students discover and apply; they do not supervise.
AUTHORING_ROLES = frozenset({"FACULTY", "ADMIN"})

# Deterministic lifecycle. DRAFT and OPEN are reversible while an author is still deciding;
# FILLED and CANCELLED are outcomes that only lead to ARCHIVED, so a closed search cannot be
# quietly reopened under the same posting and mislead applicants who were already rejected.
VALID_TRANSITIONS: dict[PostingStatus, frozenset[PostingStatus]] = {
    PostingStatus.DRAFT: frozenset({PostingStatus.OPEN, PostingStatus.CANCELLED, PostingStatus.ARCHIVED}),
    PostingStatus.OPEN: frozenset(
        {PostingStatus.CLOSED, PostingStatus.FILLED, PostingStatus.CANCELLED, PostingStatus.DRAFT}
    ),
    PostingStatus.CLOSED: frozenset({PostingStatus.OPEN, PostingStatus.FILLED, PostingStatus.ARCHIVED}),
    PostingStatus.FILLED: frozenset({PostingStatus.ARCHIVED}),
    PostingStatus.CANCELLED: frozenset({PostingStatus.ARCHIVED}),
    PostingStatus.ARCHIVED: frozenset(),
}

SORTABLE_FIELDS = frozenset({"created_at", "updated_at", "application_deadline", "title", "application_count"})


class PostingNotFoundError(Exception):
    pass


class PostingPermissionError(Exception):
    pass


class InvalidPostingTransitionError(Exception):
    pass


class ResearchPostingService:
    DEFAULT_LIMIT = 20
    MAX_LIMIT = 100

    # ── Authorization ────────────────────────────────────────────────────────

    @staticmethod
    def assert_can_author(user: UserModel) -> None:
        """Only faculty and administrators may create postings."""
        if user.role not in AUTHORING_ROLES:
            raise PostingPermissionError(
                "Only FACULTY and ADMIN accounts may create research postings."
            )

    @staticmethod
    def _is_owner_or_admin(posting: ResearchPostingModel, user: UserModel) -> bool:
        return posting.author_user_id == user.id or user.role == "ADMIN"

    @classmethod
    def _assert_can_modify(cls, posting: ResearchPostingModel, user: UserModel) -> None:
        if not cls._is_owner_or_admin(posting, user):
            raise PostingPermissionError("Only the posting's author may modify it.")

    # ── Lifecycle ────────────────────────────────────────────────────────────

    @staticmethod
    def get_allowed_transitions(status: PostingStatus | str) -> list[PostingStatus]:
        current = PostingStatus(status) if not isinstance(status, PostingStatus) else status
        return sorted(VALID_TRANSITIONS.get(current, frozenset()), key=lambda s: s.value)

    # ── Reads ────────────────────────────────────────────────────────────────

    @staticmethod
    def _base_query() -> Select:
        return select(ResearchPostingModel).options(
            joinedload(ResearchPostingModel.author_profile).joinedload(ResearchProfileModel.user),
            selectinload(ResearchPostingModel.topic_associations).joinedload(
                ResearchPostingTopicModel.topic
            ),
        )

    @classmethod
    def get_posting(
        cls,
        db: Session,
        posting_id: uuid.UUID,
        *,
        requesting_user: UserModel | None = None,
    ) -> ResearchPostingModel:
        """
        Loads a posting, enforcing visibility.

        A posting that is not OPEN is visible only to its author or an administrator. The same
        `PostingNotFoundError` is raised for "does not exist" and "not visible to you" so the
        existence of an unpublished draft is not disclosed.
        """
        posting = db.execute(
            cls._base_query().where(ResearchPostingModel.id == posting_id)
        ).unique().scalar_one_or_none()
        if posting is None:
            raise PostingNotFoundError(f"Research posting '{posting_id}' not found.")

        if posting.status != PostingStatus.OPEN.value:
            if requesting_user is None or not cls._is_owner_or_admin(posting, requesting_user):
                raise PostingNotFoundError(f"Research posting '{posting_id}' not found.")
        return posting

    @classmethod
    def list_postings(
        cls,
        db: Session,
        *,
        requesting_user: UserModel | None = None,
        author_profile_id: uuid.UUID | None = None,
        posting_type: PostingType | None = None,
        status: PostingStatus | None = None,
        country: str | None = None,
        work_mode: str | None = None,
        topic_id: uuid.UUID | None = None,
        search: str | None = None,
        accepting_only: bool = False,
        include_own_drafts: bool = False,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        reference_time: datetime | None = None,
    ) -> ResearchPostingListResponse:
        """
        Lists postings with filtering and pagination.

        By default only OPEN postings are returned. `include_own_drafts` additionally returns
        the requesting author's non-public postings, which is how an author reviews their own
        drafts without a separate endpoint.
        """
        now = reference_time or datetime.now(timezone.utc)
        safe_limit = max(1, min(limit, cls.MAX_LIMIT))
        safe_offset = max(0, offset)

        stmt = cls._base_query()
        count_stmt = select(func.count()).select_from(ResearchPostingModel)

        conditions = []
        if status is not None:
            # An explicit non-OPEN status filter is only meaningful for one's own postings.
            conditions.append(ResearchPostingModel.status == status.value)
            if status != PostingStatus.OPEN and requesting_user is not None:
                conditions.append(ResearchPostingModel.author_user_id == requesting_user.id)
        elif include_own_drafts and requesting_user is not None:
            conditions.append(
                or_(
                    ResearchPostingModel.status == PostingStatus.OPEN.value,
                    ResearchPostingModel.author_user_id == requesting_user.id,
                )
            )
        else:
            conditions.append(ResearchPostingModel.status == PostingStatus.OPEN.value)

        if author_profile_id is not None:
            conditions.append(ResearchPostingModel.author_profile_id == author_profile_id)
        if posting_type is not None:
            conditions.append(ResearchPostingModel.posting_type == posting_type.value)
        if country:
            conditions.append(ResearchPostingModel.country == country.strip().upper())
        if work_mode:
            conditions.append(ResearchPostingModel.work_mode == work_mode.strip().upper())
        if accepting_only:
            conditions.append(
                or_(
                    ResearchPostingModel.application_deadline.is_(None),
                    ResearchPostingModel.application_deadline > now,
                )
            )
        if search:
            pattern = f"%{search.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(ResearchPostingModel.title).like(pattern),
                    func.lower(ResearchPostingModel.description).like(pattern),
                    func.lower(func.coalesce(ResearchPostingModel.summary, "")).like(pattern),
                )
            )
        if topic_id is not None:
            topic_subquery = (
                select(ResearchPostingTopicModel.posting_id)
                .where(ResearchPostingTopicModel.topic_id == topic_id)
                .scalar_subquery()
            )
            conditions.append(ResearchPostingModel.id.in_(topic_subquery))

        for condition in conditions:
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        total = db.execute(count_stmt).scalar_one()

        sort_field = sort_by if sort_by in SORTABLE_FIELDS else "created_at"
        column = getattr(ResearchPostingModel, sort_field)
        # A secondary key on id keeps pagination stable when the primary key ties.
        ordering = (
            [column.asc(), ResearchPostingModel.id.asc()]
            if sort_order.lower() == "asc"
            else [column.desc(), ResearchPostingModel.id.desc()]
        )
        postings = (
            db.execute(stmt.order_by(*ordering).limit(safe_limit).offset(safe_offset))
            .unique()
            .scalars()
            .all()
        )

        return ResearchPostingListResponse(
            postings=[
                cls.build_posting_read(p, requesting_user=requesting_user, reference_time=now)
                for p in postings
            ],
            total=total,
            limit=safe_limit,
            offset=safe_offset,
        )

    @classmethod
    def get_author_summary(
        cls,
        db: Session,
        author_profile_id: uuid.UUID,
        *,
        reference_time: datetime | None = None,
    ) -> PostingSummaryResponse:
        """Aggregated counts for an author's postings, computed in two grouped queries."""
        now = reference_time or datetime.now(timezone.utc)

        status_rows = db.execute(
            select(ResearchPostingModel.status, func.count(), func.sum(ResearchPostingModel.application_count))
            .where(ResearchPostingModel.author_profile_id == author_profile_id)
            .group_by(ResearchPostingModel.status)
        ).all()
        type_rows = db.execute(
            select(ResearchPostingModel.posting_type, func.count())
            .where(ResearchPostingModel.author_profile_id == author_profile_id)
            .group_by(ResearchPostingModel.posting_type)
        ).all()

        by_status = {row[0]: row[1] for row in status_rows}
        total_applications = sum(int(row[2] or 0) for row in status_rows)

        accepting = db.execute(
            select(func.count())
            .select_from(ResearchPostingModel)
            .where(
                ResearchPostingModel.author_profile_id == author_profile_id,
                ResearchPostingModel.status == PostingStatus.OPEN.value,
                or_(
                    ResearchPostingModel.application_deadline.is_(None),
                    ResearchPostingModel.application_deadline > now,
                ),
            )
        ).scalar_one()

        return PostingSummaryResponse(
            author_profile_id=author_profile_id,
            total=sum(by_status.values()),
            by_status=by_status,
            by_type={row[0]: row[1] for row in type_rows},
            total_applications=total_applications,
            open_accepting_applications=accepting,
        )

    # ── Writes ───────────────────────────────────────────────────────────────

    @classmethod
    def create_posting(
        cls,
        db: Session,
        author_profile: ResearchProfileModel,
        author_user: UserModel,
        payload: ResearchPostingCreate,
    ) -> ResearchPostingModel:
        cls.assert_can_author(author_user)

        posting = ResearchPostingModel(
            id=uuid.uuid4(),
            author_profile_id=author_profile.id,
            author_user_id=author_user.id,
            title=payload.title,
            posting_type=payload.posting_type.value,
            status=PostingStatus.DRAFT.value,
            summary=payload.summary,
            description=payload.description,
            required_skills=list(payload.required_skills),
            preferred_qualifications=payload.preferred_qualifications,
            # Placement defaults to the author's own affiliation, which is correct for the
            # overwhelming majority of postings and saves retyping it every time.
            institution=payload.institution or author_profile.institution,
            department=payload.department or author_profile.department,
            location=payload.location,
            country=payload.country,
            work_mode=payload.work_mode.value,
            positions_available=payload.positions_available,
            application_deadline=payload.application_deadline,
            expected_start_date=payload.expected_start_date,
            expected_end_date=payload.expected_end_date,
            contact_email=payload.contact_email,
            external_url=payload.external_url,
        )
        db.add(posting)
        db.flush()

        cls._replace_topics(db, posting, payload.topic_ids)
        db.commit()
        db.refresh(posting)
        logger.info(
            "Research posting created",
            extra={"posting_id": str(posting.id), "author_profile_id": str(author_profile.id)},
        )
        return posting

    @classmethod
    def update_posting(
        cls,
        db: Session,
        posting_id: uuid.UUID,
        user: UserModel,
        payload: ResearchPostingUpdate,
    ) -> ResearchPostingModel:
        posting = db.execute(
            cls._base_query().where(ResearchPostingModel.id == posting_id)
        ).unique().scalar_one_or_none()
        if posting is None:
            raise PostingNotFoundError(f"Research posting '{posting_id}' not found.")
        cls._assert_can_modify(posting, user)

        if posting.status == PostingStatus.ARCHIVED.value:
            raise InvalidPostingTransitionError("An archived posting can no longer be edited.")

        data = payload.model_dump(exclude_unset=True)
        topic_ids = data.pop("topic_ids", None)

        for field, value in data.items():
            if field == "posting_type" and value is not None:
                posting.posting_type = PostingType(value).value
            elif field == "work_mode" and value is not None:
                posting.work_mode = value.value if hasattr(value, "value") else str(value)
            else:
                setattr(posting, field, value)

        if topic_ids is not None:
            cls._replace_topics(db, posting, topic_ids)

        db.commit()
        db.refresh(posting)
        return posting

    @classmethod
    def transition_status(
        cls,
        db: Session,
        posting_id: uuid.UUID,
        user: UserModel,
        target_status: PostingStatus,
        note: str | None = None,
        reference_time: datetime | None = None,
    ) -> ResearchPostingModel:
        """Applies a lifecycle transition, rejecting any move the state machine disallows."""
        posting = db.execute(
            cls._base_query().where(ResearchPostingModel.id == posting_id)
        ).unique().scalar_one_or_none()
        if posting is None:
            raise PostingNotFoundError(f"Research posting '{posting_id}' not found.")
        cls._assert_can_modify(posting, user)

        current = PostingStatus(posting.status)
        if target_status == current:
            return posting
        if target_status not in VALID_TRANSITIONS.get(current, frozenset()):
            allowed = ", ".join(s.value for s in cls.get_allowed_transitions(current)) or "none"
            raise InvalidPostingTransitionError(
                f"Cannot move a posting from {current.value} to {target_status.value}. "
                f"Allowed transitions: {allowed}."
            )

        now = reference_time or datetime.now(timezone.utc)
        posting.status = target_status.value
        posting.status_note = note

        if target_status == PostingStatus.OPEN and posting.published_at is None:
            posting.published_at = now
        if target_status in (PostingStatus.CLOSED, PostingStatus.FILLED, PostingStatus.CANCELLED):
            posting.closed_at = now
        if target_status == PostingStatus.ARCHIVED:
            posting.archived_at = now
        if target_status == PostingStatus.OPEN:
            # Reopening clears the previous closure so the record does not claim to be both
            # open and closed at once.
            posting.closed_at = None

        db.commit()
        db.refresh(posting)
        logger.info(
            "Research posting transitioned",
            extra={
                "posting_id": str(posting.id),
                "from_status": current.value,
                "to_status": target_status.value,
            },
        )
        return posting

    @classmethod
    def delete_posting(cls, db: Session, posting_id: uuid.UUID, user: UserModel) -> None:
        """
        Deletes a posting outright.

        Only permitted while it is still a DRAFT: once published, other researchers may have
        seen or applied to it, so the auditable path is CANCELLED then ARCHIVED.
        """
        posting = db.get(ResearchPostingModel, posting_id)
        if posting is None:
            raise PostingNotFoundError(f"Research posting '{posting_id}' not found.")
        cls._assert_can_modify(posting, user)
        if posting.status != PostingStatus.DRAFT.value:
            raise InvalidPostingTransitionError(
                "Only a DRAFT posting may be deleted. Cancel and archive a published posting instead."
            )
        db.delete(posting)
        db.commit()

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _replace_topics(
        db: Session,
        posting: ResearchPostingModel,
        topic_ids: Sequence[uuid.UUID] | None,
    ) -> None:
        """
        Replaces a posting's topic links, ignoring ids that are not canonical topics.

        Unknown ids are dropped rather than raising: the taxonomy is curated separately, and a
        stale id from a client should not block an otherwise valid posting edit.
        """
        posting.topic_associations.clear()
        db.flush()
        if not topic_ids:
            return

        unique_ids = list(dict.fromkeys(topic_ids))
        known = set(
            db.execute(select(TopicModel.id).where(TopicModel.id.in_(unique_ids))).scalars().all()
        )
        for index, topic_id in enumerate(unique_ids):
            if topic_id not in known:
                continue
            db.add(
                ResearchPostingTopicModel(
                    posting_id=posting.id,
                    topic_id=topic_id,
                    is_primary=(index == 0),
                    confidence_score=1.00,
                )
            )
        db.flush()

    @classmethod
    def build_posting_read(
        cls,
        posting: ResearchPostingModel,
        *,
        requesting_user: UserModel | None = None,
        reference_time: datetime | None = None,
    ) -> ResearchPostingRead:
        now = reference_time or datetime.now(timezone.utc)

        deadline = posting.application_deadline
        days_remaining: int | None = None
        if deadline is not None:
            aware_deadline = deadline if deadline.tzinfo is not None else deadline.replace(tzinfo=timezone.utc)
            days_remaining = (aware_deadline - now).days

        is_open = posting.status == PostingStatus.OPEN.value
        accepting = is_open and (
            deadline is None
            or (deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)) > now
        )

        profile = posting.author_profile
        author = ResearchPostingAuthorSchema(
            profile_id=posting.author_profile_id,
            full_name=getattr(getattr(profile, "user", None), "full_name", None),
            institution=getattr(profile, "institution", None),
            department=getattr(profile, "department", None),
            academic_status=getattr(profile, "academic_status", None),
        )

        topics = [
            PostingTopicSchema(
                topic_id=assoc.topic_id,
                name=getattr(assoc.topic, "name", None),
                slug=getattr(assoc.topic, "slug", None),
                is_primary=bool(assoc.is_primary),
                confidence_score=float(assoc.confidence_score or 1.0),
            )
            for assoc in sorted(
                posting.topic_associations,
                key=lambda a: (not a.is_primary, str(getattr(a.topic, "name", "") or "")),
            )
        ]

        return ResearchPostingRead(
            id=posting.id,
            author=author,
            title=posting.title,
            posting_type=PostingType(posting.posting_type),
            status=PostingStatus(posting.status),
            summary=posting.summary,
            description=posting.description,
            required_skills=list(posting.required_skills or []),
            preferred_qualifications=posting.preferred_qualifications,
            institution=posting.institution,
            department=posting.department,
            location=posting.location,
            country=posting.country,
            work_mode=posting.work_mode,
            positions_available=posting.positions_available,
            application_deadline=posting.application_deadline,
            expected_start_date=posting.expected_start_date,
            expected_end_date=posting.expected_end_date,
            contact_email=posting.contact_email,
            external_url=posting.external_url,
            topics=topics,
            application_count=posting.application_count,
            published_at=posting.published_at,
            closed_at=posting.closed_at,
            archived_at=posting.archived_at,
            status_note=posting.status_note,
            created_at=posting.created_at,
            updated_at=posting.updated_at,
            is_accepting_applications=accepting,
            days_until_deadline=days_remaining,
            allowed_transitions=cls.get_allowed_transitions(posting.status),
            is_owner=bool(requesting_user is not None and posting.author_user_id == requesting_user.id),
        )
