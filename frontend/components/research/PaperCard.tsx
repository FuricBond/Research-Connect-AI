"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { Compass, Megaphone } from "lucide-react";
import type { ResearchWorkRead } from "../../types/discovery";
import { topReasons } from "../../utils/research";
import { SaveToReadingListButton } from "../reading-list/SaveToReadingListButton";
import { CitationMetadata } from "./CitationMetadata";
import { MatchScore } from "./MatchScore";
import { explainLabel, similarHref, venuesHref, type PaperItem } from "./paper";
import styles from "./PaperCard.module.css";

/** An abstract longer than this gets a "Show full abstract" control (two lines show by default). */
const ABSTRACT_TOGGLE_AT = 180;

interface PaperCardProps {
  item: PaperItem;
  /** The title opens the paper panel. */
  onOpen: (item: PaperItem) => void;
  /** "Why this result?" opens the Evidence panel. */
  onExplain: (item: PaperItem) => void;
  /** Called before "Find similar" or "Find venues" opens the paper-based page. */
  onChoose: (work: ResearchWorkRead) => void;
  saved?: boolean;
  onSaved?: (workId: string, itemId: string) => void;
}

/**
 * A paper in a list (DESIGN_SYSTEM.md §9): rank and serif title (it opens the paper panel), venue
 * and year, the citation facts, a two-line abstract, the evidence line — the relevance band, the
 * two strongest reasons in words and "Why this result?" — and quiet actions. No primary button:
 * a list of twenty cards has no twenty primary actions. `paper-card` stays as a stable hook.
 */
export function PaperCard({ item, onOpen, onExplain, onChoose, saved = false, onSaved }: PaperCardProps) {
  const { work, rank, score, scoreKind, explanation, sharedTopics, venue, context } = item;
  const titleId = `paper-${useId()}`;
  const abstractId = `${titleId}-abstract`;
  const [abstractOpen, setAbstractOpen] = useState(false);
  const reasons = topReasons(explanation);
  const where = [venue, work.publication_year ? String(work.publication_year) : null].filter(Boolean).join(" · ");
  const abstract = work.abstract?.trim();

  return (
    <article className={`${styles.card} paper-card`} aria-labelledby={titleId}>
      <h3 className={styles.heading}>
        <span className={styles.rank}>{rank}.</span>
        <button type="button" id={titleId} className={styles.title} aria-haspopup="dialog" onClick={() => onOpen(item)}>
          {work.title}
        </button>
      </h3>

      {where && <p className={styles.where}>{where}</p>}
      <CitationMetadata work={work} />

      {abstract ? (
        <div className={styles.abstractBlock}>
          <p id={abstractId} className={abstractOpen ? styles.abstract : styles.abstractClamped}>
            {abstract}
          </p>
          {abstract.length > ABSTRACT_TOGGLE_AT && (
            <button type="button" className={styles.toggle} aria-expanded={abstractOpen} aria-controls={abstractId} onClick={() => setAbstractOpen((open) => !open)}>
              {abstractOpen ? "Show less" : "Show full abstract"}
            </button>
          )}
        </div>
      ) : (
        <p className={styles.noAbstract}>No abstract available.</p>
      )}

      {sharedTopics.length > 0 && context === "similar" && (
        <p className={styles.topics}>
          <span className={styles.topicsLabel}>Shared topics:</span> {sharedTopics.slice(0, 4).join(" · ")}
        </p>
      )}

      <div className={styles.evidence}>
        <MatchScore score={score} kind={scoreKind} />
        {reasons.length > 0 && <span className={styles.reasons}>{reasons.join(" · ")}</span>}
        {explanation && (
          <button type="button" className={styles.why} aria-haspopup="dialog" onClick={() => onExplain(item)}>
            {explainLabel(context)}
            <span className="rc-visually-hidden"> {work.title}</span>
          </button>
        )}
      </div>

      <div className={styles.actions}>
        <SaveToReadingListButton workId={work.id} isSaved={saved} onSaved={onSaved} describedBy={titleId} />
        <Link href={similarHref(work.id)} className={styles.action} aria-describedby={titleId} onClick={() => onChoose(work)}>
          <Compass size={16} aria-hidden="true" />
          Find similar
        </Link>
        <Link href={venuesHref(work.id)} className={styles.action} aria-describedby={titleId} onClick={() => onChoose(work)}>
          <Megaphone size={16} aria-hidden="true" />
          Find venues
        </Link>
      </div>
    </article>
  );
}
