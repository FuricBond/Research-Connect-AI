"""
Phase 3.6 — Feedback & Recommendation Learning Configuration.

Centralizes all constants, event weights, decay parameters, saturation factors,
and guardrails governing deterministic behavioral learning.

Zero magic numbers across the codebase: all parameters are defined, documented,
and validated here.
"""
from __future__ import annotations

import math

# ── Event Types & Base Weights ────────────────────────────────────────────────
# Positive signals increase attribute preferences; negative signals decrease them.
# Scale: [-1.0, +1.0]

FEEDBACK_EVENT_WEIGHTS: dict[str, float] = {
    "VIEW": 0.05,            # Weak positive: Inspected opportunity details
    "SAVE": 0.25,            # Strong positive: Bookmarked for future action
    "INTERESTED": 0.30,      # Strong positive: Explicit endorsement ("thumbs up")
    "APPLY": 0.40,           # Strongest positive: Tracked submission / application
    "DISMISS": -0.20,        # Negative: Skipped / hidden from feed
    "NOT_INTERESTED": -0.30, # Strong negative: Explicit rejection ("thumbs down")
}

SUPPORTED_FEEDBACK_TYPES: tuple[str, ...] = tuple(FEEDBACK_EVENT_WEIGHTS.keys())
POSITIVE_FEEDBACK_TYPES: tuple[str, ...] = ("VIEW", "SAVE", "INTERESTED", "APPLY")
NEGATIVE_FEEDBACK_TYPES: tuple[str, ...] = ("DISMISS", "NOT_INTERESTED")

# ── Temporal Decay Parameters ─────────────────────────────────────────────────
# Deterministic exponential decay with 30-day half-life.
# lambda = ln(2) / T_half = 0.693147... / 30.0 ~= 0.023105
FEEDBACK_HALF_LIFE_DAYS: float = 30.0
TEMPORAL_DECAY_LAMBDA: float = math.log(2.0) / FEEDBACK_HALF_LIFE_DAYS

# Maximum age of feedback events considered for active behavioral learning (180 days)
MAX_FEEDBACK_HORIZON_DAYS: float = 180.0

# ── Diminishing Returns & Saturation ──────────────────────────────────────────
# Prevents runaway score growth from repeated interactions with the same opportunity or topic.
# effective_weight(k) = base_weight / (1.0 + DIMINISHING_RETURNS_GAMMA * (k - 1))
DIMINISHING_RETURNS_GAMMA: float = 0.50

# Per-opportunity cumulative weight cap (prevents multiple clicks on same opportunity inflating score)
MAX_OPPORTUNITY_CUMULATIVE_POSITIVE_WEIGHT: float = 0.50
MAX_OPPORTUNITY_CUMULATIVE_NEGATIVE_WEIGHT: float = -0.50

# ── Bounded Behavioral Contribution Limits ────────────────────────────────────
# Behavioral adjustments are strictly bounded and must never overpower Phase 3.5 ranking.
MAX_POSITIVE_BEHAVIORAL_ADJUSTMENT: float = 0.08
MAX_NEGATIVE_BEHAVIORAL_ADJUSTMENT: float = 0.15

# Phase 3.5 Personalization hard cap remains strictly <= 0.15
MAX_OVERALL_PERSONALIZATION_CAP: float = 0.15

# ── Confidence Scaling Parameters ─────────────────────────────────────────────
# Volume scaling: 1.0 - exp(-N / VOLUME_SCALE_N)
# N=1 -> ~0.28, N=3 -> ~0.63, N=5 -> ~0.81, N=10 -> ~0.96
CONFIDENCE_VOLUME_SCALE_N: float = 3.0

# Minimum confidence required before a learned signal is permitted to influence ranking
MIN_BEHAVIORAL_CONFIDENCE_THRESHOLD: float = 0.20

# High-confidence threshold
HIGH_BEHAVIORAL_CONFIDENCE_THRESHOLD: float = 0.70

# ── Explicit Preference Protection & Conflict Handling ────────────────────────
# Explicit preferences (Phase 3.3) are authoritative and inviolable.
# If an attribute has an active EXPLICIT preference, conflicting behavioral negative
# feedback is dampened so the explicit preference score never drops below this floor.
EXPLICIT_PREFERENCE_DOMINANCE_FLOOR: float = 0.50

# Maximum fraction by which behavioral negative feedback can dampen an explicit preference
MAX_BEHAVIORAL_DAMPENING_OF_EXPLICIT: float = 0.40

# ── Negative Signal Suppression ───────────────────────────────────────────────
# Opportunities with active negative feedback (DISMISS or NOT_INTERESTED)
# are suppressed from candidate generation within this window (days).
SUPPRESSION_TTL_DAYS: float = 90.0
