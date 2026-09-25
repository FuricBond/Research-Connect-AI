"""
Deterministic demo-data seeder (Phase 6).

Entry point:
    python -m scripts.seed_demo_data [options]        (run from the backend/ directory)

Options:
    --password TEXT     Password for the seeded demo accounts (default: DemoPass123!)
    --reset             Delete previously seeded demo rows before inserting
    --dry-run           Report what would be created without writing

The repository ships no dataset, so a fresh database has nothing to demonstrate: ranking,
risk and deadline intelligence all need opportunities to operate on, and live scraping needs
network access. This seeder writes a small, fixed corpus through the ORM so a new
environment can be exercised end to end offline.

What it creates (idempotently, keyed on stable demo emails and opportunity titles):
    - Three accounts with bcrypt-hashed passwords and researcher profiles:
      a faculty researcher, a postgraduate student, and an administrator.
    - Explicit preferences for the faculty researcher, so personalization has signal.
    - Twelve opportunities spanning conferences, journals and workshops, with deadlines
      from "already expired" through "months away", including two venues carrying the
      textual markers the Phase 2.6 risk engine flags as predatory.

What it deliberately does not create:
    - Semantic embeddings. Those need `sentence-transformers` and a model download; run
      `python -m ml.embeddings.generate_embeddings` afterwards for vector retrieval.
    - Behavioural interactions or derived personalization state. Those are produced by
      using the application, which is the point of a demo.

Re-running is safe: existing rows are updated in place rather than duplicated.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import sys
import uuid

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _BACKEND_ROOT.parent
for _path in (_PROJECT_ROOT, _BACKEND_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.opportunity import OpportunityModel
from app.models.research_profile import AcademicStatus, ResearchProfileModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.user import UserModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("seed.demo")

DEFAULT_PASSWORD = "DemoPass123!"

# Text the Phase 2.6 heuristic extractors recognize. Kept in one place so it is obvious
# these two venues are deliberately synthetic examples of predatory solicitation.
_PREDATORY_BODY = (
    "Peer review completed within 24 hours and acceptance is guaranteed. "
    "Guaranteed publication upon payment of fee; remit the article charge via Western Union. "
    "Impact factor 9.2 as certified by our own indexing service."
)

DEMO_ACCOUNTS: list[dict] = [
    {
        "email": "demo.faculty@researchconnect.test",
        "full_name": "Dr. Amara Okafor",
        "role": "FACULTY",
        "academic_status": AcademicStatus.FACULTY,
        "institution": "Fairview Institute of Technology",
        "department": "Computer Science",
        "bio": "Faculty researcher working on information retrieval and applied machine learning.",
        "keywords": ["information retrieval", "machine learning", "natural language processing"],
        "target_opportunity_types": ["CONFERENCE", "JOURNAL"],
    },
    {
        "email": "demo.student@researchconnect.test",
        "full_name": "Priya Raghavan",
        "role": "STUDENT",
        "academic_status": AcademicStatus.POSTGRADUATE,
        "institution": "Fairview Institute of Technology",
        "department": "Computer Science",
        "bio": "Postgraduate student preparing a first conference submission.",
        "keywords": ["human-computer interaction", "accessibility"],
        "target_opportunity_types": ["CONFERENCE", "WORKSHOP"],
    },
    {
        "email": "demo.admin@researchconnect.test",
        "full_name": "Sam Whitfield",
        "role": "ADMIN",
        "academic_status": AcademicStatus.RESEARCHER,
        "institution": "Fairview Institute of Technology",
        "department": "Research Office",
        "bio": "Platform administrator.",
        "keywords": [],
        "target_opportunity_types": [],
    },
]

# Preferences for the faculty account so personalization has explicit signal to work with,
# including one exclusion, which exercises the 3-state Preferred/Neutral/Excluded semantics.
DEMO_PREFERENCES: list[dict] = [
    {"category": "RESEARCH_DOMAIN", "preference_value": "information retrieval", "preference_type": "PREFERRED"},
    {"category": "RESEARCH_DOMAIN", "preference_value": "machine learning", "preference_type": "PREFERRED"},
    {"category": "OPPORTUNITY_TYPE", "preference_value": "CONFERENCE", "preference_type": "PREFERRED"},
    {"category": "COUNTRY", "preference_value": "US", "preference_type": "PREFERRED"},
    {"category": "OPPORTUNITY_TYPE", "preference_value": "SPECIAL_ISSUE", "preference_type": "EXCLUDED"},
]

# (title, type, publisher, delivery_mode, location, days_until_deadline, indexing, predatory)
# Negative day offsets are expired on purpose: the deadline engine must classify and exclude
# them, and a demo that only contains healthy future deadlines never shows that.
DEMO_OPPORTUNITIES: list[tuple] = [
    ("International Conference on Information Retrieval Systems", "CONFERENCE",
     "ACM", "HYBRID", "Boston, US", 52, ["Scopus", "DBLP"], False),
    ("Conference on Applied Machine Learning", "CONFERENCE",
     "IEEE", "OFFLINE", "Seattle, US", 28, ["Scopus", "IEEE"], False),
    ("Workshop on Neural Retrieval Methods", "WORKSHOP",
     "ACM", "ONLINE", "Online", 12, ["DBLP"], False),
    ("Symposium on Human-Computer Interaction and Accessibility", "CONFERENCE",
     "ACM", "HYBRID", "Glasgow, UK", 75, ["Scopus", "DBLP"], False),
    ("Journal of Information Retrieval Research", "JOURNAL",
     "Springer", "ONLINE", "Online", 120, ["Scopus", "DOAJ"], False),
    ("Transactions on Applied Machine Intelligence", "JOURNAL",
     "Elsevier", "ONLINE", "Online", 95, ["Scopus"], False),
    ("Workshop on Research Data Management", "WORKSHOP",
     "Springer", "ONLINE", "Online", 5, [], False),
    ("Conference on Natural Language Understanding", "CONFERENCE",
     "ACL", "OFFLINE", "Vienna, AT", 41, ["Scopus", "DBLP", "ACL"], False),
    ("Nordic Conference on Software Engineering Practice", "CONFERENCE",
     "IEEE", "OFFLINE", "Oslo, NO", -9, ["Scopus"], False),
    ("Journal of Computational Science Letters", "JOURNAL",
     "Wiley", "ONLINE", "Online", -21, ["Scopus"], False),
    ("Global Open Journal of Multidisciplinary Advances", "JOURNAL",
     "Global Open Publishing Group", "ONLINE", "Online", 16, [], True),
    ("World Congress on Emerging Interdisciplinary Innovation", "CONFERENCE",
     "World Congress Series", "ONLINE", "Online", 9, [], True),
]

DEMO_EMAILS = tuple(account["email"] for account in DEMO_ACCOUNTS)
DEMO_TITLES = tuple(row[0] for row in DEMO_OPPORTUNITIES)


def _delete_demo_rows(db: Session) -> dict[str, int]:
    """
    Removes previously seeded demo rows, keyed on the demo emails and titles so unrelated
    data is never touched.

    The rows this seeder creates are deleted explicitly, in foreign-key order, rather than
    left to cascade: `ResearchProfileModel` declares no ORM relationship for preferences, so
    cascading them depends on database-level foreign keys, which PostgreSQL enforces but
    SQLite does not by default. Derived personalization state produced by *using* the demo
    (interactions, adaptive signals, calibrations) is left to the database's own cascade.
    """
    users = db.execute(select(UserModel).where(UserModel.email.in_(DEMO_EMAILS))).scalars().all()
    user_ids = [user.id for user in users]

    profiles = (
        db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.user_id.in_(user_ids))
        ).scalars().all()
        if user_ids
        else []
    )
    profile_ids = [profile.id for profile in profiles]

    preferences = (
        db.execute(
            select(ResearcherPreferenceModel).where(
                ResearcherPreferenceModel.profile_id.in_(profile_ids)
            )
        ).scalars().all()
        if profile_ids
        else []
    )

    opportunities = db.execute(
        select(OpportunityModel).where(OpportunityModel.title.in_(DEMO_TITLES))
    ).scalars().all()

    for preference in preferences:
        db.delete(preference)
    for profile in profiles:
        db.delete(profile)
    for user in users:
        db.delete(user)
    for opportunity in opportunities:
        db.delete(opportunity)
    db.commit()
    return {
        "users": len(users),
        "profiles": len(profiles),
        "preferences": len(preferences),
        "opportunities": len(opportunities),
    }


def _seed_accounts(db: Session, password: str, dry_run: bool) -> dict[str, ResearchProfileModel]:
    """Creates or updates the demo accounts and their researcher profiles."""
    hashed = hash_password(password)
    profiles: dict[str, ResearchProfileModel] = {}

    for account in DEMO_ACCOUNTS:
        user = db.execute(
            select(UserModel).where(UserModel.email == account["email"])
        ).scalar_one_or_none()

        if user is None:
            logger.info("creating account %s (%s)", account["email"], account["role"])
            if dry_run:
                continue
            user = UserModel(
                id=uuid.uuid4(),
                email=account["email"],
                hashed_password=hashed,
                full_name=account["full_name"],
                role=account["role"],
                is_active=True,
                is_verified=True,
            )
            db.add(user)
            db.flush()
        else:
            logger.info("updating account %s", account["email"])
            if dry_run:
                continue
            # Reset the password so a re-run always yields known demo credentials.
            user.hashed_password = hashed
            user.full_name = account["full_name"]
            user.role = account["role"]
            user.is_active = True
            user.is_verified = True

        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.user_id == user.id)
        ).scalar_one_or_none()
        if profile is None:
            profile = ResearchProfileModel(id=uuid.uuid4(), user_id=user.id)
            db.add(profile)

        profile.academic_status = account["academic_status"].value
        profile.institution = account["institution"]
        profile.department = account["department"]
        profile.bio = account["bio"]
        profile.keywords = list(account["keywords"])
        profile.target_opportunity_types = list(account["target_opportunity_types"])
        db.flush()
        profiles[account["email"]] = profile

    if not dry_run:
        db.commit()
    return profiles


def _seed_preferences(db: Session, profile: ResearchProfileModel, dry_run: bool) -> int:
    """Declares explicit preferences for a profile, keyed on (category, value)."""
    created = 0
    for pref in DEMO_PREFERENCES:
        existing = db.execute(
            select(ResearcherPreferenceModel).where(
                ResearcherPreferenceModel.profile_id == profile.id,
                ResearcherPreferenceModel.category == pref["category"],
                ResearcherPreferenceModel.preference_value == pref["preference_value"],
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.preference_type = pref["preference_type"]
            existing.is_active = True
            continue
        created += 1
        if dry_run:
            continue
        db.add(
            ResearcherPreferenceModel(
                id=uuid.uuid4(),
                profile_id=profile.id,
                category=pref["category"],
                preference_type=pref["preference_type"],
                preference_key=pref["category"].lower(),
                preference_value=pref["preference_value"],
                display_label=pref["preference_value"],
                strength=0.80,
                confidence=1.00,
                source="EXPLICIT",
                is_active=True,
                provenance={"reasons": ["Seeded demo preference"]},
            )
        )
    if not dry_run:
        db.commit()
    return created


def _seed_opportunities(db: Session, reference_time: datetime, dry_run: bool) -> tuple[int, int]:
    """Creates or updates the demo opportunity corpus. Returns (created, updated)."""
    created = updated = 0
    for (
        title,
        opportunity_type,
        publisher,
        delivery_mode,
        location,
        day_offset,
        indexing,
        predatory,
    ) in DEMO_OPPORTUNITIES:
        deadline = reference_time + timedelta(days=day_offset)
        expired = day_offset < 0
        description = (
            _PREDATORY_BODY
            if predatory
            else (
                f"{title} invites full papers, short papers and posters. Submissions are "
                "peer reviewed by at least three programme committee members."
            )
        )

        opportunity = db.execute(
            select(OpportunityModel).where(OpportunityModel.title == title)
        ).scalar_one_or_none()

        if opportunity is None:
            created += 1
            logger.info("creating opportunity %s", title)
            if dry_run:
                continue
            opportunity = OpportunityModel(id=uuid.uuid4(), title=title)
            db.add(opportunity)
        else:
            updated += 1
            logger.info("updating opportunity %s", title)
            if dry_run:
                continue

        opportunity.opportunity_type = opportunity_type
        opportunity.publisher = publisher
        opportunity.organizer = publisher
        opportunity.delivery_mode = delivery_mode
        opportunity.location = location
        opportunity.summary = f"{opportunity_type.title()} hosted by {publisher}."
        opportunity.description = description
        opportunity.website_url = "https://example.test/" + title.lower().replace(" ", "-")[:80]
        opportunity.submission_url = opportunity.website_url + "/submit"
        opportunity.submission_deadline = deadline
        opportunity.notification_date = deadline + timedelta(days=30)
        opportunity.camera_ready_deadline = deadline + timedelta(days=52)
        opportunity.event_start_date = (deadline + timedelta(days=90)).date()
        opportunity.event_end_date = (deadline + timedelta(days=93)).date()
        opportunity.indexing = list(indexing)
        opportunity.is_predatory_flag = predatory
        opportunity.status = "EXPIRED" if expired else "ACTIVE"
        opportunity.last_seen_at = reference_time

    if not dry_run:
        db.commit()
    return created, updated


REQUIRED_TABLES = ("users", "research_profiles", "researcher_preferences", "opportunities")


def verify_schema(db: Session) -> list[str]:
    """
    Returns the required tables that do not exist.

    Seeding an unmigrated database otherwise fails with a raw driver traceback, which is an
    unhelpful first experience for the one script whose job is to make setup easy.
    """
    from sqlalchemy import inspect

    inspector = inspect(db.get_bind())
    return [table for table in REQUIRED_TABLES if not inspector.has_table(table)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a deterministic demo dataset.")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password for demo accounts")
    parser.add_argument("--reset", action="store_true", help="Delete seeded demo rows first")
    parser.add_argument("--dry-run", action="store_true", help="Report actions without writing")
    args = parser.parse_args()

    reference_time = datetime.now(timezone.utc)

    with SessionLocal() as db:
        missing = verify_schema(db)
        if missing:
            logger.error(
                "database schema is missing: %s. Run `alembic upgrade head` first.",
                ", ".join(missing),
            )
            return 1

        if args.reset:
            if args.dry_run:
                logger.info("--dry-run: skipping reset")
            else:
                removed = _delete_demo_rows(db)
                logger.info(
                    "reset removed %d accounts and %d opportunities",
                    removed["users"],
                    removed["opportunities"],
                )

        profiles = _seed_accounts(db, args.password, args.dry_run)
        opp_created, opp_updated = _seed_opportunities(db, reference_time, args.dry_run)

        pref_created = 0
        faculty_profile = profiles.get("demo.faculty@researchconnect.test")
        if faculty_profile is not None:
            pref_created = _seed_preferences(db, faculty_profile, args.dry_run)
        elif not args.dry_run:
            logger.warning("faculty profile missing; skipped preference seeding")

    logger.info(
        "seed complete: %d accounts, %d preferences created, %d opportunities created, %d updated%s",
        len(profiles),
        pref_created,
        opp_created,
        opp_updated,
        " (dry run, nothing written)" if args.dry_run else "",
    )
    if not args.dry_run:
        logger.info("demo sign-in: %s / %s", DEMO_ACCOUNTS[0]["email"], args.password)
        logger.info(
            "next steps: POST /api/v1/auth/login to obtain a token; run "
            "`python -m ml.embeddings.generate_embeddings` for vector retrieval"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
