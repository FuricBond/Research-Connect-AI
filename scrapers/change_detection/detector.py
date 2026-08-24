"""
Change detection engine for scraped opportunities.

Compares an existing OpportunityModel (or dictionary representation) with a
newly scraped NormalizedOpportunity to detect meaningful field changes.
"""
from __future__ import annotations

import logging
from typing import Any

from scrapers.models import ChangeDetectionResult, FieldChange, NormalizedOpportunity

logger = logging.getLogger(__name__)

# Fields evaluated for meaningful modifications
TRACKED_FIELDS = [
    "title",
    "opportunity_type",
    "publisher",
    "organizer",
    "summary",
    "description",
    "website_url",
    "delivery_mode",
    "location",
    "submission_deadline",
    "event_start_date",
    "event_end_date",
    "indexing",
    "apc_or_fee",
]


def detect_changes(existing: Any, incoming: NormalizedOpportunity) -> ChangeDetectionResult:
    """
    Compare an existing opportunity entity/model with an incoming NormalizedOpportunity.

    Args:
        existing: SQLAlchemy OpportunityModel or dict containing current DB state.
        incoming: NormalizedOpportunity with latest scraped data.

    Returns:
        ChangeDetectionResult containing `has_changed` boolean and list of `FieldChange`.
    """
    changes: list[FieldChange] = []

    for field_name in TRACKED_FIELDS:
        if isinstance(existing, dict):
            current_val = existing.get(field_name)
        else:
            current_val = getattr(existing, field_name, None)

        incoming_val = getattr(incoming, field_name, None)

        # Normalize comparisons for empty strings/None or collections
        if current_val != incoming_val:
            # Special case: don't overwrite existing non-null fields with incoming None
            # (e.g. detailed fields not present on list-page scrapers)
            if incoming_val is None and current_val is not None:
                continue

            changes.append(
                FieldChange(
                    field_name=field_name,
                    old_value=current_val,
                    new_value=incoming_val,
                )
            )

    has_changed = len(changes) > 0
    if has_changed:
        logger.debug(
            "Change detected for %r: %s",
            incoming.title,
            ", ".join(f"{c.field_name}: {c.old_value!r} -> {c.new_value!r}" for c in changes),
        )

    return ChangeDetectionResult(has_changed=has_changed, changes=changes)
