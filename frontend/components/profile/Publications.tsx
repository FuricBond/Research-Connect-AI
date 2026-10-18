"use client";

import { useState } from "react";
import type { ApiResource } from "../../hooks/useApiResource";
import type { ResearcherProfile, ResearcherWorkSummary } from "../../types/researcher";
import { Button } from "../ui/Button/Button";
import { SkeletonList } from "../ui/State/State";
import styles from "./Profile.module.css";

/** Publications listed before "Show all": enough to recognise them, short enough to keep the page to three screens. */
const SHOWN = 5;

/**
 * The researcher's publications (plan §12), linked through their ORCID or OpenAlex identity: the
 * title, year, author position, citations and DOI. Asked for only once the profile is linked.
 */
export function Publications({ profile, works }: { profile: ResearcherProfile; works: ApiResource<ResearcherWorkSummary[]> }) {
  const [all, setAll] = useState(false);
  const linked = Boolean(profile.canonical_researcher_id);
  const list = works.data ?? [];
  const shown = all ? list : list.slice(0, SHOWN);

  return (
    <section className={styles.card} aria-labelledby="publications-heading">
      <div className={styles.cardHead}>
        <h2 id="publications-heading" className={styles.cardTitle}>
          Publications
        </h2>
        {linked && works.status === "success" && list.length > 0 && <span className={styles.muted}>{profile.works_count > list.length ? `${list.length} of ${profile.works_count}` : list.length}</span>}
      </div>
      {!linked ? (
        <p className={styles.muted}>
          {profile.orcid || profile.openalex_id
            ? "Your identifiers are recorded; your publications are linked at the next synchronisation."
            : "Add an ORCID iD or OpenAlex author ID to your profile and your publications are linked here."}
        </p>
      ) : works.status === "loading" || works.status === "idle" ? (
        <SkeletonList rows={3} label="Loading your publications" announce={false} />
      ) : works.status === "error" ? (
        <div className={styles.completeness}>
          <p className={styles.muted}>Your publications could not be loaded.</p>
          <div>
            <Button variant="secondary" size="sm" onClick={works.retry}>
              Try again
            </Button>
          </div>
        </div>
      ) : list.length === 0 ? (
        <p className={styles.muted}>No publications are linked to your scholarly record yet.</p>
      ) : (
        <>
          <ol className={styles.rows}>
            {shown.map((work) => (
              <li key={work.id} className={styles.row}>
                <h3 className={styles.rowTitle}>{work.title}</h3>
                <span className={styles.rowMeta}>
                  {work.publication_year && <span>{work.publication_year}</span>}
                  {work.author_position && <span>{work.author_position.charAt(0).toUpperCase() + work.author_position.slice(1)} author</span>}
                  <span>
                    {work.cited_by_count} citation{work.cited_by_count === 1 ? "" : "s"}
                  </span>
                  {work.doi && (
                    <a className={styles.link} href={`https://doi.org/${work.doi}`} target="_blank" rel="noopener noreferrer">
                      DOI<span className="rc-visually-hidden"> for {work.title} (opens in new tab)</span>
                    </a>
                  )}
                </span>
              </li>
            ))}
          </ol>
          {list.length > SHOWN && (
            <div>
              <Button variant="link" size="sm" aria-expanded={all} onClick={() => setAll(!all)}>
                {all ? "Show fewer" : `Show all ${list.length}`}
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
