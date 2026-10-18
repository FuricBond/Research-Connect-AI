"use client";

import { useId, useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { deleteRecommendationFeedback, recordRecommendationFeedback } from "../../services/api";
import type { OpportunityListItem, OpportunityType } from "../../types/opportunity";
import type { FeedbackType, PersonalizedCandidateOpportunity, PersonalizedRankedCandidate } from "../../types/researcher";
import type { WorkspaceItem } from "../../types/workspace";
import { withoutMark } from "../../utils/personalization";
import { MatchScore } from "../research/MatchScore";
import { OpportunityCard } from "../research/OpportunityCard";
import { Button } from "../ui/Button/Button";
import styles from "./Recommendations.module.css";

/** A recommended call in the shape the shared call card reads; only what the API sent, nothing filled in. */
export function toCall(opportunity: PersonalizedCandidateOpportunity): OpportunityListItem {
  return {
    id: opportunity.id,
    title: opportunity.title,
    opportunity_type: opportunity.opportunity_type as OpportunityType,
    publisher: null,
    organizer: opportunity.organizer ?? null,
    summary: null,
    delivery_mode: opportunity.delivery_mode as OpportunityListItem["delivery_mode"],
    location: opportunity.location ?? null,
    submission_deadline: opportunity.submission_deadline ?? null,
    event_start_date: null,
    event_end_date: null,
    indexing: null,
    website_url: opportunity.website_url ?? null,
    submission_url: null,
    is_predatory_flag: opportunity.is_predatory_flag,
    risk_score: opportunity.risk_score ?? null,
    risk_level: opportunity.risk_level ?? null,
    risk_confidence: null,
    deadline_intelligence: null,
    status: opportunity.status as OpportunityListItem["status"],
    created_at: "",
    updated_at: "",
  };
}

type Given = { type: FeedbackType; id: string } | null;

const LABELS: Partial<Record<FeedbackType, string>> = { INTERESTED: "Helpful", NOT_INTERESTED: "Not relevant" };

/**
 * "Helpful" / "Not relevant" (plan §12): recommendation feedback (Phase 3.6), recorded as coming
 * from the recommendations with the item's rank, and undone by deleting it. It shapes later rankings
 * while feedback learning is on. The confirmation is announced politely; a failure says so.
 */
function FeedbackControls({ profileId, opportunityId, rank, titleId }: { profileId: string; opportunityId: string; rank: number; titleId: string }) {
  const [given, setGiven] = useState<Given>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const give = async (type: FeedbackType) => {
    if (busy || given?.type === type) return;
    setBusy(true);
    try {
      if (given) await deleteRecommendationFeedback(profileId, given.id);
      const item = await recordRecommendationFeedback(profileId, { opportunity_id: opportunityId, feedback_type: type, source: "RECOMMENDATION", rank_position: rank });
      setGiven({ type, id: item.id });
      setMessage(`Marked ${LABELS[type]?.toLowerCase()}. Your feedback shapes later recommendations.`);
    } catch {
      setMessage("Your feedback could not be saved. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const undo = async () => {
    if (!given || busy) return;
    setBusy(true);
    try {
      await deleteRecommendationFeedback(profileId, given.id);
      setGiven(null);
      setMessage("Feedback removed.");
    } catch {
      setMessage("Your feedback could not be removed. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.feedback} role="group" aria-label="Feedback" aria-describedby={titleId}>
      {(["INTERESTED", "NOT_INTERESTED"] as const).map((type) => (
        <Button
          key={type}
          variant="ghost"
          size="sm"
          aria-pressed={given?.type === type}
          disabled={busy}
          leadingIcon={type === "INTERESTED" ? <ThumbsUp size={16} aria-hidden="true" /> : <ThumbsDown size={16} aria-hidden="true" />}
          onClick={() => give(type)}
        >
          {LABELS[type]}
        </Button>
      ))}
      {given && (
        <Button variant="link" size="sm" onClick={undo} disabled={busy}>
          Undo
        </Button>
      )}
      <span role="status" className={styles.feedbackMessage}>
        {message}
      </span>
    </div>
  );
}

interface RecommendationCardProps {
  item: PersonalizedRankedCandidate;
  profileId: string;
  saved: boolean;
  onSaved: (item: WorkspaceItem) => void;
  onExplain: (item: PersonalizedRankedCandidate) => void;
}

/**
 * A recommended call (DESIGN_SYSTEM.md §9 RecommendationCard): the shared call card — type and
 * venue risk, the title linking to the call's page, deadline, Save (which, from this feed, is
 * also a "saved" interaction) — with a reason strip: the match band, the API's main reason and
 * "Why this match?", then Helpful / Not relevant.
 */
export function RecommendationCard({ item, profileId, saved, onSaved, onExplain }: RecommendationCardProps) {
  const titleId = `recommendation-${useId()}`;
  const first = item.explanation?.primary_reasons?.[0] ?? item.provenance?.reasons?.[0] ?? null;
  const reason = first ? withoutMark(first) : null;
  return (
    <OpportunityCard
      call={toCall(item.opportunity)}
      titleId={titleId}
      rank={item.rank}
      saved={saved}
      onSaved={onSaved}
      interactionProfileId={profileId}
      evidence={
        <>
          <MatchScore score={item.final_score} kind="match" />
          {reason && <span className={styles.reason}>{reason}</span>}
          <button type="button" className={styles.why} aria-haspopup="dialog" onClick={() => onExplain(item)}>
            Why this match?<span className="rc-visually-hidden"> {item.opportunity.title}</span>
          </button>
        </>
      }
      actionsExtra={<FeedbackControls profileId={profileId} opportunityId={item.opportunity_id} rank={item.rank} titleId={titleId} />}
    />
  );
}
