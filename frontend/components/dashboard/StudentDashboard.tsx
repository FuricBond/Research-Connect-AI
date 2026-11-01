"use client";

import Link from "next/link";
import { useMemo } from "react";
import { LatestNotifications } from "./LatestNotifications";
import { NeedsAttention } from "./NeedsAttention";
import { NoProfile } from "./NoProfile";
import { PostingsThatFit } from "./PostingsThatFit";
import { ReadingProgress } from "./ReadingProgress";
import { RecommendedForYou } from "./RecommendedForYou";
import { callDeadlines, calendarEvents, Upcoming } from "./Upcoming";
import { UPCOMING_DAYS, useApplicationSummary, useCalendarWindow, useReadingCounts, useRecommendations, useTrackedCalls } from "./resources";
import styles from "./Dashboard.module.css";

/** The student's modules (plan §8). */
export function StudentDashboard({ profileId }: { profileId: string | null }) {
  const calls = useTrackedCalls();
  const applications = useApplicationSummary();
  const calendar = useCalendarWindow(profileId);
  const recommendations = useRecommendations(profileId);
  const reading = useReadingCounts();
  const tracked = useMemo(() => new Set(calls.data?.items.map((item) => item.opportunity_id) ?? []), [calls.data]);

  return (
    <div className={styles.grid}>
      <div className={styles.column}>
        <NeedsAttention calls={calls} applications={applications} recommendations={recommendations} reading={reading} />
        <Upcoming
          title={`Upcoming (next ${UPCOMING_DAYS} days)`}
          first={{ resource: calls, failure: "Your tracked calls could not be loaded." }}
          second={{ resource: calendar, failure: "Your calendar could not be loaded." }}
          build={(workspace, events) => [...(workspace ? callDeadlines(workspace) : []), ...(events ? calendarEvents(events, tracked) : [])]}
          emptyDescription={
            <>
              <Link href="/browse">Save calls for papers</Link> or add milestones to your <Link href="/calendar">calendar</Link>.
            </>
          }
        />
      </div>
      <div className={styles.column}>
        {profileId ? <RecommendedForYou recommendations={recommendations} profileId={profileId} /> : <NoProfile id="dashboard-recommended" title="Recommended for you" />}
        <PostingsThatFit />
        <ReadingProgress reading={reading} />
        <LatestNotifications />
      </div>
    </div>
  );
}
