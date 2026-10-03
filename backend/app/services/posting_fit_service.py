"""
Phase 5.15 — How well a research posting fits a student.

Read-only and deterministic. A student's signals are read directly from their research
interests, their active preferences and their profile keywords. Nothing is written, no profile is
created, and `get_researcher_intelligence` (which recomputes and stores) is never called.

Three parts with fixed weights, renormalised over the parts the posting gives evidence for:

  topic    0.50  canonical topic overlap (the Phase 2.4D topic compatibility), when the posting
                 has topics
  skills   0.30  share of the posting's required skills the student has recorded, when it lists any
  opening  0.20  the average of type, stage and placement fit, always

A student with no signals in a part still scores 0 for it: renormalising only over the
posting's evidence is what lets a topic match outrank a skills-only match.

An EXCLUDED preference matching one of the posting's topics or its type caps the score at 20. A
student with no interests, keywords or preferences at all gets no score, only guidance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Iterable, Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.research_posting import PostingType, PostingWorkMode, ResearchPostingModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_interest import ResearcherInterestModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.user import UserModel
from app.schemas.posting_fit import PostingFitRead, PostingFitReason
from app.services.research_opportunity_matching_service import calculate_topic_compatibility

TOPIC_WEIGHT = 0.50
SKILLS_WEIGHT = 0.30
OPENING_WEIGHT = 0.20

EXCLUDED_CAP = 20
MAX_GAPS = 5
NO_SIGNALS_GAP = "Add research interests or keywords to your profile"
EXCLUDED_LABEL = "Matches something you excluded"
DEADLINE_LABEL = "Applications closed"

# Score bands, highest first.
BANDS: tuple[tuple[int, str], ...] = ((75, "Strong"), (50, "Good"), (25, "Partial"))
LOW_BAND = "Low"

# Career stage fit by posting type: (suited stages, score when suited, score otherwise). Any
# other type scores 0.5 for every stage. A post-doc needs a completed doctorate.
_STAGE_RULES: dict[str, tuple[frozenset[str], float, float]] = {
    PostingType.POSTDOC.value: (frozenset({"PHD", "POSTDOC"}), 1.0, 0.0),
    PostingType.INTERNSHIP.value: (frozenset({"UNDERGRADUATE", "POSTGRADUATE", "PHD"}), 1.0, 0.5),
    PostingType.RESEARCH_ASSISTANTSHIP.value: (
        frozenset({"UNDERGRADUATE", "POSTGRADUATE", "PHD"}),
        1.0,
        0.5,
    ),
}
_NEUTRAL = 0.5

_TOKEN = re.compile(r"[^\W_]+(?:[+#]+)?")
_SKILL_STOPWORDS = frozenset({"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"})


@dataclass(frozen=True)
class TopicSignal:
    """The attributes `calculate_topic_compatibility` reads from a topic association."""

    topic_id: uuid.UUID
    confidence_score: float
    is_primary: bool = False
    topic: Any = None


@dataclass(frozen=True)
class StudentSignals:
    """Everything the scorer reads about one student, normalised away from the ORM."""

    profile_id: uuid.UUID
    academic_status: str | None = None
    topics: tuple[TopicSignal, ...] = ()
    # Profile keywords, KEYWORD preferences and interest names: what skills are matched against.
    terms: tuple[str, ...] = ()
    preferred_types: frozenset[str] = frozenset()
    excluded_types: frozenset[str] = frozenset()
    excluded_topic_ids: frozenset[uuid.UUID] = frozenset()
    excluded_topic_slugs: frozenset[str] = frozenset()
    countries: frozenset[str] = frozenset()
    locations: tuple[str, ...] = ()

    @property
    def has_signals(self) -> bool:
        return bool(
            self.topics
            or self.terms
            or self.preferred_types
            or self.excluded_types
            or self.excluded_topic_ids
            or self.excluded_topic_slugs
            or self.countries
            or self.locations
        )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in _TOKEN.findall(text.casefold()) if t not in _SKILL_STOPWORDS)


def build_signals(
    profile: ResearchProfileModel,
    interests: Iterable[ResearcherInterestModel],
    preferences: Iterable[ResearcherPreferenceModel],
) -> StudentSignals:
    """Normalises one student's rows. `preferences` must already be the active ones."""
    best_topics: dict[uuid.UUID, TopicSignal] = {}

    def add_topic(topic_id: uuid.UUID, confidence: float, primary: bool) -> None:
        candidate = TopicSignal(topic_id, round(_clamp(confidence), 6), primary)
        current = best_topics.get(topic_id)
        if current is None or (candidate.confidence_score, candidate.is_primary) > (
            current.confidence_score,
            current.is_primary,
        ):
            best_topics[topic_id] = candidate

    terms: list[str] = [kw for kw in (profile.keywords or []) if isinstance(kw, str)]
    for interest in interests:
        if interest.topic_id is not None:
            add_topic(
                interest.topic_id,
                float(interest.confidence or 0.0),
                bool(interest.is_primary_expertise),
            )
        if interest.topic_name:
            terms.append(interest.topic_name)

    preferred_types: set[str] = set()
    excluded_types: set[str] = set()
    excluded_topic_ids: set[uuid.UUID] = set()
    excluded_topic_slugs: set[str] = set()
    countries: set[str] = set()
    locations: set[str] = set()
    for pref in preferences:
        category = (pref.category or "").upper()
        excluded = (pref.preference_type or "").upper() == "EXCLUDED"
        value = (pref.preference_value or "").strip()
        if category == "TOPIC":
            if excluded:
                if pref.canonical_id is not None:
                    excluded_topic_ids.add(pref.canonical_id)
                if value:
                    excluded_topic_slugs.add(value.casefold())
            elif pref.canonical_id is not None:
                add_topic(pref.canonical_id, float(pref.confidence or 0.0), False)
        elif category == "KEYWORD" and not excluded and value:
            terms.append(value)
        elif category == "OPPORTUNITY_TYPE" and value:
            normalised = value.upper().replace("-", "_").replace(" ", "_")
            (excluded_types if excluded else preferred_types).add(normalised)
        elif category == "COUNTRY" and not excluded and value:
            countries.add(value.casefold())
        elif category == "LOCATION" and not excluded and value:
            locations.add(value.casefold())

    unique_terms: dict[str, str] = {}
    for term in terms:
        cleaned = " ".join(term.split())
        if cleaned:
            unique_terms.setdefault(cleaned.casefold(), cleaned)

    return StudentSignals(
        profile_id=profile.id,
        academic_status=(profile.academic_status or "").upper() or None,
        topics=tuple(best_topics[t] for t in sorted(best_topics, key=str)),
        terms=tuple(unique_terms[k] for k in sorted(unique_terms)),
        preferred_types=frozenset(preferred_types),
        excluded_types=frozenset(excluded_types),
        excluded_topic_ids=frozenset(excluded_topic_ids),
        excluded_topic_slugs=frozenset(excluded_topic_slugs),
        countries=frozenset(countries),
        locations=tuple(sorted(locations)),
    )


