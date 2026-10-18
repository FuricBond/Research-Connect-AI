import { Unlock } from "lucide-react";
import type { ResearchWorkRead } from "../../types/discovery";
import { cx } from "../../utils/cx";
import { bareDoi, citationsLabel, doiHref, workTypeLabel } from "../../utils/research";
import styles from "./Research.module.css";

/**
 * A paper's bibliographic facts in one row: "Journal article · 217 citations · Open access ·
 * doi:10.1109/…" (DESIGN_SYSTEM.md §9). Only what the API returned; a missing fact is left out,
 * never filled in.
 */
export function CitationMetadata({ work, showYear = false, className }: { work: ResearchWorkRead; showYear?: boolean; className?: string }) {
  const type = workTypeLabel(work.work_type);
  const citations = citationsLabel(work.cited_by_count);
  const doi = bareDoi(work.doi);
  const facts = [type, showYear && work.publication_year ? String(work.publication_year) : null, citations].filter(Boolean) as string[];
  if (facts.length === 0 && !work.is_oa && !doi) return null;
  return (
    <p className={cx(styles.facts, className)}>
      {facts.map((fact) => (
        <span key={fact} className={styles.fact}>
          {fact}
        </span>
      ))}
      {work.is_oa && (
        <span className={cx(styles.fact, styles.openAccess)}>
          <Unlock size={13} aria-hidden="true" />
          Open access
        </span>
      )}
      {doi && (
        <a className={cx(styles.fact, styles.doi)} href={doiHref(doi)} target="_blank" rel="noopener noreferrer">
          doi:{doi}
          <span className="rc-visually-hidden"> (opens in new tab)</span>
        </a>
      )}
    </p>
  );
}
