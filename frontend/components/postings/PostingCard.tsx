"use client";

import Link from "next/link";
import { useId } from "react";
import { Trash2 } from "lucide-react";
import type { PostingFit, PostingStatus, ResearchPosting } from "../../types/posting";
import { POSTING_STATUS_LABELS, POSTING_TYPE_LABELS, WORK_MODE_LABELS } from "../../types/posting";
import { postingStatusMeta } from "../../utils/status";
import { DeadlineCountdown } from "../research/DeadlineCountdown";
import { FitScore } from "../research/FitScore";
import { TopicTags } from "../research/TopicTags";
import { Badge, StatusBadge } from "../ui/Badge/Badge";
import { Button } from "../ui/Button/Button";
import styles from "./PostingCard.module.css";

export interface PostingCardProps {
  posting: ResearchPosting;
  /** Shown only to the author: lifecycle controls driven by `allowed_transitions`. */
  showOwnerControls?: boolean;
  onTransition?: (posting: ResearchPosting, target: PostingStatus) => void;
  onDelete?: (posting: ResearchPosting) => void;
  busy?: boolean;
  /** Phase 5.15: the signed-in student's fit, when one was computed. */
  fit?: PostingFit | null;
  /** P9: false in the editor's preview, where the posting has no page yet. */
  linkTitle?: boolean;
}

/**
 * A research posting in a list (DESIGN_SYSTEM.md §9 PostingCard): the category, the status and
 * the deadline in the header row; the serif title linking to the posting; author · institution ·
 * location · mode · positions; for a student, the fit in the API's words with its strongest
 * reason (a partial or low fit says what would raise it); a two-line summary and skill chips.
 * The author's lifecycle controls follow the server's allowed transitions. The deadline's words
 * come from the server's day count, so the urgency shown is the urgency the API reported.
 */
export function PostingCard({ posting, showOwnerControls = false, onTransition, onDelete, busy = false, fit = null, linkTitle = true }: PostingCardProps) {
  const titleId = `posting-${useId()}`;
  const place = posting.location || posting.country || null;
  const facts = [
    posting.author.full_name,
    posting.institution,
    place ? `${place} · ${WORK_MODE_LABELS[posting.work_mode]}` : WORK_MODE_LABELS[posting.work_mode],
    `${posting.positions_available} position${posting.positions_available === 1 ? "" : "s"}`,
  ].filter(Boolean);

  return (
    <article className={styles.card} aria-labelledby={titleId}>
      <div className={styles.top}>
        <Badge tone="neutral">{POSTING_TYPE_LABELS[posting.posting_type]}</Badge>
        <StatusBadge meta={postingStatusMeta(posting.status)} />
        <DeadlineCountdown deadline={posting.application_deadline} daysRemaining={posting.days_until_deadline} />
      </div>

      <h3 className={styles.title}>
        {linkTitle ? (
          <Link id={titleId} href={`/postings/${posting.id}`} className={styles.titleLink}>
            {posting.title}
          </Link>
        ) : (
          <span id={titleId}>{posting.title}</span>
        )}
      </h3>
      <p className={styles.facts}>{facts.join(" · ")}</p>

      {/* No score means nothing was recorded to compare: the card says nothing rather than repeat it on every posting. */}
      {fit && fit.score !== null && <FitScore score={fit.score} band={fit.band} reason={fit.reasons[0]?.label ?? null} gaps={fit.gaps} />}

      {posting.summary && <p className={styles.summary}>{posting.summary}</p>}

      {posting.required_skills.length > 0 && <TopicTags topics={posting.required_skills.slice(0, 8)} label={`Skills for ${posting.title}`} />}

      {showOwnerControls && posting.is_owner && (
        <div className={styles.actions}>
          {posting.allowed_transitions.map((target) => (
            <Button key={target} variant={target === "OPEN" ? "primary" : "secondary"} size="sm" disabled={busy} aria-describedby={titleId} onClick={() => onTransition?.(posting, target)}>
              {target === "OPEN" ? "Publish" : `Mark ${POSTING_STATUS_LABELS[target].toLowerCase()}`}
            </Button>
          ))}
          {posting.status === "DRAFT" && onDelete && (
            <Button variant="danger-ghost" size="sm" disabled={busy} aria-describedby={titleId} leadingIcon={<Trash2 size={16} aria-hidden="true" />} onClick={() => onDelete(posting)}>
              Delete draft
            </Button>
          )}
        </div>
      )}
    </article>
  );
}
