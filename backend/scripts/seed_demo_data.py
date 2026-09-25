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
    - Three faculty-authored research postings (Phase 5.10/5.11): a published project, a
      published research assistantship that accepts applications on the platform, and a
      draft, so both the discovery and authoring views have something to show.
    - Peer discoverability for the faculty and student accounts (Phase 5.12), with
      complementary expertise topics so peer matching returns an explainable result.

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
from app.models.research_posting import (
    PostingStatus,
    PostingType,
    PostingWorkMode,
    ResearchPostingModel,
)
from app.models.research_profile import AcademicStatus, ResearchProfileModel
from app.models.researcher_discovery import (
    CollaborationInterest,
    CollaborationStatus,
    ResearcherDiscoverySettingsModel,
)
from app.models.researcher_interest import ResearcherInterestModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.topic import TopicModel
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

# (title, type, status, days_until_deadline, accepts_applications, terms)
# One of each shape a reviewer would want to see: a published supervisor-led project, a funded
# opening that accepts applications on-platform, and an unpublished draft.
DEMO_POSTINGS: list[dict] = [
    {
        "title": "Doctoral project on neural retrieval evaluation",
        "posting_type": PostingType.PROJECT,
        "status": PostingStatus.OPEN,
        "days_until_deadline": 45,
        "summary": "Supervised doctoral work on how retrieval systems should be evaluated.",
        "description": (
            "We are looking for a doctoral researcher to study evaluation methodology for dense "
            "retrieval systems, including offline metrics and their correlation with user outcomes."
        ),
        "required_skills": ["Python", "Information Retrieval", "Statistics"],
        "work_mode": PostingWorkMode.HYBRID,
        "positions": 1,
        "accepts_applications": False,
    },
    {
        "title": "Research assistantship in retrieval benchmarking",
        "posting_type": PostingType.RESEARCH_ASSISTANTSHIP,
        "status": PostingStatus.OPEN,
        "days_until_deadline": 21,
        "summary": "Part-time funded assistantship building and running retrieval benchmarks.",
        "description": (
            "A funded research assistantship supporting our benchmarking infrastructure. You will "
            "build reproducible evaluation pipelines and help analyse the results."
        ),
        "required_skills": ["Python", "Data Analysis"],
        "work_mode": PostingWorkMode.ONSITE,
        "positions": 2,
        "accepts_applications": True,
        "compensation_type": "STIPEND",
        "compensation_amount": 2200,
        "compensation_currency": "USD",
        "compensation_period": "MONTH",
        "commitment_type": "PART_TIME",
        "hours_per_week": 20,
        "duration_months": 12,
        "eligibility": "Enrolled in a postgraduate programme at the time of appointment.",
    },
    {
        "title": "Thesis topic on query understanding for low-resource languages",
        "posting_type": PostingType.THESIS_TOPIC,
        "status": PostingStatus.DRAFT,
        "days_until_deadline": 90,
        "summary": "An available thesis topic, still being drafted.",
        "description": (
            "A proposed thesis topic investigating query understanding where training data is "
            "scarce. Scope and supervision arrangements are still being finalised."
        ),
        "required_skills": ["Natural Language Processing"],
        "work_mode": PostingWorkMode.REMOTE,
        "positions": 1,
        "accepts_applications": False,
    },
]

# Expertise topics per demo account. Deliberately overlapping in one area and divergent
# elsewhere, so Phase 5.12 has both shared and complementary signal to report rather than
# returning a near-identical profile or an unrelated stranger.
DEMO_TOPIC_TREE: dict[str, str | None] = {
    "information-retrieval": None,
    "dense-retrieval": "information-retrieval",
    "query-understanding": "information-retrieval",
    "retrieval-evaluation": "information-retrieval",
    "human-computer-interaction": None,
    "accessibility": "human-computer-interaction",
}

DEMO_EXPERTISE: dict[str, dict[str, float]] = {
    "demo.faculty@researchconnect.test": {
        "dense-retrieval": 0.92,
        "retrieval-evaluation": 0.85,
    },
    "demo.student@researchconnect.test": {
        "retrieval-evaluation": 0.55,
        "query-understanding": 0.70,
        "accessibility": 0.65,
    },
}

