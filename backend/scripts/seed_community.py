"""
Community seeder: a realistic population of researchers around the demo accounts.

Entry point (run from the backend/ directory):
    python -m scripts.seed_community --password TEXT    add the community (safe to re-run)
    python -m scripts.seed_community --remove           delete everything this script added

The demo seeder gives a reviewer three accounts to sign in as, but a platform with three
members does not look like one in use: peer discovery finds almost nobody, postings have no
applicants and the administration list is nearly empty. This script adds sixty researchers,
15 faculty and 45 students at five universities, and has them use the platform the way
people do, through the same services the API calls:

    - researcher profiles, expertise drawn from the topic taxonomy and a few explicit
      preferences;
    - peer-discovery opt-ins: most people are findable, and contact emails stay hidden;
    - research postings by the faculty: mostly open, some closed or filled, a few drafts;
    - applications from students at every stage of review, with the status history and the
      notifications the application service records. The demo faculty's open assistantship
      receives a few applications that are left for the demo to review.

Everyone here is fictional: the names are made up, the universities do not exist, and the
addresses are never contacted (the platform sends no email). Postings carry no external
links. Accounts are recognised by the ID this script gave them, as the demo seeder does
(Phase 6.4 audit P2-1), so an account someone registered with one of these emails is never
adopted, changed or removed.

Re-running is safe: people, postings and applications that exist are kept and anything
missing is added; the randomness is seeded, so every run makes the same choices. A re-run
also sets the given password on the community accounts.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import logging
from pathlib import Path
import random
import sys
import unicodedata
import uuid

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _BACKEND_ROOT.parent
for _path in (_PROJECT_ROOT, _BACKEND_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.research_posting import PostingStatus, PostingType, PostingWorkMode, ResearchPostingModel
from app.models.research_posting_application import (
    ApplicationStatus,
    CommitmentType,
    CompensationType,
    ResearchPostingApplicationModel,
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
from app.schemas.auth import RegisterRequest
from app.schemas.research_posting import ResearchPostingCreate
from app.schemas.research_posting_application import ApplicationCreate, OpeningTermsUpdate
from app.services.research_posting_application_service import (
    ApplicationNotAcceptedError,
    DuplicateApplicationError,
    ResearchPostingApplicationService,
)
from app.services.research_posting_service import ResearchPostingService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("seed.community")

# The demo seeder's public password; refused here too when APP_ENV=production.
_PUBLIC_DEMO_PASSWORD = "DemoPass123!"
_SEED = 20260928
_INTEREST_SOURCE = "SEED_COMMUNITY"
DEMO_ASSISTANTSHIP_TITLE = "Research assistantship in retrieval benchmarking"

# (name, email domain, posting location, ISO country). All made up.
INSTITUTIONS: dict[str, tuple[str, str, str, str]] = {
    "fairview": ("Fairview Institute of Technology", "fairviewtech.edu", "Fairview, US", "US"),
    "northgate": ("Northgate University", "northgate.edu", "Leeds, GB", "GB"),
    "lakeshore": ("Lakeshore Institute of Science", "lakeshore-science.edu", "Toronto, CA", "CA"),
    "kaveri": ("Kaveri Institute of Technology", "kaveritech.edu", "Bengaluru, IN", "IN"),
    "crestwood": ("Crestwood University", "crestwood.edu", "Melbourne, AU", "AU"),
}


@dataclass(frozen=True)
class Area:
    label: str
    keywords: tuple[str, str, str]
    topics: dict[str, float]


# Research areas, with expertise topics from the taxonomy the corpus is tagged with.
AREAS: dict[str, Area] = {
    "retrieval": Area(
        "information retrieval",
        ("information retrieval", "question answering", "search evaluation"),
        {"information-retrieval": 0.90, "question-answering": 0.72, "natural-language-processing": 0.50},
    ),
    "nlp": Area(
        "natural language processing",
        ("natural language processing", "large language models", "machine translation"),
        {"natural-language-processing": 0.90, "large-language-models": 0.80, "machine-translation": 0.60},
    ),
    "vision": Area(
        "computer vision",
        ("computer vision", "object detection", "medical imaging"),
        {"computer-vision": 0.90, "object-detection": 0.75, "image-segmentation": 0.70, "medical-imaging": 0.50},
    ),
    "hci": Area(
        "human-computer interaction",
        ("human-computer interaction", "accessibility", "educational technology"),
        {"human-computer-interaction": 0.90, "accessibility": 0.70, "educational-technology": 0.60},
    ),
    "systems": Area(
        "distributed systems",
        ("distributed systems", "cloud computing", "databases"),
        {"distributed-systems": 0.90, "cloud-computing": 0.75, "databases": 0.65},
    ),
    "security": Area(
        "cybersecurity",
        ("cybersecurity", "network security", "privacy"),
        {"cybersecurity": 0.90, "computer-networks": 0.70, "machine-learning": 0.45},
    ),
    "se": Area(
        "software engineering",
        ("software engineering", "program analysis", "code generation"),
        {"software-engineering": 0.90, "compiler-design": 0.60, "large-language-models": 0.45},
    ),
    "ml": Area(
        "machine learning",
        ("machine learning", "reinforcement learning", "graph neural networks"),
        {"machine-learning": 0.90, "reinforcement-learning": 0.75, "graph-neural-networks": 0.65, "deep-learning": 0.70},
    ),
    "data": Area(
        "data mining",
        ("data mining", "data science", "social network analysis"),
        {"data-mining": 0.85, "data-science": 0.80, "social-networks": 0.60},
    ),
}

# (full name without title, institution, area, department, rank)
FACULTY: list[tuple[str, str, str, str, str]] = [
    ("Rohan Mehta", "kaveri", "retrieval", "Computer Science and Engineering", "Associate Professor"),
    ("Aisha Rahman", "kaveri", "data", "Data Science", "Assistant Professor"),
    ("Arjun Nair", "kaveri", "security", "Computer Science and Engineering", "Professor"),
    ("Elena Vasquez", "northgate", "nlp", "School of Computing", "Senior Lecturer"),
    ("Marco Bellini", "northgate", "systems", "School of Computing", "Professor"),
    ("Fatima Al-Sayed", "northgate", "data", "School of Computing", "Lecturer"),
    ("Kwame Mensah", "lakeshore", "vision", "Computer Science", "Associate Professor"),
    ("Sofia Novak", "lakeshore", "security", "Information Systems", "Assistant Professor"),
    ("Tomas Herrera", "lakeshore", "ml", "Computer Science", "Professor"),
    ("Hannah Lindqvist", "crestwood", "hci", "Human-Centred Computing", "Senior Lecturer"),
    ("Daniel Okoye", "crestwood", "se", "Software Engineering", "Associate Professor"),
    ("Yuki Tanaka", "crestwood", "vision", "Computer Science", "Lecturer"),
    ("Wei Zhang", "fairview", "ml", "Computer Science", "Associate Professor"),
    ("Meera Iyer", "fairview", "nlp", "Computer Science", "Assistant Professor"),
    ("Grace Whitmore", "fairview", "hci", "Human-Computer Interaction", "Professor"),
]

# (full name, institution, area, academic status)
STUDENTS: list[tuple[str, str, str, AcademicStatus]] = [
    ("Aditi Kulkarni", "kaveri", "retrieval", AcademicStatus.PHD),
    ("Rahul Verma", "kaveri", "security", AcademicStatus.POSTGRADUATE),
    ("Sneha Pillai", "kaveri", "data", AcademicStatus.POSTGRADUATE),
    ("Karthik Subramanian", "kaveri", "retrieval", AcademicStatus.POSTGRADUATE),
    ("Ananya Das", "kaveri", "nlp", AcademicStatus.UNDERGRADUATE),
    ("Vikram Joshi", "kaveri", "security", AcademicStatus.PHD),
    ("Nikhil Rao", "kaveri", "ml", AcademicStatus.UNDERGRADUATE),
    ("Divya Menon", "kaveri", "data", AcademicStatus.PHD),
    ("Ishaan Chopra", "kaveri", "vision", AcademicStatus.POSTGRADUATE),
    ("Oliver Bennett", "northgate", "nlp", AcademicStatus.PHD),
    ("Chloe Hughes", "northgate", "systems", AcademicStatus.POSTGRADUATE),
    ("Amir Hassan", "northgate", "nlp", AcademicStatus.POSTGRADUATE),
    ("Isla Morrison", "northgate", "data", AcademicStatus.UNDERGRADUATE),
    ("Jacob Clarke", "northgate", "systems", AcademicStatus.PHD),
    ("Zara Ahmed", "northgate", "data", AcademicStatus.POSTGRADUATE),
    ("Ethan Walsh", "northgate", "se", AcademicStatus.UNDERGRADUATE),
    ("Lucy Fernandes", "northgate", "nlp", AcademicStatus.POSTGRADUATE),
    ("Samuel Adeyemi", "northgate", "systems", AcademicStatus.POSTGRADUATE),
    ("Liam Tremblay", "lakeshore", "vision", AcademicStatus.PHD),
    ("Maya Singh", "lakeshore", "ml", AcademicStatus.POSTGRADUATE),
    ("Noah Chen", "lakeshore", "ml", AcademicStatus.PHD),
    ("Ava Robinson", "lakeshore", "security", AcademicStatus.UNDERGRADUATE),
    ("Gabriel Lefebvre", "lakeshore", "vision", AcademicStatus.POSTGRADUATE),
    ("Emma Nguyen", "lakeshore", "security", AcademicStatus.POSTGRADUATE),
    ("Lucas Martin", "lakeshore", "ml", AcademicStatus.UNDERGRADUATE),
    ("Sara Haddad", "lakeshore", "vision", AcademicStatus.POSTGRADUATE),
    ("Benjamin Park", "lakeshore", "retrieval", AcademicStatus.POSTGRADUATE),
    ("Charlotte Evans", "crestwood", "hci", AcademicStatus.PHD),
    ("Jack Donovan", "crestwood", "se", AcademicStatus.POSTGRADUATE),
    ("Mia Kowalski", "crestwood", "hci", AcademicStatus.POSTGRADUATE),
    ("Ruby Thompson", "crestwood", "vision", AcademicStatus.UNDERGRADUATE),
    ("Aarav Patel", "crestwood", "se", AcademicStatus.PHD),
    ("Grace Liu", "crestwood", "vision", AcademicStatus.POSTGRADUATE),
    ("Henry Ashford", "crestwood", "hci", AcademicStatus.UNDERGRADUATE),
    ("Olivia Martins", "crestwood", "se", AcademicStatus.POSTGRADUATE),
    ("Luca Romano", "crestwood", "ml", AcademicStatus.POSTGRADUATE),
    ("Daniel Kim", "fairview", "ml", AcademicStatus.PHD),
    ("Sophia Garcia", "fairview", "hci", AcademicStatus.POSTGRADUATE),
    ("Michael Brennan", "fairview", "retrieval", AcademicStatus.POSTGRADUATE),
    ("Jamal Carter", "fairview", "nlp", AcademicStatus.PHD),
    ("Natalia Petrova", "fairview", "retrieval", AcademicStatus.PHD),
    ("Ryan Doyle", "fairview", "hci", AcademicStatus.UNDERGRADUATE),
    ("Hana Yamamoto", "fairview", "nlp", AcademicStatus.POSTGRADUATE),
    ("Carlos Mendoza", "fairview", "ml", AcademicStatus.POSTGRADUATE),
    ("Priyanka Shah", "fairview", "retrieval", AcademicStatus.UNDERGRADUATE),
]


@dataclass(frozen=True)
class PostingSpec:
    author: str
    title: str
    posting_type: PostingType
    final_status: PostingStatus
    published_days_ago: int
    days_until_deadline: int
    summary: str
    description: str
    skills: tuple[str, ...]
    work_mode: PostingWorkMode = PostingWorkMode.ONSITE
    positions: int = 1
    # (compensation type, amount, currency, period, commitment, hours/week, months)
    terms: tuple | None = None


_RA = PostingType.RESEARCH_ASSISTANTSHIP
_OPEN = PostingStatus.OPEN

POSTINGS: list[PostingSpec] = [
    PostingSpec("Rohan Mehta", "Research assistantship: evaluating retrieval-augmented generation", _RA, _OPEN, 12, 30,
                "Part-time assistantship measuring how well retrieval-augmented systems ground their answers.",
                "Join a small team building evaluation suites for retrieval-augmented generation. You will "
                "collect question sets, run retrieval and generation baselines, and analyse where answers "
                "drift from their sources.", ("Python", "Information Retrieval", "Evaluation"),
                PostingWorkMode.HYBRID, 2, (CompensationType.STIPEND, 25000, "INR", "MONTH", CommitmentType.PART_TIME, 20, 6)),
    PostingSpec("Rohan Mehta", "Doctoral project: conversational search for low-resource languages", PostingType.PROJECT, _OPEN, 30, 60,
                "Fully supervised doctoral project on conversational search beyond English.",
                "A doctoral project on conversational search for languages with little training data, "
                "combining cross-lingual retrieval with user studies in Kannada and Tamil.",
                ("Information Retrieval", "NLP", "Python")),
    PostingSpec("Aisha Rahman", "Summer internship: mining open health-policy datasets", PostingType.INTERNSHIP, _OPEN, 8, 25,
                "Ten-week internship analysing open public-health datasets.",
                "Interns will clean and link open health-policy datasets, build exploratory dashboards and "
                "help write a short data paper describing the resulting corpus.",
                ("Python", "Pandas", "Data Visualisation"), PostingWorkMode.ONSITE, 3,
                (CompensationType.STIPEND, 15000, "INR", "MONTH", CommitmentType.FULL_TIME, 40, 3)),
    PostingSpec("Arjun Nair", "Thesis topic: detecting phishing campaigns with graph learning", PostingType.THESIS_TOPIC, _OPEN, 20, 75,
                "Master's thesis topic on graph-based phishing detection.",
                "Model email and domain-registration activity as a graph and study whether graph neural "
                "networks detect coordinated phishing campaigns earlier than content filters.",
                ("Cybersecurity", "Graph Neural Networks")),
    PostingSpec("Elena Vasquez", "Postdoctoral fellow in multilingual language models", PostingType.POSTDOC, _OPEN, 18, 45,
                "Two-year postdoctoral fellowship on multilingual and low-resource language models.",
                "The fellow will lead work on evaluating and adapting large language models for "
                "under-resourced languages, supervise two PhD students and publish at ACL venues.",
                ("NLP", "Large Language Models", "PyTorch"), PostingWorkMode.HYBRID, 1,
                (CompensationType.SALARY, 42000, "GBP", "YEAR", CommitmentType.FULL_TIME, 37, 24)),
    PostingSpec("Elena Vasquez", "Research assistantship: annotation study for clinical text", _RA, PostingStatus.FILLED, 40, 20,
                "Part-time assistantship coordinating an annotation study on clinical notes.",
                "Coordinate a team of annotators labelling de-identified clinical notes, measure agreement "
                "and help train baseline extraction models.", ("Annotation", "NLP", "Statistics"),
                PostingWorkMode.ONSITE, 1, (CompensationType.STIPEND, 1400, "GBP", "MONTH", CommitmentType.PART_TIME, 15, 9)),
    PostingSpec("Marco Bellini", "Doctoral project: energy-aware scheduling for serverless platforms", PostingType.PROJECT, _OPEN, 25, 50,
                "Doctoral project on reducing the energy footprint of serverless workloads.",
                "Design and evaluate schedulers that trade latency for energy on serverless platforms, "
                "using traces from a university cloud and an open benchmark suite.",
                ("Distributed Systems", "Go", "Performance Analysis")),
    PostingSpec("Fatima Al-Sayed", "Collaboration: shared benchmark for fairness in recommender data", PostingType.COLLABORATION, _OPEN, 15, 90,
                "Looking for partner groups to co-build a fairness benchmark for recommender systems.",
                "We are assembling a shared benchmark of recommender datasets annotated for exposure and "
                "fairness, and invite groups with complementary data or evaluation expertise to join.",
                ("Recommender Systems", "Data Mining"), PostingWorkMode.REMOTE),
    PostingSpec("Kwame Mensah", "Research assistantship: dataset curation for agricultural drone imagery", _RA, _OPEN, 10, 20,
                "Assistantship curating and labelling drone imagery of crop fields.",
                "Help curate a public dataset of drone images of smallholder farms: plan labelling "
                "guidelines, manage annotators and train baseline segmentation models.",
                ("Computer Vision", "Python", "Annotation"), PostingWorkMode.ONSITE, 2,
                (CompensationType.STIPEND, 2200, "CAD", "MONTH", CommitmentType.PART_TIME, 20, 8)),
    PostingSpec("Kwame Mensah", "Lab rotation: 3D scene understanding", PostingType.LAB_ROTATION, _OPEN, 22, 35,
                "Eight-week lab rotation for first-year PhD students.",
                "Rotating students will reproduce a recent 3D scene understanding paper and extend it with "
                "a small experiment of their own, presented at the group seminar.",
                ("Computer Vision", "PyTorch")),
    PostingSpec("Sofia Novak", "Internship: privacy auditing of mobile health apps", PostingType.INTERNSHIP, _OPEN, 9, 28,
                "Four-month internship auditing data flows in mobile health apps.",
                "Interns will instrument popular mobile health apps, trace where personal data is sent and "
                "compare the findings with each app's privacy policy.",
                ("Cybersecurity", "Android", "Network Analysis"), PostingWorkMode.HYBRID, 2,
                (CompensationType.STIPEND, 3200, "CAD", "MONTH", CommitmentType.FULL_TIME, 37, 4)),
    PostingSpec("Tomas Herrera", "Postdoc in reinforcement learning for robotics", PostingType.POSTDOC, PostingStatus.CLOSED, 35, 30,
                "Postdoctoral position on sample-efficient reinforcement learning for manipulation.",
                "Develop sample-efficient reinforcement learning methods for robotic manipulation and "
                "validate them on the lab's robot arms.", ("Reinforcement Learning", "Robotics", "PyTorch"),
                PostingWorkMode.ONSITE, 1, (CompensationType.SALARY, 68000, "CAD", "YEAR", CommitmentType.FULL_TIME, 40, 24)),
    PostingSpec("Hannah Lindqvist", "Research assistantship: accessible interfaces for older adults", _RA, _OPEN, 14, 18,
                "Part-time assistantship running co-design sessions with older adults.",
                "Run co-design workshops with older adults, prototype accessible interfaces and help analyse "
                "interview data for a journal article.", ("User Research", "Accessibility", "Prototyping"),
                PostingWorkMode.ONSITE, 1, (CompensationType.STIPEND, 2600, "AUD", "MONTH", CommitmentType.PART_TIME, 16, 10)),
    PostingSpec("Hannah Lindqvist", "Thesis topic: evaluating voice assistants with blind users", PostingType.THESIS_TOPIC, _OPEN, 28, 80,
                "Honours or master's thesis on voice assistant accessibility.",
                "Design and run a study of how blind users complete everyday tasks with voice assistants, "
                "and propose design guidelines from the findings.", ("HCI", "User Studies")),
    PostingSpec("Daniel Okoye", "Internship: LLM-assisted code review tooling", PostingType.INTERNSHIP, _OPEN, 6, 22,
                "Twelve-week internship building code review assistants.",
                "Build and evaluate tools that use language models to summarise pull requests and flag "
                "risky changes, measured on open-source repositories.",
                ("Python", "Software Engineering", "Large Language Models"), PostingWorkMode.REMOTE, 2,
                (CompensationType.STIPEND, 4200, "AUD", "MONTH", CommitmentType.FULL_TIME, 38, 3)),
    PostingSpec("Yuki Tanaka", "Doctoral project: self-supervised learning for medical image segmentation", PostingType.PROJECT, _OPEN, 24, 65,
                "Doctoral project with a hospital partner on label-efficient segmentation.",
                "Investigate self-supervised pre-training for segmenting organs in CT scans when only a few "
                "labelled scans are available, in partnership with a teaching hospital.",
                ("Computer Vision", "Medical Imaging", "PyTorch")),
    PostingSpec("Wei Zhang", "Research assistantship: graph neural networks for traffic forecasting", _RA, _OPEN, 11, 26,
                "Part-time assistantship on spatio-temporal graph models.",
                "Implement and benchmark graph neural networks that forecast city traffic from sensor "
                "networks, and help prepare an open-source release.",
                ("Graph Neural Networks", "Python", "Time Series"), PostingWorkMode.HYBRID, 1,
                (CompensationType.STIPEND, 2400, "USD", "MONTH", CommitmentType.PART_TIME, 20, 12)),
    PostingSpec("Wei Zhang", "Postdoc in trustworthy machine learning", PostingType.POSTDOC, PostingStatus.DRAFT, 0, 100,
                "Draft posting for a postdoc on robustness and calibration.",
                "A planned postdoctoral position on robustness and calibration of deep models; the funding "
                "details are still being confirmed.", ("Machine Learning", "Statistics"),
                PostingWorkMode.ONSITE, 1, (CompensationType.SALARY, 62000, "USD", "YEAR", CommitmentType.FULL_TIME, 40, 24)),
    PostingSpec("Meera Iyer", "Internship: evaluating LLM reasoning on scientific text", PostingType.INTERNSHIP, _OPEN, 7, 30,
                "Summer internship on reasoning benchmarks for scientific papers.",
                "Build a benchmark of reasoning questions over scientific abstracts and evaluate how "
                "current language models answer them.", ("NLP", "Large Language Models", "Python"),
                PostingWorkMode.REMOTE, 2, (CompensationType.STIPEND, 3500, "USD", "MONTH", CommitmentType.FULL_TIME, 40, 3)),
    PostingSpec("Grace Whitmore", "Collaboration: participatory design study across three universities", PostingType.COLLABORATION, _OPEN, 19, 70,
                "Seeking partner HCI groups for a cross-site participatory design study.",
                "We are running the same participatory design protocol at three universities and are looking "
                "for one more partner site with experience in community-based research.",
                ("HCI", "Qualitative Research"), PostingWorkMode.REMOTE),
    PostingSpec("Grace Whitmore", "Research assistantship: eye-tracking study on reading interfaces", _RA, PostingStatus.CLOSED, 33, 25,
                "Part-time assistantship running an eye-tracking study.",
                "Recruit participants, run eye-tracking sessions on reading interfaces and help analyse "
                "fixation data.", ("Eye Tracking", "Statistics", "User Studies"), PostingWorkMode.ONSITE, 1,
                (CompensationType.STIPEND, 2000, "USD", "MONTH", CommitmentType.PART_TIME, 15, 6)),
]

_REJECTION_REASONS = (
    "We selected a candidate with more hands-on experience in this area.",
    "The role needs availability for the full duration, which did not fit your timeline.",
    "We had a very strong pool and could only take a small number forward.",
)
_REVIEWER_NOTES = (
    "Strong project experience; invite to a short interview.",
    "Good fit on skills, check availability for the start date.",
    "Promising, but compare with the other shortlisted candidates first.",
)
_COVER_OPENINGS = (
    "I would like to apply for this opening.",
    "I am very interested in this position.",
    "This opening matches what I hope to work on next.",
)

# ── Identity (Phase 6.4 audit P2-1 scheme, separate namespace) ───────────────────────────
_ACCOUNT_ID_DOMAIN = b"researchconnect-ai/seed-community/account-id/v1"


def _account_id(email: str, nonce: bytes) -> uuid.UUID:
    check = hashlib.sha256(_ACCOUNT_ID_DOMAIN + nonce + email.encode("utf-8")).digest()[:8]
    return uuid.UUID(bytes=nonce + check, version=4)


def new_community_account_id(email: str) -> uuid.UUID:
    return _account_id(email, uuid.uuid4().bytes[:8])


def is_community_account(user: UserModel) -> bool:
    """Whether this script created the account, whatever email it holds now."""
    return user.id == _account_id(user.email, user.id.bytes[:8])


def _rng_for(key: str) -> random.Random:
    """A random stream fixed by one key (a person's email, a posting's title), so a re-run that
    skips earlier work still makes exactly the same choices for everything after it."""
    return random.Random(f"{_SEED}:{key}")


def email_for(full_name: str, domain: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", full_name).encode("ascii", "ignore").decode()
    parts = ["".join(ch for ch in part.lower() if ch.isalnum()) for part in ascii_name.split()]
    return f"{parts[0]}.{parts[-1]}@{domain}"


def community_emails() -> list[str]:
    return [email_for(name, INSTITUTIONS[inst][1]) for name, inst, *_ in FACULTY + STUDENTS]


def resolve_password(requested: str | None, app_env: str) -> str:
    """The community accounts' password: required, and held to the registration policy."""
    if not requested:
        raise ValueError("--password is required to create the community accounts")
    if app_env == "production" and requested == _PUBLIC_DEMO_PASSWORD:
        raise ValueError("APP_ENV=production: the public demo password is not accepted")
    try:
        RegisterRequest(email="someone@fairviewtech.edu", password=requested, full_name="Community")
    except ValidationError as err:
        reasons = [e["msg"] for e in err.errors() if e.get("loc") and e["loc"][0] == "password"]
        raise ValueError("--password " + ("; ".join(reasons) or "is not acceptable")) from None
    return requested


