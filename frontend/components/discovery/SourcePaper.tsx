"use client";

import { useId, useState, type ReactNode, type RefObject } from "react";
import type { ResearchWorkRead } from "../../types/discovery";
import { CitationMetadata } from "../research/CitationMetadata";
import styles from "./PaperTools.module.css";

/**
 * The chosen paper at the top of a paper-based page (plan §10): its title, facts and a collapsed
 * abstract, and the page's way to the other tool. Without the paper's details (a shared link this
 * tab never saw) it says so instead of inventing them.
 */
export function SourcePaper({ work, headingRef, action }: { work: ResearchWorkRead | null; headingRef: RefObject<HTMLHeadingElement | null>; action?: ReactNode }) {
  const abstractId = useId();
  const [open, setOpen] = useState(false);
  const abstract = work?.abstract?.trim();

  return (
    <section className={styles.source} aria-labelledby={`${abstractId}-title`}>
      <p className={styles.sourceLabel}>Chosen paper</p>
      <h2 id={`${abstractId}-title`} ref={headingRef} tabIndex={-1} className={styles.sourceTitle}>
        {work?.title ?? "A paper chosen elsewhere"}
      </h2>
      {work ? (
        <>
          <CitationMetadata work={work} showYear />
          {abstract && (
            <div className={styles.abstractBlock}>
              <p id={abstractId} className={open ? styles.abstract : styles.abstractClamped}>
                {abstract}
              </p>
              <button type="button" className={styles.toggle} aria-expanded={open} aria-controls={abstractId} onClick={() => setOpen((value) => !value)}>
                {open ? "Hide abstract" : "Show abstract"}
              </button>
            </div>
          )}
        </>
      ) : (
        <p className={styles.note}>
          This paper was not opened in this tab, so its title and abstract are not available here (papers can only be looked up from a search). Its
          results are below.
        </p>
      )}
      {action && <div className={styles.sourceActions}>{action}</div>}
    </section>
  );
}
