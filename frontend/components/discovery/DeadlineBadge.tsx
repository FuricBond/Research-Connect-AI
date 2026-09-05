"use client";

import React from "react";
import { AlertTriangle, ArrowUpRight, Calendar, Clock, History, Info } from "lucide-react";
import type { OpportunityDeadline } from "../../types/opportunity";
import { formatDeadlineDate } from "../../utils/date";

interface DeadlineBadgeProps {
  deadlineIntelligence?: OpportunityDeadline | null;
  fallbackDeadline?: string | null;
  onInspectDeadlines?: () => void;
  showInspectButton?: boolean;
}

export const DeadlineBadge: React.FC<DeadlineBadgeProps> = ({
  deadlineIntelligence,
  fallbackDeadline,
  onInspectDeadlines,
  showInspectButton = true,
}) => {
  // Case 1: Structured Deadline Intelligence available (Phase 2.7F)
  if (deadlineIntelligence && deadlineIntelligence.primary_view) {
    const pv = deadlineIntelligence.primary_view;
    const norm = pv.canonical_deadline;
    const ass = pv.canonical_assessment;
    const isConflict = pv.conflict_state === "SOURCE_CONFLICT";
    const isSuperseded = pv.conflict_state === "SUPERSEDED";
    const isExtended =
      deadlineIntelligence.has_extension ||
      pv.latest_revision?.classification === "EXTENDED";

    // Format localized date and timezone safely without client-side day shifting
    let dateStr = "";
    if (norm?.local_date) {
      dateStr = norm.local_date;
      if (norm.timezone_name) {
        dateStr += ` ${norm.timezone_name}`;
      }
    } else if (fallbackDeadline) {
      dateStr = formatDeadlineDate(fallbackDeadline);
    }

    // Determine status text and urgency styling
    let labelText = "Deadline unknown";
    let urgencyClass = "urgency-unknown";
    let statusIcon = <Clock size={13} className="badge-icon" />;

    if (isConflict) {
      labelText = "Conflicting sources (unresolved)";
      urgencyClass = "deadline-conflict";
      statusIcon = <AlertTriangle size={13} className="badge-icon icon-conflict" />;
    } else if (ass) {
      switch (ass.status) {
        case "DUE_TODAY":
          urgencyClass = "urgency-due-today";
          labelText = `Due today! (${ass.hours_remaining ? `${Math.round(ass.hours_remaining)}h left` : "urgent"})`;
          statusIcon = <Clock size={13} className="badge-icon icon-critical" />;
          break;
        case "UPCOMING":
          if (ass.urgency_tier === "CRITICAL") {
            urgencyClass = "urgency-critical";
            statusIcon = <Clock size={13} className="badge-icon icon-critical" />;
          } else if (ass.urgency_tier === "URGENT") {
            urgencyClass = "urgency-urgent";
            statusIcon = <Clock size={13} className="badge-icon icon-urgent" />;
          } else if (ass.urgency_tier === "APPROACHING") {
            urgencyClass = "urgency-approaching";
            statusIcon = <Calendar size={13} className="badge-icon icon-approaching" />;
          } else {
            urgencyClass = "urgency-distant";
            statusIcon = <Calendar size={13} className="badge-icon icon-distant" />;
          }

          if (ass.days_remaining !== null && ass.days_remaining !== undefined) {
            const days = Math.round(ass.days_remaining);
            labelText = `${dateStr} (${days}d left)`;
          } else {
            labelText = dateStr || "Upcoming";
          }
          break;
        case "EXPIRED":
          urgencyClass = "urgency-expired";
          labelText = `Expired ${dateStr ? `(${dateStr})` : ""}`;
          statusIcon = <History size={13} className="badge-icon icon-expired" />;
          break;
        case "MISSING":
        default:
          urgencyClass = "urgency-unknown";
          labelText = "Deadline unknown";
          statusIcon = <Info size={13} className="badge-icon icon-unknown" />;
          break;
      }
    }

    const extensionDays = pv.latest_revision?.days_diff;
    const extensionBadge = isExtended ? (
      <span
        className="deadline-extension-pill"
        title={pv.extension_reason || "Deadline extended"}
      >
        <ArrowUpRight size={11} />
        {extensionDays ? `+${Math.round(extensionDays)}d` : "Extended"}
      </span>
    ) : null;

    const supersededBadge = isSuperseded ? (
      <span
        className="deadline-superseded-pill"
        title={pv.source_selection_reason || "Authoritative source supersedes earlier aggregator date"}
      >
        Verified
      </span>
    ) : null;

    return (
      <div
        className={`deadline-badge-wrapper ${urgencyClass}`}
        role={onInspectDeadlines ? "button" : "status"}
        tabIndex={onInspectDeadlines ? 0 : undefined}
        onClick={onInspectDeadlines}
        onKeyDown={(e) => {
          if (onInspectDeadlines && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            onInspectDeadlines();
          }
        }}
        aria-label={`Deadline status: ${labelText}${isExtended ? " (Extended)" : ""}`}
        title="Click to view full deadline intelligence & milestone timeline"
      >
        <div className="deadline-badge-main">
          {statusIcon}
          <span className="deadline-badge-text">{labelText}</span>
          {extensionBadge}
          {supersededBadge}
        </div>

        {showInspectButton && onInspectDeadlines && (
          <span className="deadline-inspect-hint" aria-hidden="true">
            Timeline
          </span>
        )}
      </div>
    );
  }

  // Case 2: Backward-compatible fallback when structured intelligence is not yet loaded
  if (fallbackDeadline) {
    const formatted = formatDeadlineDate(fallbackDeadline);
    return (
      <div
        className="deadline-badge-wrapper urgency-approaching fallback-mode"
        role={onInspectDeadlines ? "button" : "status"}
        tabIndex={onInspectDeadlines ? 0 : undefined}
        onClick={onInspectDeadlines}
        aria-label={`Submission deadline: ${formatted}`}
      >
        <div className="deadline-badge-main">
          <Clock size={13} className="badge-icon" />
          <span className="deadline-badge-text">Due {formatted}</span>
        </div>
        {showInspectButton && onInspectDeadlines && (
          <span className="deadline-inspect-hint" aria-hidden="true">
            Details
          </span>
        )}
      </div>
    );
  }

  // Case 3: No deadline specified
  return (
    <div className="deadline-badge-wrapper urgency-unknown">
      <div className="deadline-badge-main">
        <Clock size={13} className="badge-icon icon-unknown" />
        <span className="deadline-badge-text">Deadline unknown</span>
      </div>
    </div>
  );
};

