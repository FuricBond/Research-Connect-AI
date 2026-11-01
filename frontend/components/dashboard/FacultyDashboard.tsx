"use client";

import Link from "next/link";
import { NeedsDecision } from "./NeedsDecision";
import { NoProfile } from "./NoProfile";
import { OpenPostings } from "./OpenPostings";
import { RecommendedPapers } from "./RecommendedPapers";
import { callDeadlines, postingDeadlines, Upcoming } from "./Upcoming";
import { useMyPostings, useTrackedCalls } from "./resources";
import styles from "./Dashboard.module.css";

/** The faculty member's modules (plan §8). */
export function FacultyDashboard({ profileId }: { profileId: string | null }) {
  const calls = useTrackedCalls();
  const mine = useMyPostings();

  return (
    <div className={styles.grid}>
      <div className={styles.column}>
        <NeedsDecision mine={mine} />
        <OpenPostings mine={mine} />
      </div>
      <div className={styles.column}>
        <Upcoming
          title="Upcoming deadlines"
          first={{ resource: calls, failure: "Your tracked calls could not be loaded." }}
          second={{ resource: mine, failure: "Your postings could not be loaded." }}
          build={(workspace, postings) => [...(workspace ? callDeadlines(workspace) : []), ...(postings ? postingDeadlines(postings) : [])]}
          emptyDescription={
            <>
              Deadlines of the <Link href="/browse">calls you save</Link> and of your open postings appear here.
            </>
          }
        />
        {profileId ? <RecommendedPapers profileId={profileId} /> : <NoProfile id="dashboard-papers" title="Recommended papers" />}
      </div>
    </div>
  );
}