# ── People ───────────────────────────────────────────────────────────────────────────────


@dataclass
class Person:
    full_name: str
    email: str
    institution: str
    area: Area
    role: str
    academic_status: AcademicStatus
    department: str
    rank: str = ""
    user: UserModel | None = None
    profile: ResearchProfileModel | None = None
    applications: list = field(default_factory=list)


def _people() -> list[Person]:
    people = [
        Person(f"Dr. {name}", email_for(name, INSTITUTIONS[inst][1]), inst, AREAS[area], "FACULTY",
               AcademicStatus.FACULTY, dept, rank)
        for name, inst, area, dept, rank in FACULTY
    ]
    faculty_depts = {inst: dept for _, inst, _, dept, _ in FACULTY}
    people += [
        Person(name, email_for(name, INSTITUTIONS[inst][1]), inst, AREAS[area], "STUDENT", status,
               faculty_depts.get(inst, "Computer Science"))
        for name, inst, area, status in STUDENTS
    ]
    return people


def _bio(person: Person) -> str:
    inst = INSTITUTIONS[person.institution][0]
    k1, k2, k3 = person.area.keywords
    if person.role == "FACULTY":
        return (f"{person.rank} in {person.department} at {inst}. Leads a group working on {k1} "
                f"and {k2}, with a recent focus on {k3}.")
    stage = {
        AcademicStatus.PHD: "PhD candidate",
        AcademicStatus.POSTGRADUATE: "Master's student",
        AcademicStatus.UNDERGRADUATE: "Final-year undergraduate",
    }[person.academic_status]
    return f"{stage} in {person.department} at {inst}, interested in {k1} and {k2}."