DEMO_DISCOVERY: dict[str, dict] = {
    "demo.faculty@researchconnect.test": {
        "collaboration_status": CollaborationStatus.SEEKING_COLLABORATORS,
        "collaboration_interests": [
            CollaborationInterest.CO_AUTHORSHIP,
            CollaborationInterest.JOINT_GRANT,
            CollaborationInterest.STUDENT_CO_SUPERVISION,
        ],
        "show_institution": True,
        "show_contact_email": False,
        "collaboration_note": "Interested in co-authoring on retrieval evaluation methodology.",
    },
    "demo.student@researchconnect.test": {
        "collaboration_status": CollaborationStatus.OPEN_TO_ENQUIRIES,
        "collaboration_interests": [
            CollaborationInterest.CO_AUTHORSHIP,
            CollaborationInterest.METHOD_EXCHANGE,
        ],
        "show_institution": True,
        "show_contact_email": False,
        "collaboration_note": "Looking for a first co-authorship in query understanding.",
    },
}

DEMO_EMAILS = tuple(account["email"] for account in DEMO_ACCOUNTS)
DEMO_TITLES = tuple(row[0] for row in DEMO_OPPORTUNITIES)
DEMO_POSTING_TITLES = tuple(row["title"] for row in DEMO_POSTINGS)


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

    postings = db.execute(
        select(ResearchPostingModel).where(ResearchPostingModel.title.in_(DEMO_POSTING_TITLES))
    ).scalars().all()

    interests = (
        db.execute(
            select(ResearcherInterestModel).where(
                ResearcherInterestModel.profile_id.in_(profile_ids),
                ResearcherInterestModel.source == "SEED_DEMO",
            )
        ).scalars().all()
        if profile_ids
        else []
    )

    discovery = (
        db.execute(
            select(ResearcherDiscoverySettingsModel).where(
                ResearcherDiscoverySettingsModel.profile_id.in_(profile_ids)
            )
        ).scalars().all()
        if profile_ids
        else []
    )

    for posting in postings:
        db.delete(posting)
    for interest in interests:
        db.delete(interest)
    for setting in discovery:
        db.delete(setting)
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
        "postings": len(postings),
        "interests": len(interests),
        "discovery_settings": len(discovery),
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


def _seed_topics(db: Session, dry_run: bool) -> int:
    """Ensures the demo taxonomy exists, creating parents before children."""
    created = 0
    # Roots first, so a child's parent_id can always be resolved in one pass.
    for slug in sorted(DEMO_TOPIC_TREE, key=lambda s: (DEMO_TOPIC_TREE[s] is not None, s)):
        parent_slug = DEMO_TOPIC_TREE[slug]
        existing = db.execute(select(TopicModel).where(TopicModel.slug == slug)).scalar_one_or_none()
        if existing is not None:
            continue
        created += 1
        if dry_run:
            continue
        parent_id = None
        if parent_slug:
            parent = db.execute(
                select(TopicModel).where(TopicModel.slug == parent_slug)
            ).scalar_one_or_none()
            parent_id = parent.id if parent else None
        db.add(
            TopicModel(
                id=uuid.uuid4(),
                name=slug.replace("-", " ").title(),
                slug=slug,
                parent_id=parent_id,
            )
        )
        db.flush()
    if not dry_run:
        db.commit()
    return created


