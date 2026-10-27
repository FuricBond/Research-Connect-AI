"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import { Plus } from "lucide-react";
import { AuthPending } from "../auth/RequireAuth";
import { useSession } from "../auth/SessionProvider";
import { NEW_POSTING_HREF } from "../../utils/postings";
import { ButtonLink } from "../ui/Button/Button";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { EmptyState } from "../ui/State/State";
import { DashboardModule } from "./Module";
import { NeedsAttention } from "./NeedsAttention";
import { NeedsDecision } from "./NeedsDecision";
import { OpenPostings } from "./OpenPostings";
import { PostingsThatFit } from "./PostingsThatFit";
import { ReadingProgress } from "./ReadingProgress";
import { RecommendedForYou } from "./RecommendedForYou";
import { RecommendedPapers } from "./RecommendedPapers";
import { callDeadlines, calendarEvents, postingDeadlines, Upcoming } from "./Upcoming";
import {
  UPCOMING_DAYS,
  useApplicationSummary,
  useCalendarWindow,
  useMyPostings,
  useReadingCounts,
  useRecommendations,
  useTrackedCalls,
} from "./resources";
import styles from "./Dashboard.module.css";

/**
 * P10: an administrator's home, the administration overview (utils/navigation.ts "Overview"). A
 * literal: importing the navigation's config or utils/admin here would add their code to this page.
 */
const ADMIN_HOME_HREF = "/admin";

const DESCRIPTION = {
  STUDENT: "What needs your attention, what is new for you, and what is coming up.",
  FACULTY: "Applications waiting for you, your open postings, and what is coming up.",
} as const;

/**
 * P4 — the signed-in home (`/dashboard`, FRONTEND_REDESIGN_PLAN.md §8): student and faculty
 * modules, each loading and failing on its own, at most seven requests (see resources.ts).
 * P10: an administrator's home is the administration overview (plan §8), so /dashboard — where
 * signing in lands — takes them there, replacing itself in the history.
 */
export function Dashboard() {
  const { user, role, profileId } = useSession();
  if (user === null || role === null) return null;
  if (role === "ADMIN") return <AdminHome />;
  return (
    <div className={styles.page}>
      <PageHeader
        display
        title={<>Welcome back, {user.full_name.trim() || "researcher"}</>}
        description={DESCRIPTION[role]}
        // P9: the recruiting home's one main action.
        actions={
          role === "FACULTY" && (
            <ButtonLink href={NEW_POSTING_HREF} variant="primary" leadingIcon={<Plus size={16} aria-hidden="true" />}>
              New posting
            </ButtonLink>
          )
        }
      />
      {role === "STUDENT" && <StudentDashboard profileId={profileId} />}
      {role === "FACULTY" && <FacultyDashboard profileId={profileId} />}
    </div>
  );
}

function StudentDashboard({ profileId }: { profileId: string | null }) {
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
      </div>
    </div>
  );
}

function FacultyDashboard({ profileId }: { profileId: string | null }) {
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

/** A legacy account without a researcher profile: the profile-based modules say why they are empty. */
function NoProfile({ id, title }: { id: string; title: string }) {
  return (
    <DashboardModule id={id} title={title} reserve="timeline">
      <EmptyState bare headingLevel={3} title="This needs a researcher profile." description="Your account has no researcher profile yet." />
    </DashboardModule>
  );
}

function AdminHome() {
  const router = useRouter();
  useEffect(() => {
    router.replace(ADMIN_HOME_HREF);
  }, [router]);
  return (
    <>
      <AuthPending label="Opening the administration overview…" />
      <p className={styles.reason}>
        <Link href={ADMIN_HOME_HREF}>Go to the administration overview</Link>
      </p>
    </>
  );
}