def _upsert_person(db: Session, person: Person, hashed: str) -> bool:
    """Creates or refreshes one account and profile. False when the email is someone else's."""
    user = db.execute(select(UserModel).where(UserModel.email == person.email)).scalar_one_or_none()
    if user is not None and not is_community_account(user):
        logger.warning("skipping %s: that email belongs to an account this script did not create", person.email)
        return False
    if user is None:
        user = UserModel(id=new_community_account_id(person.email), email=person.email)
        db.add(user)
    user.hashed_password = hashed
    user.full_name = person.full_name
    user.role = person.role
    user.is_active = True
    user.is_verified = True
    db.flush()

    profile = db.execute(
        select(ResearchProfileModel).where(ResearchProfileModel.user_id == user.id)
    ).scalar_one_or_none()
    if profile is None:
        profile = ResearchProfileModel(id=uuid.uuid4(), user_id=user.id)
        db.add(profile)
    profile.academic_status = person.academic_status.value
    profile.institution = INSTITUTIONS[person.institution][0]
    profile.department = person.department
    profile.bio = _bio(person)
    profile.keywords = list(person.area.keywords)
    profile.target_opportunity_types = (
        ["CONFERENCE", "JOURNAL"] if person.role == "FACULTY" else ["CONFERENCE", "WORKSHOP"]
    )
    db.flush()
    person.user, person.profile = user, profile
    return True


