"use client";

/**
 * P0.3 — the signed-in home: a starting point, not a dashboard.
 *
 * It answers "what needs my attention" from data the API already provides (tracked calls with
 * a deadline in the next 30 days; application or posting status) and offers the way into each
 * area of the product. At most three requests, made in parallel; each section loads and fails
 * on its own. The unread notification count lives in the navigation and is not fetched again.
 */

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { RequireAuth } from "../../components/auth/RequireAuth";
import { useSession } from "../../components/auth/SessionProvider";
import { DeadlineCountdown } from "../../components/research/DeadlineCountdown";
import { RiskIndicator } from "../../components/research/RiskIndicator";
import { StatusBadge } from "../../components/ui/Badge/Badge";
import { Button } from "../../components/ui/Button/Button";
import { Card } from "../../components/ui/Card/Card";
import { PageHeader, SectionHeader } from "../../components/ui/PageHeader/PageHeader";
import { Alert, EmptyState, SkeletonList } from "../../components/ui/State/State";
import {
  fetchMyApplicationSummary,
  fetchMyPostingSummary,
  fetchReadingList,
  fetchWorkspaceItems,
} from "../../services/api";
import type { PlatformRole } from "../../types/auth";
import { ROLE_LABELS } from "../../types/auth";
import type { ApplicationSummaryResponse, PostingSummaryResponse } from "../../types/posting";
import type { ReadingListResponse } from "../../types/reading_list";
import type { WorkspaceListResponse } from "../../types/workspace";
import { humanizeEnum } from "../../utils/date";
import { riskPresentation } from "../../utils/risk";
import { workspaceStatusMeta } from "../../utils/status";
import { upcomingDeadlines, workspaceDeadline } from "../../utils/workspace";
import styles from "./home.module.css";

/** Deadlines further out than this are not "needs attention" yet. */
const ATTENTION_WINDOW_DAYS = 30;
const ATTENTION_ITEMS_SHOWN = 5;

type Loadable<T> = { state: "idle" } | { state: "loading" } | { state: "ready"; data: T } | { state: "failed" };

/** Runs `load` once when enabled (and again on retry); `load` must be a stable function. */
function useLoad<T>(load: (signal: AbortSignal) => Promise<T>, enabled = true): [Loadable<T>, () => void] {
  const [result, setResult] = useState<Loadable<T>>({ state: enabled ? "loading" : "idle" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!enabled) {
      setResult({ state: "idle" });
      return;
    }
    const controller = new AbortController();
    setResult({ state: "loading" });
    load(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setResult({ state: "ready", data });
      })
      .catch(() => {
        if (!controller.signal.aborted) setResult({ state: "failed" });
      });
    return () => controller.abort();
  }, [load, enabled, attempt]);
  return [result, () => setAttempt((n) => n + 1)];
}

const loadWorkspace = (signal: AbortSignal) =>
  fetchWorkspaceItems({ sort_by: "deadline", sort_order: "asc", limit: 100 }, undefined, signal);
const loadReadingList = (signal: AbortSignal) => fetchReadingList({ limit: 1 }, signal);

