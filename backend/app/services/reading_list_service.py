"""
Phase 5.14 — Personal reading list service.

Every operation is scoped to the calling user. An item id that exists but belongs to someone
else raises PermissionError (403), an unknown one ValueError (404), matching the workspace
routes.

Saving a paper is private bookkeeping, so nothing here records a personalization interaction or
feedback signal.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.reading_list import ReadingListItemModel, ReadingStatus
from app.models.research_knowledge import (
    ResearcherModel,
    ResearchSourceModel,
    ResearchWorkAuthorModel,
    ResearchWorkModel,
)
from app.schemas.reading_list import (
    ReadingListItemCreate,
    ReadingListItemRead,
    ReadingListItemUpdate,
    ReadingListResponse,
    ReadingListWorkSummary,
)
from app.services.bibtex_formatter import format_entries, ordered_author_names


def _work_options() -> tuple:
    """
    Loads each item's work with only the bibliographic columns, its authors and its venue, in a
    fixed number of queries however many items there are. The embedding and abstract are never
    loaded.
    """
    work = selectinload(ReadingListItemModel.work)
    return (
        work.load_only(
            ResearchWorkModel.id,
            ResearchWorkModel.title,
            ResearchWorkModel.doi,
            ResearchWorkModel.publication_year,
            ResearchWorkModel.work_type,
            ResearchWorkModel.landing_page_url,
            ResearchWorkModel.volume,
            ResearchWorkModel.issue,
            ResearchWorkModel.page,
            ResearchWorkModel.primary_source_id,
        ),
        work.selectinload(ResearchWorkModel.author_links)
        .selectinload(ResearchWorkAuthorModel.researcher)
        .load_only(ResearcherModel.id, ResearcherModel.display_name),
        work.selectinload(ResearchWorkModel.primary_source).load_only(
            ResearchSourceModel.id,
            ResearchSourceModel.display_name,
            ResearchSourceModel.source_type,
        ),
    )


class ReadingListService:
    LOOKUP_LIMIT = 100

    # ── Create ────────────────────────────────────────────────────────────────

    @classmethod
    def add_work(
        cls,
        db: Session,
        user_id: uuid.UUID,
        payload: ReadingListItemCreate,
    ) -> tuple[ReadingListItemModel, bool]:
        """
        Saves a work to the user's list. Idempotent: saving a work already on the list returns
        the existing item unchanged, with is_new False.
        """
        exists = db.execute(
            select(ResearchWorkModel.id).where(ResearchWorkModel.id == payload.work_id)
        ).scalar_one_or_none()
        if exists is None:
            raise ValueError(f"Research work with ID '{payload.work_id}' not found.")

        existing = cls._find(db, user_id, payload.work_id)
        if existing is not None:
            return existing, False

        now = datetime.now(timezone.utc)
        item = ReadingListItemModel(
            user_id=user_id,
            work_id=payload.work_id,
            status=payload.status.value,
            notes=payload.notes,
            status_updated_at=now,
            started_at=now if payload.status == ReadingStatus.READING else None,
            finished_at=now if payload.status == ReadingStatus.DONE else None,
            created_at=now,
            updated_at=now,
        )
        db.add(item)
        try:
            db.commit()
        except IntegrityError:
            # A concurrent save of the same work won the unique constraint; return its row.
            db.rollback()
            existing = cls._find(db, user_id, payload.work_id)
            if existing is None:
                raise
            return existing, False
        return cls._find(db, user_id, payload.work_id), True

    # ── Read ──────────────────────────────────────────────────────────────────

    @classmethod
    def list_items(
        cls,
        db: Session,
        user_id: uuid.UUID,
        *,
        status: ReadingStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ReadingListResponse:
        """A page of the user's list, most recently updated first."""
        conditions = [ReadingListItemModel.user_id == user_id]
        if status is not None:
            conditions.append(ReadingListItemModel.status == status.value)

        total = db.execute(
            select(func.count()).select_from(ReadingListItemModel).where(*conditions)
        ).scalar_one()
        items = (
            db.execute(
                select(ReadingListItemModel)
                .options(*_work_options())
                .where(*conditions)
                .order_by(ReadingListItemModel.updated_at.desc(), ReadingListItemModel.id)
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )

        counts = {s.value: 0 for s in ReadingStatus}
        for status_value, count in db.execute(
            select(ReadingListItemModel.status, func.count())
            .where(ReadingListItemModel.user_id == user_id)
            .group_by(ReadingListItemModel.status)
        ).all():
            counts[status_value] = count

        return ReadingListResponse(
            items=[cls.build_item_read(item) for item in items],
            total_count=total,
            limit=limit,
            offset=offset,
            counts_by_status=counts,
        )

    @classmethod
    def get_owned_item(
        cls,
        db: Session,
        user_id: uuid.UUID,
        item_id: uuid.UUID,
    ) -> ReadingListItemModel:
        item = db.execute(
            select(ReadingListItemModel)
            .options(*_work_options())
            .where(ReadingListItemModel.id == item_id)
        ).scalar_one_or_none()
        if item is None:
            raise ValueError(f"Reading list item with ID '{item_id}' not found.")
        if item.user_id != user_id:
            raise PermissionError("Forbidden: this reading list item belongs to another user.")
        return item

    @classmethod
    def lookup(
        cls,
        db: Session,
        user_id: uuid.UUID,
        work_ids: Sequence[uuid.UUID],
    ) -> dict[uuid.UUID, uuid.UUID]:
        """work_id -> item id for the given works the user has saved."""
        if not work_ids:
            return {}
        rows = db.execute(
            select(ReadingListItemModel.work_id, ReadingListItemModel.id).where(
                ReadingListItemModel.user_id == user_id,
                ReadingListItemModel.work_id.in_(list(dict.fromkeys(work_ids))),
            )
        ).all()
        return {work_id: item_id for work_id, item_id in rows}

    # ── Update and delete ─────────────────────────────────────────────────────

    @classmethod
    def update_item(
        cls,
        db: Session,
        user_id: uuid.UUID,
        item_id: uuid.UUID,
        payload: ReadingListItemUpdate,
    ) -> ReadingListItemModel:
        """
        Applies only the fields the caller sent. Entering READING records when reading started
        (once); entering DONE records when it finished, and leaving DONE clears that again.
        """
        item = cls.get_owned_item(db, user_id, item_id)
        sent = payload.model_fields_set
        now = datetime.now(timezone.utc)
        changed = False

        if "status" in sent and payload.status is not None and payload.status.value != item.status:
            target = payload.status
            if target == ReadingStatus.READING and item.started_at is None:
                item.started_at = now
            if target == ReadingStatus.DONE:
                item.finished_at = now
            elif item.status == ReadingStatus.DONE.value:
                item.finished_at = None
            item.status = target.value
            item.status_updated_at = now
            changed = True

        if "notes" in sent and payload.notes != item.notes:
            item.notes = payload.notes
            changed = True

        if changed:
            item.updated_at = now
            db.commit()
        return cls.get_owned_item(db, user_id, item_id)

    @classmethod
    def remove_item(cls, db: Session, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
        item = cls.get_owned_item(db, user_id, item_id)
        db.delete(item)
        db.commit()

    # ── Export ────────────────────────────────────────────────────────────────

    @classmethod
    def export_bibtex(
        cls,
        db: Session,
        user_id: uuid.UUID,
        *,
        item_ids: Sequence[uuid.UUID] | None = None,
        status: ReadingStatus | None = None,
    ) -> str:
        """
        BibTeX for the chosen items, or the whole list (optionally one status). Any id that
        belongs to another user rejects the whole export, so a crafted request cannot pull
        someone else's entries; an unknown id is a 404.
        """
        stmt = select(ReadingListItemModel).options(*_work_options())
        if item_ids is not None:
            wanted = list(dict.fromkeys(item_ids))
            items = db.execute(stmt.where(ReadingListItemModel.id.in_(wanted))).scalars().all()
            if any(item.user_id != user_id for item in items):
                raise PermissionError("Forbidden: the export includes another user's reading list item.")
            found = {item.id for item in items}
            missing = [str(item_id) for item_id in wanted if item_id not in found]
            if missing:
                raise ValueError(f"Reading list item with ID '{missing[0]}' not found.")
            if status is not None:
                items = [item for item in items if item.status == status.value]
        else:
            stmt = stmt.where(ReadingListItemModel.user_id == user_id)
            if status is not None:
                stmt = stmt.where(ReadingListItemModel.status == status.value)
            items = db.execute(stmt).scalars().all()

        return format_entries([item.work for item in items])

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _find(
        db: Session,
        user_id: uuid.UUID,
        work_id: uuid.UUID,
    ) -> ReadingListItemModel | None:
        return db.execute(
            select(ReadingListItemModel)
            .options(*_work_options())
            .where(
                ReadingListItemModel.user_id == user_id,
                ReadingListItemModel.work_id == work_id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def build_item_read(item: ReadingListItemModel) -> ReadingListItemRead:
        work = item.work
        source = work.primary_source
        return ReadingListItemRead(
            id=item.id,
            work_id=item.work_id,
            status=ReadingStatus(item.status),
            notes=item.notes,
            status_updated_at=item.status_updated_at,
            started_at=item.started_at,
            finished_at=item.finished_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
            work=ReadingListWorkSummary(
                id=work.id,
                title=work.title,
                doi=work.doi,
                publication_year=work.publication_year,
                work_type=work.work_type,
                venue_name=source.display_name if source is not None else None,
                authors=ordered_author_names(work),
                landing_page_url=work.landing_page_url,
            ),
        )