def _seed_expertise(db: Session, person: Person, topics: dict[str, TopicModel], rng: random.Random) -> None:
    chosen = list(person.area.topics.items())
    if person.role != "FACULTY":
        chosen = chosen[: rng.randint(2, 3)]
    for slug, base in chosen:
        topic = topics.get(slug)
        if topic is None:
            continue
        scale = 1.0 if person.role == "FACULTY" else rng.uniform(0.6, 0.85)
        strength = round(min(0.98, base * scale + rng.uniform(-0.04, 0.04)), 2)
        interest = db.execute(
            select(ResearcherInterestModel).where(
                ResearcherInterestModel.profile_id == person.profile.id,
                ResearcherInterestModel.topic_slug == slug,
            )
        ).scalar_one_or_none()
        if interest is None:
            interest = ResearcherInterestModel(
                id=uuid.uuid4(), profile_id=person.profile.id, topic_id=topic.id,
                topic_name=topic.name, topic_slug=slug, source=_INTEREST_SOURCE,
                provenance={"reasons": ["Community seed expertise"]},
            )
            db.add(interest)
        interest.strength = strength
        interest.confidence = round(rng.uniform(0.80, 0.95), 2)
        interest.evidence_count = rng.randint(2, 9)
        interest.classification = "PRIMARY_EXPERTISE" if strength >= 0.65 else "EMERGING_INTEREST"
        interest.is_primary_expertise = strength >= 0.65


