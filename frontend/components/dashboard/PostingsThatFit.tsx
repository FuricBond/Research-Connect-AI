"use client";

import Link from "next/link";
import { useMemo, type ReactNode } from "react";
import type { PostingFit, ResearchPosting } from "../../types/posting";
import { DeadlineCountdown } from "../research/DeadlineCountdown";
import { MatchScore } from "../research/MatchScore";
import { EmptyState } from "../ui/State/State";
import { DashboardModule, Loaded, ModuleError, ModuleLoading } from "./Module";
import { useOpenPostings, usePostingFits } from "./resources";
import styles from "./Dashboard.module.css";

const SHOWN = 3;

/** The fit's strongest reason in words: "Topics: graph neural networks, explainability". */
function mainReason(fit: PostingFit): string | null {
  const [best] = [...fit.reasons].filter((reason) => reason.weight > 0).sort((a, b) => b.weight - a.weight);
  if (!best) return null;
  return best.matched.length > 0 ? `${best.label}: ${best.matched.slice(0, 3).join(", ")}` : best.label;
}

/**
 * Student "Postings that fit you" (plan §8): open postings that accept applications, scored for
 * this student in one batch (`POST /postings/fit-scores`, which needs the postings' ids — the
 * module's one dependent request), the best three shown with their fit and main reason.
 */
export function PostingsThatFit() {
  const postings = useOpenPostings();
  const ids = useMemo(() => (postings.data ? postings.data.postings.map((posting) => posting.id) : null), [postings.data]);
  const fits = usePostingFits(ids);

  const empty = (description: ReactNode) => (
    <EmptyState bare variant="first-use" headingLevel={3} title="No posting fits you yet." description={description} />
  );

  return (
    <DashboardModule id="dashboard-postings" title="Postings that fit you" action={<Link href="/postings">All postings</Link>} reserve="list">
      <Loaded resource={postings} loading="Loading open postings" failure="Open postings could not be loaded.">
        {(data) => {
          if (data.postings.length === 0) return empty("No research posting is open for applications right now.");
          if (fits.status === "idle" || fits.status === "loading") return <ModuleLoading label="Scoring postings for you" />;
          if (fits.status === "error") return <ModuleError message="How well postings fit you could not be worked out." resource={fits} />;
          const byId = new Map<string, ResearchPosting>(data.postings.map((posting) => [posting.id, posting]));
          const best = (fits.data?.fits ?? [])
            .filter((fit) => fit.score !== null && byId.has(fit.posting_id))
            .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
            .slice(0, SHOWN);
          if (best.length === 0) {
            return empty(
              <>
                Fit comes from your topics and skills. <Link href="/researcher?section=interests">Add your research interests</Link>.
              </>
            );
          }
          return (
            <ul className={styles.list}>
              {best.map((fit) => {
                const posting = byId.get(fit.posting_id)!;
                const reason = mainReason(fit);
                return (
                  <li key={posting.id} className={styles.item}>
                    <Link href={`/postings/${posting.id}`} className={styles.itemTitle}>
                      {posting.title}
                    </Link>
                    <div className={styles.meta}>
                      <MatchScore score={fit.score} kind="fit" />
                      {posting.application_deadline && (
                        <DeadlineCountdown deadline={posting.application_deadline} daysRemaining={posting.days_until_deadline} />
                      )}
                      {posting.author.full_name && <span>{posting.author.full_name}</span>}
                    </div>
                    {reason && <p className={styles.reason}>{reason}</p>}
                  </li>
                );
              })}
            </ul>
          );
        }}
      </Loaded>
    </DashboardModule>
  );
}
