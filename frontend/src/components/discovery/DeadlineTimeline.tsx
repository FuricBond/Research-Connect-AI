import React from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  Calendar,
  CheckCircle2,
  Clock,
  ExternalLink,
  History,
  ShieldCheck,
} from "lucide-react";
import type { CanonicalDeadlineView, DeadlineType } from "../../types/opportunity";

interface DeadlineTimelineProps {
  milestoneViews: Record<string, CanonicalDeadlineView>;
  primaryMilestone?: DeadlineType | string;
}

// Canonical academic lifecycle ordering
const MILESTONE_ORDER: { type: DeadlineType; label: string; description: string }[] = [
  { type: "ABSTRACT", label: "Abstract Due", description: "Mandatory abstract registration" },
  { type: "SUBMISSION", label: "Paper Submission", description: "Full manuscript submission cutoff" },
  { type: "NOTIFICATION", label: "Notification", description: "Author acceptance / rejection notification" },
  { type: "CAMERA_READY", label: "Camera-Ready", description: "Final publication-ready version" },
  { type: "REGISTRATION", label: "Registration", description: "Author attendance registration deadline" },
  { type: "EVENT_START", label: "Event Convenes", description: "Conference / session opening date" },
  { type: "EVENT_END", label: "Event Concludes", description: "Conference conclusion date" },
];

export const DeadlineTimeline: React.FC<DeadlineTimelineProps> = ({
  milestoneViews,
  primaryMilestone = "SUBMISSION",
}) => {
  // Only display milestones that have views present in the backend response
  const activeMilestones = MILESTONE_ORDER.filter(
    (m) => milestoneViews[m.type] !== undefined
  );

  // If other unlisted milestones are in views, append them
  const knownKeys = new Set(MILESTONE_ORDER.map((m) => m.type as string));
  const additionalKeys = Object.keys(milestoneViews).filter((k) => !knownKeys.has(k));

  if (activeMilestones.length === 0 && additionalKeys.length === 0) {
    return (
      <div className="timeline-empty-state">
        <Clock size={16} className="text-muted" />
        <span>No milestone timeline data available for this opportunity.</span>
      </div>
    );
  }

  return (
    <div className="deadline-timeline-container" role="list" aria-label="Academic Publication Timeline">
      {activeMilestones.map((meta) => {
        const view = milestoneViews[meta.type];
        return renderMilestoneItem(meta.type, meta.label, meta.description, view, primaryMilestone);
      })}

      {additionalKeys.map((key) => {
        const view = milestoneViews[key];
        const formattedLabel = key.replace(/_/g, " ").toLowerCase();
        return renderMilestoneItem(
          key as DeadlineType,
          formattedLabel.charAt(0).toUpperCase() + formattedLabel.slice(1),
          "Supplementary milestone",
          view,
          primaryMilestone
        );
      })}
    </div>
  );
};

function renderMilestoneItem(
  type: DeadlineType | string,
  label: string,
  description: string,
  view: CanonicalDeadlineView,
  primaryMilestone: DeadlineType | string
) {
  const isPrimary = type === primaryMilestone;
  const norm = view.canonical_deadline;
  const ass = view.canonical_assessment;
  const isConflict = view.conflict_state === "SOURCE_CONFLICT";
  const isSuperseded = view.conflict_state === "SUPERSEDED";
  const isExtended = view.latest_revision?.classification === "EXTENDED";

  // Timezone-safe local date string
  let displayDate = "Not specified";
  if (norm?.local_date) {
    displayDate = norm.local_date;
    if (norm.timezone_name) {
      displayDate += ` ${norm.timezone_name}`;
    }
  }

  // Urgency & Status Classes
  let statusBadgeClass = "status-unknown";
  let statusText = "Unknown";
  let statusIcon = <Clock size={14} />;

  if (isConflict) {
    statusBadgeClass = "status-conflict";
    statusText = "Conflict";
    statusIcon = <AlertTriangle size={14} className="text-conflict" />;
  } else if (ass) {
    switch (ass.status) {
      case "UPCOMING":
        statusBadgeClass = `status-${ass.urgency_tier.toLowerCase()}`;
        statusText = ass.days_remaining !== null && ass.days_remaining !== undefined
          ? `${Math.round(ass.days_remaining)}d left`
          : "Upcoming";
        statusIcon = <Calendar size={14} />;
        break;
      case "DUE_TODAY":
        statusBadgeClass = "status-due-today";
        statusText = ass.hours_remaining ? `${Math.round(ass.hours_remaining)}h left` : "Due today";
        statusIcon = <Clock size={14} />;
        break;
      case "EXPIRED":
        statusBadgeClass = "status-expired";
        statusText = "Elapsed";
        statusIcon = <History size={14} />;
        break;
      case "MISSING":
      default:
        statusBadgeClass = "status-missing";
        statusText = "Unspecified";
        statusIcon = <Clock size={14} />;
        break;
    }
  }

  // Confidence label
  const confVal = view.confidence;
  const confLabel =
    confVal >= 0.85
      ? "High confidence"
      : confVal >= 0.50
      ? "Moderate confidence"
      : confVal > 0.0
      ? "Low confidence"
      : "Insufficient evidence";

  return (
    <div
      key={type}
      className={`timeline-milestone-item ${isPrimary ? "is-primary-milestone" : ""}`}
      role="listitem"
    >
      <div className="timeline-node-column">
        <div className={`timeline-node-dot ${statusBadgeClass}`}>
          {isConflict ? <AlertTriangle size={10} /> : <div className="dot-inner" />}
        </div>
        <div className="timeline-connector-line" />
      </div>

      <div className="timeline-content-card">
        <div className="timeline-header-row">
          <div className="milestone-title-group">
            <h4 className="milestone-label">
              {label}
              {isPrimary && <span className="primary-pill">Primary</span>}
            </h4>
            <span className="milestone-desc">{description}</span>
          </div>

          <div className="milestone-status-group">
            <span className={`milestone-status-pill ${statusBadgeClass}`}>
              {statusIcon}
              <span>{statusText}</span>
            </span>
          </div>
        </div>

        <div className="timeline-details-row">
          <div className="timeline-date-display">
            <strong>{displayDate}</strong>
          </div>

          {view.selected_source && (
            <div className="timeline-source-tag" title={`Source: ${view.selected_source} (${confLabel})`}>
              <ShieldCheck size={12} />
              <span>{view.selected_source}</span>
            </div>
          )}

          {isExtended && view.latest_revision && (
            <span className="timeline-extension-chip" title={view.extension_reason || "Deadline extended"}>
              <ArrowUpRight size={11} />
              <span>+{Math.round(view.latest_revision.days_diff || 0)}d Extended</span>
            </span>
          )}

          {isSuperseded && (
            <span className="timeline-superseded-chip" title={view.source_selection_reason || "Authoritative source"}>
              Superseded
            </span>
          )}

          {isConflict && (
            <span className="timeline-conflict-chip" title={view.conflict_reason || "Multiple sources disagree"}>
              <AlertTriangle size={11} />
              <span>Disputed</span>
            </span>
          )}
        </div>

        {view.explanation && (
          <p className="timeline-explanation-text">{view.explanation}</p>
        )}
      </div>
    </div>
  );
}
