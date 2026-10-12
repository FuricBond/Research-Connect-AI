"use client";

import Link from "next/link";
import type { SimilarResearchItem } from "../../types/discovery";
import { EmptyState } from "../ui/State/State";
import { DashboardModule, Loaded, ModuleError, ModuleLoading } from "./Module";
import { useNewestWork, useSimilarPapers } from "./resources";
import styles from "./Dashboard.module.css";

/**
 * Faculty "Recommended papers" (plan §8). No endpoint recommends papers (recommendations are
 * calls), so these are the papers most similar to the researcher's newest paper: their works
 * (newest first, one) and then that paper's similar papers — the module's one dependent request.
 */
export function RecommendedPapers({ profileId }: { profileId: string }) {
  const works = useNewestWork(profileId);
  const newest = works.data?.[0] ?? null;
  const similar = useSimilarPapers(newest?.id ?? null);

  return (
    <DashboardModule id="dashboard-papers" title="Recommended papers" action={<Link href="/">Search papers</Link>} reserve="timeline">
      <Loaded resource={works} loading="Loading your papers" failure="Your papers could not be loaded.">
        {(data) => {
          if (data.length === 0) {
            return (
              <EmptyState
                bare
                variant="first-use"
                headingLevel={3}
                title="No papers of yours yet."
                description={
                  <>
                    Papers related to your work appear once your publications are on your <Link href="/researcher">researcher profile</Link>.
                  </>
                }
              />
            );
          }
          if (similar.status === "idle" || similar.status === "loading") return <ModuleLoading label="Finding related papers" />;
          if (similar.status === "error") return <ModuleError message="Related papers could not be found." resource={similar} />;
          const papers = similar.data?.items ?? [];
          return (
            <>
              <p className={styles.reason}>
                Related to your paper “{data[0].title}”{data[0].publication_year ? ` (${data[0].publication_year})` : ""}.
              </p>
              {papers.length === 0 ? (
                <EmptyState bare variant="done" headingLevel={3} title="No related papers found yet." description="New papers are compared as they arrive." />
              ) : (
                <ul className={styles.list}>
                  {papers.slice(0, 3).map((paper) => (
                    <Paper key={paper.work.id} paper={paper} />
                  ))}
                </ul>
              )}
            </>
          );
        }}
      </Loaded>
    </DashboardModule>
  );
}

function Paper({ paper }: { paper: SimilarResearchItem }) {
  const { work } = paper;
  const href = work.doi ? `https://doi.org/${work.doi.replace(/^https?:\/\/(dx\.)?doi\.org\//, "")}` : `/?q=${encodeURIComponent(work.title)}`;
  const external = href.startsWith("https://");
  return (
    <li className={styles.item}>
      {external ? (
        <a href={href} className={styles.itemTitle} target="_blank" rel="noopener noreferrer">
          {work.title}
          <span className="rc-visually-hidden"> (opens in a new tab)</span>
        </a>
      ) : (
        <Link href={href} className={styles.itemTitle}>
          {work.title}
        </Link>
      )}
      <div className={styles.meta}>
        {work.publication_year && <span>{work.publication_year}</span>}
        {typeof work.cited_by_count === "number" && (
          <span>
            {work.cited_by_count} citation{work.cited_by_count === 1 ? "" : "s"}
          </span>
        )}
      </div>
      {paper.shared_topic_names.length > 0 && <p className={styles.reason}>Shared topics: {paper.shared_topic_names.slice(0, 3).join(", ")}</p>}
    </li>
  );
}
