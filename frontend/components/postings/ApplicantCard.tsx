"use client";

import { useId, useRef, useState } from "react";
import { ExternalLink, Mail } from "lucide-react";
import type { ApplicationStatus, PostingApplication } from "../../types/posting";
import { academicStatusLabel } from "../../utils/personalization";
import { applicationOutcome, decisionsFor, NOT_SELECTED, webAddress } from "../../utils/postings";
import { applicationStatusMeta } from "../../utils/status";
import { StatusBadge } from "../ui/Badge/Badge";
import { Button } from "../ui/Button/Button";
import { Alert } from "../ui/State/State";
import { dateTime, shortDate } from "../workspace/workflow";
import { NotSelectedDialog } from "./lazy";
import type { DecisionFailure } from "./useApplicationDecisions";
import styles from "./Faculty.module.css";

/** A statement longer than this, or of more than four lines, starts clamped. */
const LONG_NOTE = 320;

export interface ApplicantCardProps {
  /** As the server last confirmed it (useApplicationDecisions().current). */
  application: PostingApplication;
  /** A decision on it is being sent: its actions wait. */
  pending: boolean;
  decide: (application: PostingApplication, target: ApplicationStatus, options?: { decisionReason?: string }) => Promise<boolean>;
  /** The latest failed decision, when it was this application's. */
  failure: DecisionFailure | null;
  onDismissFailure: () => void;
}

/**
 * P9 — one application as its posting's author reviews it (DESIGN_SYSTEM.md §9 ApplicationCard,
 * faculty): the applicant, their level and institution, the status in words, when they applied,
 * how to reach them, their statement (four lines, then "Show the whole statement"), the message
 * shared with them and the private note. Decisions follow the review pipeline — Mark under review
 * → Shortlist → Make offer — with one primary, and "Not selected" last, after a confirmation;
 * only the moves the server lists for this application are offered. The API gives the author no
 * fit for an applicant, so none is shown.
 */
export function ApplicantCard({ application, pending, decide, failure, onDismissFailure }: ApplicantCardProps) {
  const nameId = `applicant-${useId()}`;
  const heading = useRef<HTMLHeadingElement>(null);
  const [confirming, setConfirming] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const name = application.applicant.full_name ?? "Unnamed applicant";
  const decisions = decisionsFor(application);
  const outcome = applicationOutcome(application.status);
  const facts = [academicStatusLabel(application.applicant.academic_status), application.applicant.institution, application.applicant.department].filter(Boolean);
  const portfolio = webAddress(application.portfolio_url);
  const note = application.cover_note?.trim() ?? "";
  const long = note.length > LONG_NOTE || note.split("\n").length > 4;
  const mine = failure && failure.application.id === application.id ? failure : null;

  return (
    <article className={styles.applicant} aria-labelledby={nameId}>
      <div className={styles.applicantHead}>
        <h3 id={nameId} ref={heading} tabIndex={-1} className={styles.applicantName}>
          {name}
        </h3>
        <StatusBadge meta={applicationStatusMeta(application.status)} />
      </div>
      {facts.length > 0 && <p className={styles.facts}>{facts.join(" · ")}</p>}
      <p className={styles.facts}>
        Applied {shortDate(application.submitted_at) ?? "on an unknown date"}
        {application.decided_at ? ` · last decision ${shortDate(application.decided_at)}` : ""}
      </p>

      {(application.contact_email || application.portfolio_url) && (
        <p className={styles.contacts}>
          {application.contact_email && (
            <a href={`mailto:${application.contact_email}`} className={styles.contact}>
              <Mail size={16} aria-hidden="true" />
              {application.contact_email}
            </a>
          )}
          {portfolio ? (
            <a href={portfolio} target="_blank" rel="noopener noreferrer" className={styles.contact}>
              <ExternalLink size={16} aria-hidden="true" />
              CV or portfolio<span className="rc-visually-hidden"> of {name} (opens in a new tab)</span>
            </a>
          ) : (
            application.portfolio_url && <span className={styles.facts}>CV or portfolio: {application.portfolio_url}</span>
          )}
        </p>
      )}

      {note ? (
        <div className={styles.statement}>
          <p className={styles.statementLabel}>Statement of interest</p>
          <p className={long && !expanded ? styles.statementClamped : styles.statementText}>{note}</p>
          {long && (
            <Button variant="link" size="sm" aria-expanded={expanded} aria-describedby={nameId} onClick={() => setExpanded((open) => !open)}>
              {expanded ? "Show less" : "Show the whole statement"}
            </Button>
          )}
        </div>
      ) : (
        <p className={styles.facts}>No statement of interest was given.</p>
      )}

      {application.decision_reason && (
        <p className={styles.shared}>
          <span className={styles.sharedLabel}>Message to the applicant: </span>
          {application.decision_reason}
        </p>
      )}
      {application.reviewer_note && (
        <p className={styles.private}>
          <span className={styles.sharedLabel}>Private note (never shown to the applicant): </span>
          {application.reviewer_note}
        </p>
      )}

      {outcome && <p className={styles.outcome}>{outcome}</p>}

      {decisions.length > 0 && (
        <div className={styles.decisions} role="group" aria-label={`Decisions on ${name}`}>
          {decisions.map((decision) => (
            <Button
              key={decision.target}
              size="sm"
              variant={decision.variant}
              disabled={pending}
              aria-describedby={nameId}
              onClick={() => {
                if (decision.confirm) {
                  onDismissFailure();
                  setConfirming(true);
                  return;
                }
                void decide(application, decision.target).then(() => {
                  // The button used was disabled while waiting (which drops focus) and may be gone with
                  // the new status: if focus was lost, the applicant's name takes it.
                  window.setTimeout(() => {
                    if (document.activeElement === document.body || document.activeElement === null) heading.current?.focus();
                  }, 0);
                });
              }}
            >
              {decision.label}
            </Button>
          ))}
          {pending && (
            <span className={styles.saving} role="status">
              Saving…
            </span>
          )}
        </div>
      )}

      {mine && !confirming && (
        <Alert tone="danger" announce>
          {mine.message} It is still {applicationStatusMeta(application.status).label.toLowerCase()}.
        </Alert>
      )}

      {application.status_history.length > 0 && (
        <details className={styles.history}>
          <summary className={styles.historySummary}>
            History ({application.status_history.length})<span className="rc-visually-hidden"> of {name}</span>
          </summary>
          <ol className={styles.historyList}>
            {application.status_history.map((event, index) => (
              <li key={`${event.at}-${index}`}>
                <span className={styles.historyWhen}>{dateTime(event.at) ?? "Unknown time"}</span>{" "}
                {event.from_status ? `${applicationStatusMeta(event.from_status).label} → ` : ""}
                {applicationStatusMeta(event.to_status).label}, by {event.actor_role === "APPLICANT" ? "the applicant" : "the posting’s author"}
                {event.reason ? `: ${event.reason}` : ""}
              </li>
            ))}
          </ol>
        </details>
      )}

      {confirming && (
        <NotSelectedDialog
          application={application}
          failure={mine?.target === NOT_SELECTED ? mine.message : null}
          onClose={() => setConfirming(false)}
          onConfirm={async (message) => {
            const agreed = await decide(application, NOT_SELECTED, { decisionReason: message });
            // The button that opened the dialog is gone with the decision: the applicant's name takes focus.
            if (agreed) window.setTimeout(() => heading.current?.focus(), 0);
            return agreed;
          }}
        />
      )}
    </article>
  );
}