function HomePage() {
  const { user, role } = useSession();
  const [workspace, retryWorkspace] = useLoad<WorkspaceListResponse>(loadWorkspace);
  const [reading] = useLoad<ReadingListResponse>(loadReadingList);
  const [applications] = useLoad<ApplicationSummaryResponse>(fetchMyApplicationSummary, role === "STUDENT");
  const [postings] = useLoad<PostingSummaryResponse>(fetchMyPostingSummary, role === "FACULTY");

  return (
    <div className={styles.page}>
      <PageHeader
        display
        title={<>Welcome back, {user?.full_name?.trim() || "researcher"}</>}
        description={
          <>
            {role ? `${ROLE_LABELS[role]} account. ` : ""}
            Here is what needs your attention and where to pick up your work.
          </>
        }
      />

      <section aria-labelledby="home-attention">
        <SectionHeader id="home-attention" title="Needs attention" />
        <div className={styles.panels}>
          <Card>
            <h3 className={styles.panelTitle}>Deadlines in the next {ATTENTION_WINDOW_DAYS} days</h3>
            <AttentionDeadlines workspace={workspace} onRetry={retryWorkspace} />
          </Card>
          {role === "STUDENT" && <ApplicationStatus applications={applications} />}
          {role === "FACULTY" && <PostingStatus postings={postings} />}
        </div>
      </section>

      <section aria-labelledby="home-continue">
        <SectionHeader id="home-continue" title="Continue your work" />
        <ul className={`${styles.links} rc-grid`} style={{ ["--rc-grid-min" as string]: "15rem" }}>
          {destinationsFor(role, workspace, reading).map((link) => (
            <li key={link.href}>
              <Card variant="interactive" padding="compact" className={styles.card}>
                <Link href={link.href} className={styles.link}>
                  <span className={styles.linkTitle}>
                    {link.title}
                    <ArrowRight size={16} aria-hidden="true" />
                  </span>
                  <span className={styles.linkDescription}>{link.description}</span>
                </Link>
              </Card>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function AttentionDeadlines({ workspace, onRetry }: { workspace: Loadable<WorkspaceListResponse>; onRetry: () => void }) {
  if (workspace.state === "loading" || workspace.state === "idle") {
    return <SkeletonList rows={3} label="Loading your tracked calls" />;
  }
  if (workspace.state === "failed") {
    return (
      <Alert
        tone="danger"
        announce
        action={
          <Button size="sm" onClick={onRetry}>
            Try again
          </Button>
        }
      >
        Your tracked calls could not be loaded.
      </Alert>
    );
  }
  const upcoming = upcomingDeadlines(workspace.data.items, ATTENTION_WINDOW_DAYS);
  if (upcoming.length === 0) {
    return (
      <EmptyState
        bare
        variant="done"
        headingLevel={4}
        title={`No tracked call is due in the next ${ATTENTION_WINDOW_DAYS} days.`}
        description={
          <>
            <Link href="/browse">Browse calls for papers</Link> and save the ones you plan to submit to.
          </>
        }
      />
    );
  }
  return (
    <ul className="rc-ruled">
      {upcoming.slice(0, ATTENTION_ITEMS_SHOWN).map(({ item }) => {
        const deadline = workspaceDeadline(item.opportunity);
        const risk = riskPresentation(item.opportunity.risk_explanation?.risk_level, {
          isPredatory: item.opportunity.is_predatory_flag,
        });
        return (
          <li key={item.id} className={styles.deadline}>
            <Link href={`/workspace/${item.id}`} className={styles.deadlineTitle}>
              {item.opportunity.title}
            </Link>
            <div className={styles.meta}>
              <DeadlineCountdown
                deadline={deadline.deadline}
                daysRemaining={deadline.daysRemaining}
                status={deadline.status}
                urgencyTier={deadline.urgencyTier}
              />
              <StatusBadge meta={workspaceStatusMeta(item.status)} />
              {/* Only a concern is worth space here; "not assessed" stays on the workspace card. */}
              {(risk.tone === "high" || risk.tone === "caution") && (
                <RiskIndicator
                  level={item.opportunity.risk_explanation?.risk_level}
                  isPredatory={item.opportunity.is_predatory_flag}
                />
              )}
            </div>
          </li>
        );
      })}
      {upcoming.length > ATTENTION_ITEMS_SHOWN && (
        <li className={styles.more}>
          <Link href="/workspace">See all {upcoming.length} upcoming deadlines</Link>
        </li>
      )}
    </ul>
  );
}

function ApplicationStatus({ applications }: { applications: Loadable<ApplicationSummaryResponse> }) {
  if (applications.state !== "ready") return null;
  const { by_status: byStatus, active } = applications.data;
  const offers = byStatus.OFFERED ?? 0;
  let text: React.ReactNode;
  if (offers > 0) {
    text = (
      <>
        <strong>
          {offers} offer{offers === 1 ? "" : "s"} waiting for your reply.
        </strong>{" "}
        <Link href="/postings/applications">Review your applications</Link>
      </>
    );
  } else if (active > 0) {
    const parts = (["UNDER_REVIEW", "SHORTLISTED", "SUBMITTED"] as const)
      .filter((status) => (byStatus[status] ?? 0) > 0)
      .map((status) => `${byStatus[status]} ${humanizeEnum(status).toLowerCase()}`);
    text = (
      <>
        {active} application{active === 1 ? "" : "s"} in progress{parts.length ? ` (${parts.join(", ")})` : ""}.{" "}
        <Link href="/postings/applications">My applications</Link>
      </>
    );
  } else {
    text = (
      <>
        No applications in progress. <Link href="/postings">Find research postings</Link> that fit you.
      </>
    );
  }
  return (
    <Card>
      <h3 className={styles.panelTitle}>Applications</h3>
      <p className={styles.panelText}>{text}</p>
    </Card>
  );
}

function PostingStatus({ postings }: { postings: Loadable<PostingSummaryResponse> }) {
  if (postings.state !== "ready") return null;
  const { total, total_applications: received, open_accepting_applications: open } = postings.data;
  return (
    <Card>
      <h3 className={styles.panelTitle}>Your postings</h3>
      <p className={styles.panelText}>
        {total === 0 ? (
          <>
            You have no research postings yet. <Link href="/postings">Create one on Research Postings</Link>.
          </>
        ) : (
          <>
            {open} of {total} posting{total === 1 ? "" : "s"} open for applications · {received} application
            {received === 1 ? "" : "s"} received. <Link href="/postings">Manage your postings</Link>
          </>
        )}
      </p>
    </Card>
  );
}

interface Destination {
  href: string;
  title: string;
  description: string;
}

function destinationsFor(
  role: PlatformRole | null,
  workspace: Loadable<WorkspaceListResponse>,
  reading: Loadable<ReadingListResponse>
): Destination[] {
  const active = workspace.state === "ready" ? workspace.data.active_count : null;
  const counts = reading.state === "ready" ? reading.data.counts_by_status : null;
  const destinations: Destination[] = [
    {
      href: "/",
      title: "Literature Search",
      description: "Find papers by topic, method or author.",
    },
    {
      href: "/workspace",
      title: "Opportunity Workspace",
      description:
        active === null ? "Track the calls you plan to submit to." : `${active} active call${active === 1 ? "" : "s"} tracked.`,
    },
    {
      href: "/reading-list",
      title: "Reading List",
      description: counts
        ? `${counts.TO_READ} to read · ${counts.READING} reading · ${counts.DONE} done.`
        : "Papers you saved, with notes and BibTeX export.",
    },
    {
      href: "/researcher?section=recommendations",
      title: "Recommendations",
      description: "Calls and venues matched to your research interests.",
    },
    {
      href: "/browse",
      title: "Browse All Calls",
      description: "Calls for papers from conferences, journals and workshops.",
    },
    {
      href: "/postings",
      title: "Research Postings",
      description: role === "FACULTY" ? "Your openings and their applicants." : "Projects, thesis topics and assistantships from faculty.",
    },
  ];
  if (role === "STUDENT") {
    destinations.push({
      href: "/supervisors",
      title: "Find a Supervisor",
      description: "Faculty whose research fits yours.",
    });
  }
  if (role === "ADMIN") {
    destinations.unshift({
      href: "/admin",
      title: "Administration",
      description: "Accounts, roles and research data freshness.",
    });
  }
  return destinations;
}

export default function DashboardPage() {
  return (
    <RequireAuth>
      <HomePage />
    </RequireAuth>
  );
}