def _band(score: int) -> str:
    for threshold, name in BANDS:
        if score >= threshold:
            return name
    return LOW_BAND


def _clean_skills(skills: Sequence[str] | None) -> list[str]:
    """Required skills, trimmed and de-duplicated case-insensitively, in posting order."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for skill in skills or []:
        if not isinstance(skill, str):
            continue
        text = " ".join(skill.split())
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            cleaned.append(text)
    return cleaned


def _match_skills(skills: Sequence[str], terms: Sequence[str]) -> tuple[list[str], list[str]]:
    """
    A skill is matched when the student's recorded words cover all of it, or when one of the
    student's terms is wholly part of it ("python" matches "Python programming"). Casefolded
    word sets, ignoring a few connecting words.
    """
    term_sets = [s for s in (_tokens(term) for term in terms) if s]
    vocabulary = frozenset().union(*term_sets) if term_sets else frozenset()
    matched: list[str] = []
    missing: list[str] = []
    for skill in skills:
        words = _tokens(skill)
        if words and (words <= vocabulary or any(term <= words for term in term_sets)):
            matched.append(skill)
        else:
            missing.append(skill)
    return matched, missing


def _opening(posting: ResearchPostingModel, signals: StudentSignals) -> tuple[float, str, list[str]]:
    """Type, stage and placement fit, averaged; with a label and the facets that fit."""
    posting_type = posting.posting_type
    facets: list[str] = []

    type_score = 1.0 if posting_type in signals.preferred_types else _NEUTRAL
    if type_score == 1.0:
        facets.append("a type of opening you prefer")

    suited, if_suited, otherwise = _STAGE_RULES.get(posting_type, (frozenset(), _NEUTRAL, _NEUTRAL))
    if posting_type in _STAGE_RULES:
        stage_score = if_suited if signals.academic_status in suited else otherwise
    else:
        stage_score = _NEUTRAL
    if stage_score == 1.0:
        facets.append("suited to your career stage")

    location = (posting.location or "").casefold()
    country = (posting.country or "").casefold()
    remote = posting.work_mode == PostingWorkMode.REMOTE.value
    place_matches = any(c == country or (location and c in location) for c in signals.countries) or any(
        loc == country or (location and loc in location) for loc in signals.locations
    )
    placement_score = 1.0 if remote or place_matches else _NEUTRAL
    if remote:
        facets.append("remote")
    elif place_matches:
        facets.append("in a place you prefer")

    if posting_type == PostingType.POSTDOC.value and stage_score == 0.0:
        label = "Post-doctoral positions need a completed PhD"
    elif facets:
        label = "The opening is " + ", ".join(facets)
    else:
        label = "No stated preference matches this opening's type or place"
    return round((type_score + stage_score + placement_score) / 3, 6), label, facets


def _excluded_hits(posting: ResearchPostingModel, signals: StudentSignals) -> list[str]:
    hits: list[str] = []
    for assoc in posting.topic_associations or []:
        topic = getattr(assoc, "topic", None)
        slug = (getattr(topic, "slug", None) or "").casefold()
        if assoc.topic_id in signals.excluded_topic_ids or (slug and slug in signals.excluded_topic_slugs):
            hits.append(getattr(topic, "name", None) or slug or str(assoc.topic_id))
    if posting.posting_type in signals.excluded_types:
        hits.append(posting.posting_type.replace("_", " ").title())
    return sorted(set(hits))


class PostingFitService:
    """Deterministic posting fit for students. Reads only."""

    # ── Signals ──────────────────────────────────────────────────────────────

    @staticmethod
    def load_signals(
        db: Session,
        profiles: Sequence[ResearchProfileModel],
    ) -> dict[uuid.UUID, StudentSignals]:
        """Signals for many students in two queries, however many there are."""
        if not profiles:
            return {}
        ids = [profile.id for profile in profiles]
        interests: dict[uuid.UUID, list[ResearcherInterestModel]] = {}
        for row in db.execute(
            select(ResearcherInterestModel).where(ResearcherInterestModel.profile_id.in_(ids))
        ).scalars():
            interests.setdefault(row.profile_id, []).append(row)
        preferences: dict[uuid.UUID, list[ResearcherPreferenceModel]] = {}
        for row in db.execute(
            select(ResearcherPreferenceModel).where(
                ResearcherPreferenceModel.profile_id.in_(ids),
                ResearcherPreferenceModel.is_active.is_(True),
            )
        ).scalars():
            preferences.setdefault(row.profile_id, []).append(row)
        return {
            profile.id: build_signals(
                profile, interests.get(profile.id, []), preferences.get(profile.id, [])
            )
            for profile in profiles
        }

    @classmethod
    def signals_for_user(cls, db: Session, user: UserModel) -> StudentSignals | None:
        """The student's signals, or None without a profile. A profile is never created here."""
        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.user_id == user.id)
        ).scalars().first()
        if profile is None:
            return None
        return cls.load_signals(db, [profile])[profile.id]

    # ── Scoring ──────────────────────────────────────────────────────────────

    @staticmethod
    def score(
        posting: ResearchPostingModel,
        signals: StudentSignals | None,
        *,
        now: datetime | None = None,
    ) -> PostingFitRead:
        """The fit of one posting for one student. Pure: reads only the objects passed in."""
        now = now or datetime.now(timezone.utc)
        deadline = posting.application_deadline
        notices: list[PostingFitReason] = []
        if deadline is not None and _as_utc(deadline) < now:
            notices.append(PostingFitReason(code="DEADLINE_PASSED", label=DEADLINE_LABEL, weight=0.0))

        if signals is None or not signals.has_signals:
            return PostingFitRead(
                posting_id=posting.id,
                score=None,
                band=None,
                reasons=notices,
                gaps=[NO_SIGNALS_GAP],
                computed_at=now,
            )

        # (code, base weight, part score, label, matched)
        parts: list[tuple[str, float, float, str, list[str]]] = []

        posting_topics = list(posting.topic_associations or [])
        if posting_topics:
            topic_score, _, shared_names = calculate_topic_compatibility(signals.topics, posting_topics)
            shared = sorted(set(shared_names))
            label = (
                "Shares your research topics: " + ", ".join(shared[:3])
                if shared
                else "None of its research topics matches yours"
            )
            parts.append(("TOPIC", TOPIC_WEIGHT, topic_score, label, shared))

        skills = _clean_skills(posting.required_skills)
        missing: list[str] = []
        if skills:
            matched, missing = _match_skills(skills, signals.terms)
            parts.append(
                (
                    "SKILLS",
                    SKILLS_WEIGHT,
                    len(matched) / len(skills),
                    f"You have recorded {len(matched)} of its {len(skills)} required skills",
                    matched,
                )
            )

        opening_score, opening_label, facets = _opening(posting, signals)
        parts.append(("OPENING", OPENING_WEIGHT, opening_score, opening_label, facets))

        total_weight = sum(weight for _, weight, _, _, _ in parts)
        ranked: list[tuple[float, PostingFitReason]] = []
        weighted_sum = 0.0
        for code, weight, part_score, label, matched in parts:
            share = weight / total_weight
            contribution = share * part_score
            weighted_sum += contribution
            ranked.append(
                (
                    contribution,
                    PostingFitReason(code=code, label=label, weight=round(share, 4), matched=matched),
                )
            )

        score = int(round(100 * _clamp(weighted_sum)))
        hits = _excluded_hits(posting, signals)
        if hits:
            score = min(score, EXCLUDED_CAP)
            ranked.append(
                (0.0, PostingFitReason(code="EXCLUDED", label=EXCLUDED_LABEL, weight=0.0, matched=hits))
            )
        ranked.extend((0.0, notice) for notice in notices)
        ranked.sort(key=lambda item: (-item[0], item[1].code))

        return PostingFitRead(
            posting_id=posting.id,
            score=score,
            band=_band(score),
            reasons=[reason for _, reason in ranked],
            gaps=missing[:MAX_GAPS],
            computed_at=now,
        )