def _seed_expertise(
    db: Session,
    profiles: dict[str, ResearchProfileModel],
    dry_run: bool,
) -> int:
    """Records expertise topics so Phase 5.12 peer matching has something to compare."""
    created = 0
    for email, topics in DEMO_EXPERTISE.items():
        profile = profiles.get(email)
        if profile is None:
            continue
        for slug, strength in topics.items():
            topic = db.execute(
                select(TopicModel).where(TopicModel.slug == slug)
            ).scalar_one_or_none()
            if topic is None:
                continue
            existing = db.execute(
                select(ResearcherInterestModel).where(
                    ResearcherInterestModel.profile_id == profile.id,
                    ResearcherInterestModel.topic_slug == slug,
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.strength = strength
                continue
            created += 1
            if dry_run:
                continue
            db.add(
                ResearcherInterestModel(
                    id=uuid.uuid4(),
                    profile_id=profile.id,
                    topic_id=topic.id,
                    topic_name=topic.name,
                    topic_slug=slug,
                    strength=strength,
                    confidence=0.90,
                    evidence_count=4,
                    # Strong topics read as expertise; the weaker one as an emerging interest,
                    # which is what the matcher's strength thresholds are there to distinguish.
                    classification=(
                        "PRIMARY_EXPERTISE" if strength >= 0.65 else "EMERGING_INTEREST"
                    ),
                    is_primary_expertise=strength >= 0.65,
                    source="SEED_DEMO",
                    provenance={"reasons": ["Seeded demo expertise"]},
                )
            )
    if not dry_run:
        db.commit()
    return created


def _seed_discovery_settings(
    db: Session,
    profiles: dict[str, ResearchProfileModel],
    reference_time: datetime,
    dry_run: bool,
) -> int:
    """
    Opts the demo researchers into peer discovery.

    Consent is explicit in the product, and it is explicit here too: the seeder is standing in
    for two researchers who chose to be findable, and the consent timestamp is recorded as such.
    """
    created = 0
    for email, spec in DEMO_DISCOVERY.items():
        profile = profiles.get(email)
        if profile is None:
            continue
        existing = db.execute(
            select(ResearcherDiscoverySettingsModel).where(
                ResearcherDiscoverySettingsModel.profile_id == profile.id
            )
        ).scalar_one_or_none()
        if existing is None:
            created += 1
            if dry_run:
                continue
            existing = ResearcherDiscoverySettingsModel(id=uuid.uuid4(), profile_id=profile.id)
            db.add(existing)
        elif dry_run:
            continue

        existing.is_discoverable = True
        existing.collaboration_status = spec["collaboration_status"].value
        existing.collaboration_interests = [i.value for i in spec["collaboration_interests"]]
        existing.show_institution = spec["show_institution"]
        existing.show_contact_email = spec["show_contact_email"]
        existing.collaboration_note = spec["collaboration_note"]
        existing.consent_updated_at = reference_time
    if not dry_run:
        db.commit()
    return created


def _seed_postings(
    db: Session,
    author_profile: ResearchProfileModel | None,
    reference_time: datetime,
    dry_run: bool,
) -> tuple[int, int]:
    """Creates the demo research postings authored by the faculty account."""
    if author_profile is None:
        return 0, 0

    created = updated = 0
    for spec in DEMO_POSTINGS:
        posting = db.execute(
            select(ResearchPostingModel).where(ResearchPostingModel.title == spec["title"])
        ).scalar_one_or_none()

        if posting is None:
            created += 1
            logger.info("creating posting %s", spec["title"])
            if dry_run:
                continue
            posting = ResearchPostingModel(
                id=uuid.uuid4(),
                title=spec["title"],
                author_profile_id=author_profile.id,
                author_user_id=author_profile.user_id,
            )
            db.add(posting)
        else:
            updated += 1
            logger.info("updating posting %s", spec["title"])
            if dry_run:
                continue

        status_value = spec["status"]
        posting.posting_type = spec["posting_type"].value
        posting.status = status_value.value
        posting.summary = spec["summary"]
        posting.description = spec["description"]
        posting.required_skills = list(spec["required_skills"])
        posting.institution = author_profile.institution
        posting.department = author_profile.department
        posting.location = "Fairview, US"
        posting.country = "US"
        posting.work_mode = spec["work_mode"].value
        posting.positions_available = spec["positions"]
        posting.application_deadline = reference_time + timedelta(days=spec["days_until_deadline"])
        posting.expected_start_date = (reference_time + timedelta(days=120)).date()
        posting.contact_email = "demo.faculty@researchconnect.test"
        posting.accepts_applications = spec["accepts_applications"]
        posting.compensation_type = spec.get("compensation_type", "UNSPECIFIED")
        posting.compensation_amount = spec.get("compensation_amount")
        posting.compensation_currency = spec.get("compensation_currency")
        posting.compensation_period = spec.get("compensation_period")
        posting.commitment_type = spec.get("commitment_type")
        posting.hours_per_week = spec.get("hours_per_week")
        posting.duration_months = spec.get("duration_months")
        posting.eligibility_requirements = spec.get("eligibility")
        # Published postings need a publication timestamp, since the lifecycle treats it as a
        # first-publication fact rather than something recomputed on read.
        if status_value == PostingStatus.OPEN and posting.published_at is None:
            posting.published_at = reference_time

    if not dry_run:
        db.commit()
    return created, updated


REQUIRED_TABLES = (
    "users",
    "research_profiles",
    "researcher_preferences",
    "opportunities",
    "research_postings",
    "researcher_discovery_settings",
)


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

        # Phase 5.10-5.12 surfaces
        _seed_topics(db, args.dry_run)
        expertise_created = _seed_expertise(db, profiles, args.dry_run)
        discovery_created = _seed_discovery_settings(db, profiles, reference_time, args.dry_run)
        posting_created, posting_updated = _seed_postings(
            db, faculty_profile, reference_time, args.dry_run
        )

    logger.info(
        "seed complete: %d accounts, %d preferences, %d expertise topics, %d discovery opt-ins, "
        "%d opportunities created (%d updated), %d postings created (%d updated)%s",
        len(profiles),
        pref_created,
        expertise_created,
        discovery_created,
        opp_created,
        opp_updated,
        posting_created,
        posting_updated,
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
