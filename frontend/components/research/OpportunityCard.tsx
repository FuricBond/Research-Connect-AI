"use client";

import Link from "next/link";
import { useId } from "react";
import { ExternalLink } from "lucide-react";
import type { ExplanationSchema } from "../../types/discovery";
import type { OpportunityListItem } from "../../types/opportunity";
import type { WorkspaceItem } from "../../types/workspace";
import { callTypeLabel, deliveryModeLabel, topReasons } from "../../utils/research";
import { riskPresentation } from "../../utils/risk";
import { workspaceDeadline } from "../../utils/workspace";
import { Badge } from "../ui/Badge/Badge";
import { DeadlineCountdown } from "./DeadlineCountdown";
import { MatchScore } from "./MatchScore";
import { RiskIndicator } from "./RiskIndicator";
import { SaveCallButton } from "./SaveCallButton";
import type { EvidenceSection } from "./EvidencePanel";
import styles from "./OpportunityCard.module.css";

export function callHref(id: string): string {
  return `/calls/${encodeURIComponent(id)}`;
}

interface OpportunityCardProps {
  call: OpportunityListItem;
  /** Venue matching: the call's rank and score for the chosen paper, and its explanation. */
  match?: {
    rank: number;
    score: number;
    explanation: ExplanationSchema | null;
    onExplain: (section: EvidenceSection) => void;
  };
  saved?: boolean;
  onSaved?: (item: WorkspaceItem) => void;
  /** Called as the title's link is followed (to remember the way back). */
  onFollow?: () => void;
}

/**
 * A call for papers in a list (DESIGN_SYSTEM.md §9 OpportunityCard): the type and the venue risk
 * in the header row (risk in the trust slot, top right), the serif title linking to the call's
 * page, organiser · location · attendance, the deadline in words, the indexes it is listed in, a
 * two-line summary and quiet actions — Save to workspace, Source. In venue matching it also
 * carries the match band, its reasons and "Why this venue?". Deadline and risk never look alike.
 * `opportunity-card` stays on the element as a stable hook for tests.
 */
export function OpportunityCard({ call, match, saved = false, onSaved, onFollow }: OpportunityCardProps) {
  const titleId = `call-${useId()}`;
  const deadline = workspaceDeadline(call);
  const facts = [call.organizer || call.publisher, call.location, deliveryModeLabel(call.delivery_mode)].filter(Boolean).join(" · ");
  const indexing = (call.indexing ?? []).filter((name) => typeof name === "string" && name.trim());
  const risk = riskPresentation(call.risk_level, { isPredatory: call.is_predatory_flag });
  const reasons = match ? topReasons(match.explanation) : [];

  return (
    <article className={`${styles.card} opportunity-card`} aria-labelledby={titleId}>
      <div className={styles.top}>
        <div className={styles.kind}>
          {match && <span className={styles.rank}>{match.rank}.</span>}
          <Badge tone="neutral">{callTypeLabel(call.opportunity_type)}</Badge>
        </div>
        {match ? (
          <button
            type="button"
            className={styles.riskButton}
            aria-haspopup="dialog"
            aria-label={`Venue risk: ${risk.label}. Show the evidence`}
            onClick={() => match.onExplain("risk")}
          >
            <RiskIndicator level={call.risk_level} isPredatory={call.is_predatory_flag} />
          </button>
        ) : (
          <RiskIndicator level={call.risk_level} isPredatory={call.is_predatory_flag} />
        )}
      </div>

      <h3 className={styles.title}>
        <Link id={titleId} href={callHref(call.id)} className={styles.titleLink} onClick={onFollow}>
          {call.title}
        </Link>
      </h3>
      {facts && <p className={styles.facts}>{facts}</p>}

      <div className={styles.deadline}>
        <DeadlineCountdown deadline={deadline.deadline} daysRemaining={deadline.daysRemaining} status={deadline.status} urgencyTier={deadline.urgencyTier} />
        {match && (
          <button type="button" className={styles.link} aria-haspopup="dialog" onClick={() => match.onExplain("deadline")}>
            All dates<span className="rc-visually-hidden"> for {call.title}</span>
          </button>
        )}
      </div>

      {match && (
        <div className={styles.evidence}>
          <MatchScore score={match.score} kind="match" />
          {reasons.length > 0 && <span className={styles.reasons}>{reasons.join(" · ")}</span>}
          <button type="button" className={styles.link} aria-haspopup="dialog" onClick={() => match.onExplain("match")}>
            Why this venue?<span className="rc-visually-hidden"> {call.title}</span>
          </button>
        </div>
      )}

      {indexing.length > 0 && <p className={styles.indexing}>Indexed in {indexing.join(", ")}</p>}
      {call.summary && <p className={styles.summary}>{call.summary}</p>}

      <div className={styles.actions}>
        <SaveCallButton opportunityId={call.id} isSaved={saved} onSaved={onSaved} describedBy={titleId} />
        {call.website_url && (
          <a href={call.website_url} className={styles.action} target="_blank" rel="noopener noreferrer" aria-describedby={titleId}>
            <ExternalLink size={16} aria-hidden="true" />
            Source
            <span className="rc-visually-hidden"> (opens in new tab)</span>
          </a>
        )}
      </div>
    </article>
  );
}