def _seed_preferences(db: Session, person: Person) -> None:
    if person.role != "FACULTY" and person.academic_status != AcademicStatus.PHD:
        return
    wanted = [
        ("RESEARCH_DOMAIN", person.area.label),
        ("OPPORTUNITY_TYPE", "JOURNAL" if person.role == "FACULTY" else "CONFERENCE"),
    ]
    for category, value in wanted:
        existing = db.execute(
            select(ResearcherPreferenceModel).where(
                ResearcherPreferenceModel.profile_id == person.profile.id,
                ResearcherPreferenceModel.category == category,
                ResearcherPreferenceModel.preference_value == value,
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(ResearcherPreferenceModel(
            id=uuid.uuid4(), profile_id=person.profile.id, category=category,
            preference_type="PREFERRED", preference_key=category.lower(), preference_value=value,
            display_label=value, strength=0.80, confidence=1.00, source="EXPLICIT", is_active=True,
            provenance={"reasons": ["Community seed preference"]},
        ))


def _seed_discovery(db: Session, person: Person, rng: random.Random, now: datetime) -> None:
    """About 85% opt in to peer discovery; nobody's contact email is shown."""
    if rng.random() >= 0.85:
        return
    settings_row = db.execute(
        select(ResearcherDiscoverySettingsModel).where(
            ResearcherDiscoverySettingsModel.profile_id == person.profile.id
        )
    ).scalar_one_or_none()
    if settings_row is None:
        settings_row = ResearcherDiscoverySettingsModel(id=uuid.uuid4(), profile_id=person.profile.id)
        db.add(settings_row)
    if person.role == "FACULTY":
        status = rng.choice([CollaborationStatus.SEEKING_COLLABORATORS] * 3 + [CollaborationStatus.OPEN_TO_ENQUIRIES])
        pool = [CollaborationInterest.CO_AUTHORSHIP, CollaborationInterest.JOINT_GRANT,
                CollaborationInterest.STUDENT_CO_SUPERVISION, CollaborationInterest.PEER_REVIEW_EXCHANGE]
        note = f"Happy to discuss joint work on {person.area.keywords[0]} and {person.area.keywords[2]}."
    else:
        status = rng.choice([CollaborationStatus.OPEN_TO_ENQUIRIES] * 2 + [CollaborationStatus.SELECTIVELY_AVAILABLE])
        pool = [CollaborationInterest.CO_AUTHORSHIP, CollaborationInterest.METHOD_EXCHANGE,
                CollaborationInterest.MENTORSHIP, CollaborationInterest.DATA_SHARING]
        note = f"Looking to collaborate on {person.area.keywords[0]}."
    settings_row.is_discoverable = True
    settings_row.collaboration_status = status.value
    settings_row.collaboration_interests = [i.value for i in rng.sample(pool, rng.randint(2, 3))]
    settings_row.show_institution = True
    settings_row.show_contact_email = False
    settings_row.collaboration_note = note
    settings_row.consent_updated_at = now - timedelta(days=rng.randint(3, 60))


# ── Postings and applications (through the application's own services) ──────────────────

# Status reached from SUBMITTED, as (actor, next status) steps the services allow.
_PATHS: dict[ApplicationStatus, list[tuple[str, ApplicationStatus]]] = {
    ApplicationStatus.SUBMITTED: [],
    ApplicationStatus.UNDER_REVIEW: [("author", ApplicationStatus.UNDER_REVIEW)],
    ApplicationStatus.SHORTLISTED: [("author", ApplicationStatus.UNDER_REVIEW), ("author", ApplicationStatus.SHORTLISTED)],
    ApplicationStatus.OFFERED: [("author", ApplicationStatus.UNDER_REVIEW), ("author", ApplicationStatus.SHORTLISTED),
                                ("author", ApplicationStatus.OFFERED)],
    ApplicationStatus.ACCEPTED: [("author", ApplicationStatus.UNDER_REVIEW), ("author", ApplicationStatus.SHORTLISTED),
                                 ("author", ApplicationStatus.OFFERED), ("applicant", ApplicationStatus.ACCEPTED)],
    ApplicationStatus.DECLINED: [("author", ApplicationStatus.UNDER_REVIEW), ("author", ApplicationStatus.OFFERED),
                                 ("applicant", ApplicationStatus.DECLINED)],
    ApplicationStatus.REJECTED: [("author", ApplicationStatus.UNDER_REVIEW), ("author", ApplicationStatus.REJECTED)],
    ApplicationStatus.WITHDRAWN: [("applicant", ApplicationStatus.WITHDRAWN)],
}


def _outcomes(spec: PostingSpec | None, count: int, rng: random.Random) -> list[ApplicationStatus]:
    if spec is None:  # the demo faculty's opening: left for the demo to review
        return [ApplicationStatus.SUBMITTED] * (count - 1) + [ApplicationStatus.UNDER_REVIEW]
    if spec.final_status == PostingStatus.FILLED:
        head = [ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED, ApplicationStatus.DECLINED]
        pool = [ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN]
    elif spec.final_status == PostingStatus.CLOSED:
        head = [ApplicationStatus.SHORTLISTED, ApplicationStatus.UNDER_REVIEW]
        pool = [ApplicationStatus.REJECTED, ApplicationStatus.UNDER_REVIEW, ApplicationStatus.WITHDRAWN]
    else:
        head = [ApplicationStatus.SUBMITTED, ApplicationStatus.UNDER_REVIEW]
        pool = [ApplicationStatus.SUBMITTED, ApplicationStatus.SUBMITTED, ApplicationStatus.UNDER_REVIEW,
                ApplicationStatus.SHORTLISTED, ApplicationStatus.REJECTED, ApplicationStatus.OFFERED,
                ApplicationStatus.WITHDRAWN]
    chosen = head[:count] + [rng.choice(pool) for _ in range(max(0, count - len(head)))]
    rng.shuffle(chosen)
    return chosen


def _cover_note(person: Person, posting_title: str, rng: random.Random) -> str:
    stage = {"PHD": "a PhD candidate", "POSTGRADUATE": "a master's student",
             "UNDERGRADUATE": "a final-year undergraduate"}.get(person.academic_status.value, "a student")
    return (f"{rng.choice(_COVER_OPENINGS)} I am {stage} at {INSTITUTIONS[person.institution][0]} working on "
            f"{person.area.keywords[0]}, and \"{posting_title}\" builds directly on my recent coursework and "
            f"project experience with {person.area.keywords[1]}.")


def _apply_and_progress(
    db: Session,
    posting: ResearchPostingModel,
    author: UserModel,
    spec: PostingSpec | None,
    applicants: list[Person],
    published_at: datetime,
    now: datetime,
    rng: random.Random,
) -> int:
    """Submits applications as the students and moves them on as author and applicant would."""
    created = 0
    span = max(1.0, (now - published_at).total_seconds() / 86400 - 1)
    for person, outcome in zip(applicants, _outcomes(spec, len(applicants), rng)):
        existing = db.execute(
            select(ResearchPostingApplicationModel).where(
                ResearchPostingApplicationModel.posting_id == posting.id,
                ResearchPostingApplicationModel.applicant_profile_id == person.profile.id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        submitted_at = published_at + timedelta(days=rng.uniform(0.3, span))
        try:
            application = ResearchPostingApplicationService.submit_application(
                db, posting.id, person.profile, person.user,
                ApplicationCreate(cover_note=_cover_note(person, posting.title, rng)),
                reference_time=submitted_at,
            )
        except (ApplicationNotAcceptedError, DuplicateApplicationError) as exc:
            logger.info("not applying %s to %r: %s", person.email, posting.title, exc)
            continue
        created += 1
        moment = submitted_at
        for actor, target in _PATHS[outcome]:
            moment = min(now - timedelta(minutes=5), moment + timedelta(days=rng.uniform(0.2, 2.5)))
            ResearchPostingApplicationService.transition_application(
                db, application.id, author if actor == "author" else person.user, target,
                decision_reason=rng.choice(_REJECTION_REASONS) if target == ApplicationStatus.REJECTED else None,
                reviewer_note=rng.choice(_REVIEWER_NOTES) if target == ApplicationStatus.SHORTLISTED else None,
                reference_time=moment,
            )
    return created


def _pick_applicants(students: list[Person], area: Area, count: int, rng: random.Random) -> list[Person]:
    same = [s for s in students if s.area is area]
    others = [s for s in students if s.area is not area]
    rng.shuffle(same)
    rng.shuffle(others)
    return (same + others)[:count]


def _seed_postings(
    db: Session,
    people: dict[str, Person],
    students: list[Person],
    topics: dict[str, TopicModel],
    now: datetime,
) -> tuple[int, int]:
    postings_created = applications = 0
    for spec in POSTINGS:
        author = people.get(f"Dr. {spec.author}")
        if author is None or author.profile is None:
            continue
        exists = db.execute(
            select(ResearchPostingModel).where(
                ResearchPostingModel.title == spec.title,
                ResearchPostingModel.author_profile_id == author.profile.id,
            )
        ).scalar_one_or_none()
        if exists is not None:
            continue

        terms = None
        if spec.terms:
            kind, amount, currency, period, commitment, hours, months = spec.terms
            terms = OpeningTermsUpdate(
                compensation_type=kind, compensation_amount=amount, compensation_currency=currency,
                compensation_period=period, commitment_type=commitment, hours_per_week=hours,
                duration_months=months,
                eligibility_requirements="Currently enrolled in a degree programme, or graduating this year.",
                accepts_applications=True,
            )
        deadline = now + timedelta(days=spec.days_until_deadline)
        payload = ResearchPostingCreate(
            title=spec.title, posting_type=spec.posting_type, summary=spec.summary,
            description=spec.description, required_skills=list(spec.skills),
            location=INSTITUTIONS[author.institution][2], country=INSTITUTIONS[author.institution][3],
            work_mode=spec.work_mode, positions_available=spec.positions, application_deadline=deadline,
            expected_start_date=(deadline + timedelta(days=30)).date(), contact_email=author.email,
            topic_ids=[topics[s].id for s in author.area.topics if s in topics][:3],
            opening_terms=terms,
        )
        posting = ResearchPostingService.create_posting(db, author.profile, author.user, payload)
        postings_created += 1
        if spec.final_status == PostingStatus.DRAFT:
            continue

        rng = _rng_for(spec.title)
        published_at = now - timedelta(days=spec.published_days_ago, hours=rng.uniform(0, 8))
        ResearchPostingService.transition_status(
            db, posting.id, author.user, PostingStatus.OPEN, reference_time=published_at
        )
        if posting.accepts_applications:
            applicants = _pick_applicants(students, author.area, rng.randint(3, 6), rng)
            applications += _apply_and_progress(
                db, posting, author.user, spec, applicants, published_at, now, rng
            )
        if spec.final_status in (PostingStatus.CLOSED, PostingStatus.FILLED):
            ResearchPostingService.transition_status(
                db, posting.id, author.user, spec.final_status,
                reference_time=now - timedelta(days=rng.uniform(0.5, 3)),
            )
    return postings_created, applications


def _apply_to_demo_assistantship(db: Session, students: list[Person], now: datetime) -> int:
    """A few applications to the demo faculty's open assistantship, left for the demo to review."""
    posting = db.execute(
        select(ResearchPostingModel).where(ResearchPostingModel.title == DEMO_ASSISTANTSHIP_TITLE)
    ).scalar_one_or_none()
    if posting is None:
        return 0
    author = db.get(UserModel, posting.author_user_id)
    since = posting.published_at or (now - timedelta(days=10))
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    rng = _rng_for(DEMO_ASSISTANTSHIP_TITLE)
    applicants = _pick_applicants(students, AREAS["retrieval"], 4, rng)
    return _apply_and_progress(db, posting, author, None, applicants, since, now, rng)


# ── Entry points ─────────────────────────────────────────────────────────────────────────


def seed_community(db: Session, password: str, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    hashed = hash_password(password)
    topics = {t.slug: t for t in db.execute(select(TopicModel)).scalars()}

    people = _people()
    active = [p for p in people if _upsert_person(db, p, hashed)]
    for person in active:
        rng = _rng_for(person.email)
        _seed_expertise(db, person, topics, rng)
        _seed_preferences(db, person)
        _seed_discovery(db, person, rng, now)
    db.commit()

    by_name = {p.full_name: p for p in active}
    students = [p for p in active if p.role == "STUDENT"]
    postings, applications = _seed_postings(db, by_name, students, topics, now)
    applications += _apply_to_demo_assistantship(db, students, now)
    db.commit()
    return {
        "people": len(active),
        "faculty": sum(p.role == "FACULTY" for p in active),
        "students": len(students),
        "skipped_foreign_emails": len(people) - len(active),
        "postings_created": postings,
        "applications_created": applications,
    }


def remove_community(db: Session) -> dict[str, int]:
    """Deletes the accounts this script created; their profiles, postings and applications
    go with them through the database's ON DELETE CASCADE foreign keys."""
    users = db.execute(select(UserModel).where(UserModel.email.in_(community_emails()))).scalars().all()
    ours = [u.id for u in users if is_community_account(u)]
    if ours:
        db.execute(delete(UserModel).where(UserModel.id.in_(ours)))
        db.commit()
    return {"accounts_removed": len(ours), "kept_foreign": len(users) - len(ours)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Add (or remove) a realistic community of demo researchers")
    parser.add_argument("--password", help="Password for the community accounts (required unless --remove)")
    parser.add_argument("--remove", action="store_true", help="Delete everything this script created")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.remove:
            result = remove_community(db)
        else:
            try:
                password = resolve_password(args.password, settings.app_env)
            except ValueError as exc:
                logger.error("%s", exc)
                return 1
            result = seed_community(db, password)

    print("\n--- Community seed summary ---")
    for key, value in result.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
