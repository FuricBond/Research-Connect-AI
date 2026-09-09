"""
Researcher Personal Preference Intelligence Service (Phase 3.3).

Establishes a canonical, explainable representation of what a researcher prefers:
  - Opportunity types (Conferences, Workshops, Journals, CFPs, Special Issues)
  - Delivery modes (Online, In-Person, Hybrid)
  - Research topics and domains
  - Geographic/regional preferences
  - Deadline preparation windows
  - Open access preferences
  - Specific venues and publishers

Strict Phase Boundaries:
  - Descriptive preference intelligence only.
  - NO personalized recommendations or candidate ranking (Phase 3.4+).
  - Phase 2 ranking pipelines remain completely unmodified and independent.
  - Critical Invariant: Expertise != Preference. Scholarly expertise from Phase 3.2
    is never automatically converted into explicit preferences.
  - NO fabricated behavioral data: Inferred preferences require real SavedOpportunityModel records.
  - ZERO LLM dependency (deterministic math, rule-based provenance, bounded scoring).
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import math
from typing import Any, Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_interest import ResearcherInterestModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.topic import TopicModel
from app.schemas.researcher_preference import (
    PreferenceCategory,
    PreferenceCompletenessSchema,
    PreferenceConflictSchema,
    PreferenceIntelligenceSummarySchema,
    PreferenceSource,
    ResearcherPreferenceCreateSchema,
    ResearcherPreferenceIntelligenceResponse,
    ResearcherPreferenceItemSchema,
    ResearcherPreferenceUpdateSchema,
)

logger = logging.getLogger(__name__)

# Canonical Opportunity Types supported by the repository
CANONICAL_OPPORTUNITY_TYPES: dict[str, tuple[str, str]] = {
    "CONFERENCE": ("CONFERENCE", "Conference"),
    "CONFERENCES": ("CONFERENCE", "Conference"),
    "JOURNAL": ("JOURNAL", "Journal"),
    "JOURNALS": ("JOURNAL", "Journal"),
    "WORKSHOP": ("WORKSHOP", "Workshop"),
    "WORKSHOPS": ("WORKSHOP", "Workshop"),
    "CALL_FOR_PAPERS": ("CALL_FOR_PAPERS", "Call for Papers"),
    "CALL FOR PAPERS": ("CALL_FOR_PAPERS", "Call for Papers"),
    "CALL-FOR-PAPERS": ("CALL_FOR_PAPERS", "Call for Papers"),
    "CFP": ("CALL_FOR_PAPERS", "Call for Papers"),
    "CFPS": ("CALL_FOR_PAPERS", "Call for Papers"),
    "SPECIAL_ISSUE": ("SPECIAL_ISSUE", "Special Issue"),
    "SPECIAL ISSUE": ("SPECIAL_ISSUE", "Special Issue"),
    "SPECIAL-ISSUE": ("SPECIAL_ISSUE", "Special Issue"),
    "SPECIAL ISSUES": ("SPECIAL_ISSUE", "Special Issue"),
}

# Canonical Delivery Modes supported by the repository
CANONICAL_DELIVERY_MODES: dict[str, tuple[str, str]] = {
    "ONLINE": ("ONLINE", "Online / Virtual"),
    "REMOTE": ("ONLINE", "Online / Virtual"),
    "VIRTUAL": ("ONLINE", "Online / Virtual"),
    "OFFLINE": ("OFFLINE", "In-Person (Offline)"),
    "IN_PERSON": ("OFFLINE", "In-Person (Offline)"),
    "IN-PERSON": ("OFFLINE", "In-Person (Offline)"),
    "IN PERSON": ("OFFLINE", "In-Person (Offline)"),
    "ONSITE": ("OFFLINE", "In-Person (Offline)"),
    "ON-SITE": ("OFFLINE", "In-Person (Offline)"),
    "HYBRID": ("HYBRID", "Hybrid"),
    "BLENDED": ("HYBRID", "Hybrid"),
}


class ResearcherPreferenceService:
    """
    Canonical Service for Researcher Personal Preference Intelligence (Phase 3.3).

    Handles normalization, explicit preference CRUD, activity-based inference,
    derived expertise candidates, contradiction handling, and completeness evaluation.
    """

    # -------------------------------------------------------------------------
    # Normalization
    # -------------------------------------------------------------------------

    @classmethod
    def normalize_preference(
        cls,
        category: str | PreferenceCategory,
        raw_key: str | None,
        raw_value: str,
        raw_label: str | None = None,
        canonical_id: uuid.UUID | None = None,
        db: Session | None = None,
    ) -> tuple[str, str, str, str, uuid.UUID | None]:
        """
        Normalize raw inputs against canonical repository taxonomy and entities.

        Returns: (category, preference_key, preference_value, display_label, canonical_id)
        """
        cat_str = (category.value if isinstance(category, PreferenceCategory) else str(category)).strip().upper()
        val_clean = raw_value.strip()

        if cat_str == PreferenceCategory.OPPORTUNITY_TYPE.value:
            lookup_key = val_clean.upper().replace("-", "_")
            if lookup_key in CANONICAL_OPPORTUNITY_TYPES:
                norm_val, default_label = CANONICAL_OPPORTUNITY_TYPES[lookup_key]
            else:
                norm_val = lookup_key
                default_label = norm_val.replace("_", " ").title()
            pref_key = raw_key or "opportunity_type"
            display_label = raw_label or default_label
            return (cat_str, pref_key, norm_val, display_label, None)

        elif cat_str == PreferenceCategory.DELIVERY_MODE.value:
            lookup_key = val_clean.upper().replace("-", "_")
            if lookup_key in CANONICAL_DELIVERY_MODES:
                norm_val, default_label = CANONICAL_DELIVERY_MODES[lookup_key]
            else:
                norm_val = lookup_key
                default_label = norm_val.replace("_", " ").title()
            pref_key = raw_key or "delivery_mode"
            display_label = raw_label or default_label
            return (cat_str, pref_key, norm_val, display_label, None)

        elif cat_str == PreferenceCategory.TOPIC.value:
            pref_key = raw_key or "topic"
            slug = val_clean.lower().replace(" ", "-")
            matched_id = canonical_id
            matched_label = raw_label or val_clean

            if db is not None and matched_id is None:
                stmt = select(TopicModel).where(func.lower(TopicModel.slug) == slug)
                topic = db.execute(stmt).scalars().first()
                if not topic:
                    stmt = select(TopicModel).where(func.lower(TopicModel.name) == val_clean.lower())
                    topic = db.execute(stmt).scalars().first()
                if topic:
                    matched_id = topic.id
                    matched_label = topic.name
                    slug = topic.slug

            return (cat_str, pref_key, slug, matched_label, matched_id)

        elif cat_str == PreferenceCategory.LOCATION.value:
            pref_key = raw_key or "location"
            # Title-case location strings
            norm_val = val_clean.title()
            display_label = raw_label or norm_val
            return (cat_str, pref_key, norm_val, display_label, None)

        elif cat_str == PreferenceCategory.DEADLINE_WINDOW.value:
            pref_key = raw_key or "min_days_before_deadline"
            # Extract digits or default
            digits = "".join([c for c in val_clean if c.isdigit()])
            int_val = int(digits) if digits else 14
            norm_val = str(int_val)
            display_label = raw_label or f"Minimum {int_val} days preparation"
            return (cat_str, pref_key, norm_val, display_label, None)

        elif cat_str == PreferenceCategory.OPEN_ACCESS.value:
            pref_key = raw_key or "prefer_open_access"
            norm_val = "true" if val_clean.lower() in ("true", "1", "yes", "open") else "false"
            display_label = raw_label or ("Prefer Open Access" if norm_val == "true" else "No Open Access Preference")
            return (cat_str, pref_key, norm_val, display_label, None)

        elif cat_str == PreferenceCategory.VENUE.value:
            pref_key = raw_key or "venue"
            norm_val = val_clean
            display_label = raw_label or val_clean
            return (cat_str, pref_key, norm_val, display_label, None)

        else:
            # Fallback
            return (cat_str, raw_key or "preference", val_clean, raw_label or val_clean, canonical_id)

    # -------------------------------------------------------------------------
    # Explicit Preference CRUD & Ownership
    # -------------------------------------------------------------------------

    @classmethod
    def create_explicit_preference(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        payload: ResearcherPreferenceCreateSchema,
        current_user_id: uuid.UUID | None = None,
    ) -> ResearcherPreferenceModel:
        """
        Declare an explicit preference for a researcher profile.
        Enforces user ownership and deduplication.
        """
        profile = db.get(ResearchProfileModel, profile_id)
        if not profile:
            raise ValueError(f"Researcher profile {profile_id} does not exist")

        if current_user_id is not None and profile.user_id != current_user_id:
            raise PermissionError("Unauthorized: User does not own this researcher profile")

        cat, key, val, label, cid = cls.normalize_preference(
            category=payload.category,
            raw_key=payload.preference_key,
            raw_value=payload.preference_value,
            raw_label=payload.display_label,
            canonical_id=payload.canonical_id,
            db=db,
        )

        # Check existing item
        stmt = select(ResearcherPreferenceModel).where(
            ResearcherPreferenceModel.profile_id == profile_id,
            ResearcherPreferenceModel.category == cat,
            ResearcherPreferenceModel.preference_value == val,
        )
        existing = db.execute(stmt).scalars().first()

        now = datetime.now(timezone.utc)

        if existing:
            existing.strength = max(0.0, min(1.0, payload.strength))
            existing.is_active = payload.is_active
            existing.display_label = label
            existing.source = PreferenceSource.EXPLICIT.value
            existing.confidence = 0.95
            existing.recency_score = 1.0
            existing.last_observed_at = now
            existing.updated_at = now
            existing.provenance = {
                "reasons": ["Updated explicitly by researcher"],
                "updated_at": now.isoformat(),
            }
            db.commit()
            db.refresh(existing)
            return existing

        new_pref = ResearcherPreferenceModel(
            profile_id=profile_id,
            category=cat,
            preference_key=key,
            preference_value=val,
            display_label=label,
            canonical_id=cid,
            strength=max(0.0, min(1.0, payload.strength)),
            confidence=0.95,
            source=PreferenceSource.EXPLICIT.value,
            is_active=payload.is_active,
            recency_score=1.0,
            provenance={
                "reasons": ["Explicitly declared by researcher"],
                "declared_at": now.isoformat(),
            },
            last_observed_at=now,
        )
        db.add(new_pref)
        db.commit()
        db.refresh(new_pref)
        return new_pref

    @classmethod
    def list_preferences(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        category: str | None = None,
        source: str | None = None,
        is_active: bool | None = None,
    ) -> list[ResearcherPreferenceModel]:
        """List persisted preferences with optional filters."""
        stmt = select(ResearcherPreferenceModel).where(
            ResearcherPreferenceModel.profile_id == profile_id
        )

        if category is not None:
            stmt = stmt.where(ResearcherPreferenceModel.category == category.upper())
        if source is not None:
            stmt = stmt.where(ResearcherPreferenceModel.source == source.upper())
        if is_active is not None:
            stmt = stmt.where(ResearcherPreferenceModel.is_active == is_active)

        stmt = stmt.order_by(
            ResearcherPreferenceModel.strength.desc(),
            ResearcherPreferenceModel.confidence.desc(),
            ResearcherPreferenceModel.created_at.desc(),
        )
        return list(db.execute(stmt).scalars().all())

    @classmethod
    def update_preference(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        preference_id: uuid.UUID,
        payload: ResearcherPreferenceUpdateSchema,
        current_user_id: uuid.UUID | None = None,
    ) -> ResearcherPreferenceModel | None:
        """Update an existing preference item with ownership check."""
        profile = db.get(ResearchProfileModel, profile_id)
        if not profile:
            raise ValueError(f"Researcher profile {profile_id} does not exist")

        if current_user_id is not None and profile.user_id != current_user_id:
            raise PermissionError("Unauthorized: User does not own this researcher profile")

        stmt = select(ResearcherPreferenceModel).where(
            ResearcherPreferenceModel.id == preference_id,
            ResearcherPreferenceModel.profile_id == profile_id,
        )
        pref = db.execute(stmt).scalars().first()
        if not pref:
            return None

        now = datetime.now(timezone.utc)

        if payload.preference_value is not None:
            cat, key, val, label, cid = cls.normalize_preference(
                category=pref.category,
                raw_key=pref.preference_key,
                raw_value=payload.preference_value,
                raw_label=payload.display_label or pref.display_label,
                canonical_id=pref.canonical_id,
                db=db,
            )
            pref.preference_value = val
            pref.display_label = label
            pref.canonical_id = cid

        if payload.display_label is not None and payload.preference_value is None:
            pref.display_label = payload.display_label

        if payload.strength is not None:
            pref.strength = max(0.0, min(1.0, payload.strength))

        if payload.is_active is not None:
            pref.is_active = payload.is_active

        pref.last_observed_at = now
        pref.updated_at = now

        db.commit()
        db.refresh(pref)
        return pref

    @classmethod
    def delete_preference(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        preference_id: uuid.UUID,
        current_user_id: uuid.UUID | None = None,
    ) -> bool:
        """Delete an explicit preference item with ownership check."""
        profile = db.get(ResearchProfileModel, profile_id)
        if not profile:
            raise ValueError(f"Researcher profile {profile_id} does not exist")

        if current_user_id is not None and profile.user_id != current_user_id:
            raise PermissionError("Unauthorized: User does not own this researcher profile")

        stmt = select(ResearcherPreferenceModel).where(
            ResearcherPreferenceModel.id == preference_id,
            ResearcherPreferenceModel.profile_id == profile_id,
        )
        pref = db.execute(stmt).scalars().first()
        if not pref:
            return False

        db.delete(pref)
        db.commit()
        return True

    # -------------------------------------------------------------------------
    # Inferred Preferences (Activity-Based from SavedOpportunityModel)
    # -------------------------------------------------------------------------

    @classmethod
    def infer_preferences_from_activity(
        cls,
        db: Session,
        profile: ResearchProfileModel,
    ) -> list[ResearcherPreferenceItemSchema]:
        """
        Deterministically infer preferences from verified platform activity.

        Strict Boundary:
          - Only actual SavedOpportunityModel records are considered.
          - NO fabricated data. If 0 saved opportunities, returns empty list [].
          - Labeled source = INFERRED.
        """
        # Batch load saved opportunities and their associated opportunity (zero N+1)
        stmt = (
            select(SavedOpportunityModel)
            .options(joinedload(SavedOpportunityModel.opportunity))
            .where(SavedOpportunityModel.user_id == profile.user_id)
            .order_by(SavedOpportunityModel.created_at.desc())
        )
        saved_items = list(db.execute(stmt).scalars().all())

        if not saved_items:
            return []

        total_saved = len(saved_items)
        now = datetime.now(timezone.utc)

        # Tallies
        type_counts: dict[str, int] = {}
        delivery_counts: dict[str, int] = {}
        location_counts: dict[str, int] = {}
        type_latest: dict[str, datetime] = {}
        delivery_latest: dict[str, datetime] = {}
        location_latest: dict[str, datetime] = {}

        for item in saved_items:
            opp = item.opportunity
            if not opp:
                continue

            item_created = item.created_at
            if item_created.tzinfo is None:
                item_created = item_created.replace(tzinfo=timezone.utc)

            # Opportunity Type
            if opp.opportunity_type:
                t = opp.opportunity_type.upper()
                type_counts[t] = type_counts.get(t, 0) + 1
                if t not in type_latest or item_created > type_latest[t]:
                    type_latest[t] = item_created

            # Delivery Mode
            if opp.delivery_mode:
                dm = opp.delivery_mode.upper()
                delivery_counts[dm] = delivery_counts.get(dm, 0) + 1
                if dm not in delivery_latest or item_created > delivery_latest[dm]:
                    delivery_latest[dm] = item_created

            # Location
            if opp.location:
                loc = opp.location.strip().title()
                if len(loc) >= 3:
                    location_counts[loc] = location_counts.get(loc, 0) + 1
                    if loc not in location_latest or item_created > location_latest[loc]:
                        location_latest[loc] = item_created

        inferred: list[ResearcherPreferenceItemSchema] = []

        # Inferred Opportunity Types
        for opp_type, count in type_counts.items():
            freq = count / max(1, total_saved)
            # Threshold: >= 2 saves or if total_saved <= 2, >= 1 save
            if count >= 2 or (total_saved <= 2 and count >= 1):
                # Strength: 40% logarithmic volume + 60% frequency
                vol_factor = min(1.0, math.log(1 + count) / math.log(11))
                strength_raw = 0.40 * vol_factor + 0.60 * freq

                # Recency decay
                latest_dt = type_latest.get(opp_type, now)
                days_old = max(0, (now - latest_dt).days)
                recency = max(0.20, round(math.exp(-0.005 * days_old), 3))
                strength = min(1.0, max(0.1, round(strength_raw * recency, 3)))

                # Confidence: scales with volume and frequency
                confidence = min(0.85, round(0.35 + 0.10 * count + 0.20 * freq, 3))

                _, _, norm_val, label, _ = cls.normalize_preference(
                    PreferenceCategory.OPPORTUNITY_TYPE, "opportunity_type", opp_type
                )

                inferred.append(
                    ResearcherPreferenceItemSchema(
                        id=uuid.uuid5(profile.id, f"inferred_type_{norm_val}"),
                        profile_id=profile.id,
                        category=PreferenceCategory.OPPORTUNITY_TYPE.value,
                        preference_key="opportunity_type",
                        preference_value=norm_val,
                        display_label=label,
                        strength=strength,
                        confidence=confidence,
                        source=PreferenceSource.INFERRED.value,
                        is_active=True,
                        recency_score=recency,
                        provenance={
                            "match_count": count,
                            "total_saved": total_saved,
                            "frequency": round(freq, 3),
                            "days_since_latest": days_old,
                        },
                        provenance_reasons=[
                            f"{count} of {total_saved} saved opportunities were {label.lower()}s ({freq:.0%})"
                        ],
                        last_observed_at=latest_dt,
                    )
                )

        # Inferred Delivery Modes
        for mode, count in delivery_counts.items():
            freq = count / max(1, total_saved)
            if count >= 2 or (total_saved <= 2 and count >= 1):
                vol_factor = min(1.0, math.log(1 + count) / math.log(11))
                strength_raw = 0.40 * vol_factor + 0.60 * freq

                latest_dt = delivery_latest.get(mode, now)
                days_old = max(0, (now - latest_dt).days)
                recency = max(0.20, round(math.exp(-0.005 * days_old), 3))
                strength = min(1.0, max(0.1, round(strength_raw * recency, 3)))
                confidence = min(0.85, round(0.35 + 0.10 * count + 0.20 * freq, 3))

                _, _, norm_val, label, _ = cls.normalize_preference(
                    PreferenceCategory.DELIVERY_MODE, "delivery_mode", mode
                )

                inferred.append(
                    ResearcherPreferenceItemSchema(
                        id=uuid.uuid5(profile.id, f"inferred_mode_{norm_val}"),
                        profile_id=profile.id,
                        category=PreferenceCategory.DELIVERY_MODE.value,
                        preference_key="delivery_mode",
                        preference_value=norm_val,
                        display_label=label,
                        strength=strength,
                        confidence=confidence,
                        source=PreferenceSource.INFERRED.value,
                        is_active=True,
                        recency_score=recency,
                        provenance={
                            "match_count": count,
                            "total_saved": total_saved,
                            "frequency": round(freq, 3),
                            "days_since_latest": days_old,
                        },
                        provenance_reasons=[
                            f"{count} of {total_saved} saved opportunities used {label.lower()} ({freq:.0%})"
                        ],
                        last_observed_at=latest_dt,
                    )
                )

        # Inferred Locations
        for loc, count in location_counts.items():
            freq = count / max(1, total_saved)
            if count >= 2:
                vol_factor = min(1.0, math.log(1 + count) / math.log(11))
                strength_raw = 0.40 * vol_factor + 0.60 * freq

                latest_dt = location_latest.get(loc, now)
                days_old = max(0, (now - latest_dt).days)
                recency = max(0.20, round(math.exp(-0.005 * days_old), 3))
                strength = min(1.0, max(0.1, round(strength_raw * recency, 3)))
                confidence = min(0.80, round(0.30 + 0.10 * count + 0.20 * freq, 3))

                _, _, norm_val, label, _ = cls.normalize_preference(
                    PreferenceCategory.LOCATION, "location", loc
                )

                inferred.append(
                    ResearcherPreferenceItemSchema(
                        id=uuid.uuid5(profile.id, f"inferred_loc_{norm_val}"),
                        profile_id=profile.id,
                        category=PreferenceCategory.LOCATION.value,
                        preference_key="location",
                        preference_value=norm_val,
                        display_label=label,
                        strength=strength,
                        confidence=confidence,
                        source=PreferenceSource.INFERRED.value,
                        is_active=True,
                        recency_score=recency,
                        provenance={
                            "match_count": count,
                            "total_saved": total_saved,
                            "frequency": round(freq, 3),
                        },
                        provenance_reasons=[
                            f"{count} saved opportunities were located in {label}"
                        ],
                        last_observed_at=latest_dt,
                    )
                )

        return inferred

    # -------------------------------------------------------------------------
    # Derived Candidates (Bootstrap from Phase 3.2 Scholarly Expertise)
    # -------------------------------------------------------------------------

    @classmethod
    def get_derived_candidates(
        cls,
        db: Session,
        profile: ResearchProfileModel,
    ) -> list[ResearcherPreferenceItemSchema]:
        """
        Generate candidate preference suggestions from scholarly expertise (Phase 3.2).

        Strict Boundary:
          - CRITICAL INVARIANT: Expertise != Preference.
          - These are NEVER automatically explicit preferences.
          - Labeled source = DERIVED_FROM_EXPERTISE.
          - Confidence is intentionally bounded at 0.45 (weaker than explicit/inferred).
        """
        stmt = (
            select(ResearcherInterestModel)
            .where(ResearcherInterestModel.profile_id == profile.id)
            .order_by(ResearcherInterestModel.strength.desc())
        )
        interests = list(db.execute(stmt).scalars().all())

        # Fallback to canonical researcher id if profile has none directly
        if not interests and profile.canonical_researcher_id:
            stmt = (
                select(ResearcherInterestModel)
                .where(ResearcherInterestModel.canonical_researcher_id == profile.canonical_researcher_id)
                .order_by(ResearcherInterestModel.strength.desc())
            )
            interests = list(db.execute(stmt).scalars().all())

        candidates: list[ResearcherPreferenceItemSchema] = []
        for interest in interests:
            # Only consider substantial expertise
            if interest.classification in ("PRIMARY_EXPERTISE", "SECONDARY_EXPERTISE") or interest.strength >= 0.50:
                # Discounted strength: 70% of interest strength
                cand_strength = min(1.0, max(0.1, round(0.70 * interest.strength, 3)))

                candidates.append(
                    ResearcherPreferenceItemSchema(
                        id=uuid.uuid5(profile.id, f"derived_topic_{interest.topic_slug}"),
                        profile_id=profile.id,
                        category=PreferenceCategory.TOPIC.value,
                        preference_key="topic",
                        preference_value=interest.topic_slug,
                        display_label=interest.topic_name,
                        canonical_id=interest.topic_id,
                        strength=cand_strength,
                        confidence=0.45,  # Deliberately lower confidence because expertise != preference
                        source=PreferenceSource.DERIVED_FROM_EXPERTISE.value,
                        is_active=True,
                        recency_score=interest.recency_score,
                        provenance={
                            "derived_from_interest_id": str(interest.id),
                            "original_interest_strength": interest.strength,
                            "classification": interest.classification,
                        },
                        provenance_reasons=[
                            f"Derived from scholarly expertise in {interest.topic_name} ({interest.classification}, strength {interest.strength:.2f})"
                        ],
                        last_observed_at=interest.updated_at,
                    )
                )

        return candidates

    # -------------------------------------------------------------------------
    # Contradiction & Conflict Detection
    # -------------------------------------------------------------------------

    @classmethod
    def detect_conflicts(
        cls,
        preferences: Sequence[ResearcherPreferenceItemSchema | ResearcherPreferenceModel],
    ) -> list[PreferenceConflictSchema]:
        """
        Deterministically detect contradictory preferences across active preference items.
        Returns a list of structured conflicts.
        """
        conflicts: list[PreferenceConflictSchema] = []

        # 1. Contradictory Open Access
        oa_values = {
            p.preference_value.lower()
            for p in preferences
            if p.is_active and p.category == PreferenceCategory.OPEN_ACCESS.value
        }
        if "true" in oa_values and "false" in oa_values:
            conflicts.append(
                PreferenceConflictSchema(
                    category=PreferenceCategory.OPEN_ACCESS.value,
                    conflicting_values=["true", "false"],
                    reason="Contradictory Open Access requirements (both 'true' and 'false' preferences are active).",
                    is_critical=True,
                )
            )

        # 2. Contradictory Deadline Windows
        deadline_prefs = [
            p
            for p in preferences
            if p.is_active and p.category == PreferenceCategory.DEADLINE_WINDOW.value
        ]
        if len(deadline_prefs) > 1:
            values = [p.preference_value for p in deadline_prefs]
            int_values = []
            for v in values:
                try:
                    int_values.append(int(v))
                except ValueError:
                    pass
            if len(int_values) > 1 and max(int_values) - min(int_values) >= 14:
                conflicts.append(
                    PreferenceConflictSchema(
                        category=PreferenceCategory.DEADLINE_WINDOW.value,
                        conflicting_values=values,
                        reason=f"Divergent deadline preparation windows specified ({min(int_values)} days vs {max(int_values)} days).",
                        is_critical=False,
                    )
                )

        # 3. Contradictory Delivery Mode Exclusions (if conflicting explicit preferences with high strength)
        mode_prefs = [
            p
            for p in preferences
            if p.is_active and p.category == PreferenceCategory.DELIVERY_MODE.value
        ]
        explicit_modes = [p for p in mode_prefs if p.source == PreferenceSource.EXPLICIT.value]
        # If user explicitly marked both OFFLINE and ONLINE with strong opposing flags or explicit contradictions
        if len(explicit_modes) > 1:
            vals = {p.preference_value for p in explicit_modes}
            if "ONLINE" in vals and "OFFLINE" in vals and "HYBRID" not in vals:
                conflicts.append(
                    PreferenceConflictSchema(
                        category=PreferenceCategory.DELIVERY_MODE.value,
                        conflicting_values=list(vals),
                        reason="Both strictly Online and strictly In-Person formats are explicitly preferred without Hybrid participation.",
                        is_critical=False,
                    )
                )

        return conflicts

    # -------------------------------------------------------------------------
    # Preference Completeness Calculation
    # -------------------------------------------------------------------------

    @classmethod
    def calculate_completeness(
        cls,
        explicit_prefs: Sequence[Any],
        inferred_prefs: Sequence[Any],
        profile: ResearchProfileModel,
    ) -> PreferenceCompletenessSchema:
        """
        Evaluate coverage across core preference dimensions.

        Dimensions:
          - opportunity_type: weight 0.25
          - delivery_mode:    weight 0.20
          - topic:            weight 0.25
          - deadline:         weight 0.15
          - location_access:  weight 0.15
        Total = 1.00 (100%)
        """
        all_active = [p for p in explicit_prefs if p.is_active] + [p for p in inferred_prefs if p.is_active]
        active_cats = {p.category for p in all_active}

        breakdown: dict[str, bool] = {
            "opportunity_type": (
                PreferenceCategory.OPPORTUNITY_TYPE.value in active_cats
                or bool(profile.target_opportunity_types)
            ),
            "delivery_mode": PreferenceCategory.DELIVERY_MODE.value in active_cats,
            "topic": (
                PreferenceCategory.TOPIC.value in active_cats
                or bool(profile.keywords)
            ),
            "deadline": PreferenceCategory.DEADLINE_WINDOW.value in active_cats,
            "location_or_access": (
                PreferenceCategory.LOCATION.value in active_cats
                or PreferenceCategory.OPEN_ACCESS.value in active_cats
            ),
        }

        weights = {
            "opportunity_type": 0.25,
            "delivery_mode": 0.20,
            "topic": 0.25,
            "deadline": 0.15,
            "location_or_access": 0.15,
        }

        score = sum(weights[dim] for dim, present in breakdown.items() if present)
        score = round(min(1.0, max(0.0, score)), 2)
        percentage = int(round(score * 100))

        missing = [dim.replace("_", " ").title() for dim, present in breakdown.items() if not present]

        return PreferenceCompletenessSchema(
            score=score,
            percentage=percentage,
            is_complete=(score >= 0.85),
            missing_dimensions=missing,
            dimension_breakdown=breakdown,
        )

    # -------------------------------------------------------------------------
    # Aggregate Preference Intelligence
    # -------------------------------------------------------------------------

    @classmethod
    def get_preference_intelligence(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> ResearcherPreferenceIntelligenceResponse:
        """
        Generate complete, structured preference intelligence for a researcher.

        Aggregates:
          - Explicit declared preferences
          - Inferred preferences from platform activity
          - Candidate preferences derived from scholarly expertise
          - Contradiction / conflict analysis
          - Completeness assessment

        Strict Boundaries:
          - Zero candidate recommendations
          - Zero ranking alterations
          - Zero LLM calls
        """
        profile = db.get(ResearchProfileModel, profile_id)
        if not profile:
            raise ValueError(f"Researcher profile {profile_id} does not exist")

        # 1. Fetch persisted explicit preferences (eager loaded, single query)
        stmt_explicit = (
            select(ResearcherPreferenceModel)
            .where(
                ResearcherPreferenceModel.profile_id == profile_id,
                ResearcherPreferenceModel.source == PreferenceSource.EXPLICIT.value,
            )
            .order_by(
                ResearcherPreferenceModel.strength.desc(),
                ResearcherPreferenceModel.confidence.desc(),
            )
        )
        explicit_models = list(db.execute(stmt_explicit).scalars().all())

        explicit_items = [
            ResearcherPreferenceItemSchema(
                id=m.id,
                profile_id=m.profile_id,
                category=m.category,
                preference_key=m.preference_key,
                preference_value=m.preference_value,
                display_label=m.display_label,
                canonical_id=m.canonical_id,
                strength=m.strength,
                confidence=m.confidence,
                source=m.source,
                is_active=m.is_active,
                recency_score=m.recency_score,
                provenance=m.provenance,
                provenance_reasons=(m.provenance or {}).get("reasons", ["Explicit declaration"]),
                last_observed_at=m.last_observed_at,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in explicit_models
        ]

        # 2. Compute inferred preferences from platform activity (SavedOpportunityModel)
        inferred_items = cls.infer_preferences_from_activity(db, profile)

        # 3. Compute derived candidate suggestions from scholarly expertise (Phase 3.2)
        derived_items = cls.get_derived_candidates(db, profile)

        # 4. Check for conflicts
        all_for_conflict: list[Any] = explicit_items + inferred_items
        conflicts = cls.detect_conflicts(all_for_conflict)

        # If conflicts exist, halve confidence of affected inferred items
        if conflicts:
            conflicting_cats = {c.category for c in conflicts}
            for inf in inferred_items:
                if inf.category in conflicting_cats:
                    inf.confidence = round(inf.confidence * 0.5, 3)

        # 5. Completeness
        completeness = cls.calculate_completeness(explicit_items, inferred_items, profile)

        # 6. Summary metrics
        total_prefs = len(explicit_items) + len(inferred_items)
        has_conflicts = len(conflicts) > 0

        if len(explicit_items) >= 3 and not has_conflicts:
            confidence_level = "HIGH"
        elif total_prefs > 0:
            confidence_level = "MEDIUM"
        else:
            confidence_level = "LOW"

        summary = PreferenceIntelligenceSummarySchema(
            total_preferences=total_prefs,
            explicit_count=len(explicit_items),
            inferred_count=len(inferred_items),
            derived_count=len(derived_items),
            has_conflicts=has_conflicts,
            confidence_level=confidence_level,
            completeness_percentage=completeness.percentage,
        )

        display_name = profile.user.full_name if (profile.user and profile.user.full_name) else "Researcher"

        return ResearcherPreferenceIntelligenceResponse(
            profile_id=profile.id,
            user_id=profile.user_id,
            display_name=display_name,
            explicit_preferences=explicit_items,
            inferred_preferences=inferred_items,
            derived_candidates=derived_items,
            conflicts=conflicts,
            completeness=completeness,
            summary=summary,
            generated_at=datetime.now(timezone.utc),
        )
