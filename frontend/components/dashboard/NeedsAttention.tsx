"use client";

import Link from "next/link";
import { CheckCircle2, Circle } from "lucide-react";
import type { ApiResource } from "../../hooks/useApiResource";
import type { ApplicationSummaryResponse } from "../../types/posting";
import type { ReadingListResponse } from "../../types/reading_list";
import type { UnifiedRecommendationResponse } from "../../types/research_intelligence";
import type { WorkspaceListResponse, WorkspaceStatus } from "../../types/workspace";
import { humanizeEnum } from "../../utils/date";
import { riskPresentation } from "../../utils/risk";
import { workspaceStatusMeta } from "../../utils/status";
import { upcomingDeadlines, workspaceDeadline } from "../../utils/workspace";
import { DeadlineCountdown } from "../research/DeadlineCountdown";
import { RiskIndicator } from "../research/RiskIndicator";
import { StatusBadge } from "../ui/Badge/Badge";
import { EmptyState } from "../ui/State/State";
import { DashboardModule, Loaded } from "./Module";
import { ATTENTION_DAYS } from "./resources";
import styles from "./Dashboard.module.css";

const CALLS_SHOWN = 5;

/** What to do next with a tracked call, by its workspace status. */
const NEXT_STEP: Partial<Record<WorkspaceStatus, string>> = {
  SAVED: "Next: decide whether to submit",
  CONSIDERING: "Next: decide whether to submit",
  PLANNING: "Next: finish and submit your paper",
  APPLIED: "Submitted: waiting for the decision",
};

/**
 * Student "Needs attention" (plan §8): tracked calls due within 14 days with status and next
 * step; offers and applications in progress; a nudge when the profile is incomplete; and, while
 * the account is new, the three-step "Get started" checklist. Each part shows its own loading
 * and failure; the parts share the dashboard's requests (workspace, application summary,
 * recommendations, reading list) and make none of their own.
 */
export function NeedsAttention({
  calls,
  applications,
  recommendations,
  reading,
}: {
  calls: ApiResource<WorkspaceListResponse>;
  applications: ApiResource<ApplicationSummaryResponse>;
  recommendations: ApiResource<UnifiedRecommendationResponse>;
  reading: ApiResource<ReadingListResponse>;
}) {
  return (
    <DashboardModule id="dashboard-attention" title="Needs attention" reserve="attention">
      <Applications applications={applications} />
      <div className={styles.part}>
        <h3 className={styles.partTitle}>Due in the next {ATTENTION_DAYS} days</h3>
        <Loaded resource={calls} loading="Loading your tracked calls" failure="Your tracked calls could not be loaded." rows={2}>
          {(data) => <DueSoon data={data} />}
        </Loaded>
      </div>
      <ProfileAndGetStarted calls={calls} recommendations={recommendations} reading={reading} />
    </DashboardModule>
  );
}

function DueSoon({ data }: { data: WorkspaceListResponse }) {
  const due = upcomingDeadlines(data.items, ATTENTION_DAYS);
  if (due.length === 0) {
    return (
      <EmptyState
        bare
        variant="done"
        headingLevel={4}
        title={`No tracked call is due in the next ${ATTENTION_DAYS} days.`}
        description={
          <>
            <Link href="/browse">Browse calls for papers</Link> and save the ones you plan to submit to.
          </>
        }
      />
    );
  }
  return (
    <>
      <ul className={styles.list}>
        {due.slice(0, CALLS_SHOWN).map(({ item }) => {
          const deadline = workspaceDeadline(item.opportunity);
          const risk = riskPresentation(item.opportunity.risk_explanation?.risk_level, { isPredatory: item.opportunity.is_predatory_flag });
          return (
            <li key={item.id} className={styles.item}>
              <Link href={`/workspace/${item.id}`} className={styles.itemTitle}>
                {item.opportunity.title}
              </Link>
              <div className={styles.meta}>
                <DeadlineCountdown deadline={deadline.deadline} daysRemaining={deadline.daysRemaining} status={deadline.status} urgencyTier={deadline.urgencyTier} />
                <StatusBadge meta={workspaceStatusMeta(item.status)} />
                {/* Only a concern is worth space here; "not assessed" stays on the workspace card. */}
                {(risk.tone === "high" || risk.tone === "caution") && (
                  <RiskIndicator level={item.opportunity.risk_explanation?.risk_level} isPredatory={item.opportunity.is_predatory_flag} />
                )}
              </div>
              {NEXT_STEP[item.status] && <span className={styles.nextStep}>{NEXT_STEP[item.status]}</span>}
            </li>
          );
        })}
      </ul>
      {due.length > CALLS_SHOWN && (
        <Link href="/workspace" className={styles.more}>
          See all {due.length} calls due in the next {ATTENTION_DAYS} days
        </Link>
      )}
    </>
  );
}

/** Offers first (they wait on the student), then what is in progress. */
function Applications({ applications }: { applications: ApiResource<ApplicationSummaryResponse> }) {
  return (
    <div className={styles.part}>
      <h3 className={styles.partTitle}>Applications</h3>
      <Loaded resource={applications} loading="Loading your applications" failure="Your applications could not be loaded." rows={1}>
        {({ by_status: byStatus, active }) => {
          const offers = byStatus.OFFERED ?? 0;
          if (offers > 0) {
            return (
              <p className={styles.text}>
                <strong className={styles.strong}>
                  {offers} offer{offers === 1 ? "" : "s"} waiting for your reply.
                </strong>{" "}
                <Link href="/postings/applications">Review your applications</Link>
              </p>
            );
          }
          if (active > 0) {
            const parts = (["UNDER_REVIEW", "SHORTLISTED", "SUBMITTED"] as const)
              .filter((status) => (byStatus[status] ?? 0) > 0)
              .map((status) => `${byStatus[status]} ${humanizeEnum(status).toLowerCase()}`);
            return (
              <p className={styles.text}>
                {active} application{active === 1 ? "" : "s"} in progress{parts.length ? ` (${parts.join(", ")})` : ""}.{" "}
                <Link href="/postings/applications">My applications</Link>
              </p>
            );
          }
          return (
            <p className={styles.text}>
              No applications in progress. <Link href="/postings">Find research postings</Link> that fit you.
            </p>
          );
        }}
      </Loaded>
    </div>
  );
}

/**
 * The "Get started" checklist while any of its three steps is open, and otherwise a nudge when
 * the profile is still incomplete. Shown only once all three answers are in (a step is never
 * ticked or unticked on a guess); their failures are reported by their own modules.
 */
function ProfileAndGetStarted({
  calls,
  recommendations,
  reading,
}: {
  calls: ApiResource<WorkspaceListResponse>;
  recommendations: ApiResource<UnifiedRecommendationResponse>;
  reading: ApiResource<ReadingListResponse>;
}) {
  const context = recommendations.data?.researcher_context;
  if (!calls.data || !reading.data || !context) return null;

  const steps = [
    { done: context.active_interests_count > 0, label: "Add your research interests", href: "/researcher/preferences" },
    { done: calls.data.total_count > 0, label: "Save a call for papers to your workspace", href: "/browse" },
    { done: reading.data.total_count > 0, label: "Save a paper to your reading list", href: "/" },
  ];
  if (steps.some((step) => !step.done)) {
    return (
      <div className={styles.part}>
        <h3 className={styles.partTitle}>Get started</h3>
        <ol className={styles.steps}>
          {steps.map((step) => (
            <li key={step.label} className={step.done ? `${styles.step} ${styles.stepDone}` : styles.step}>
              {step.done ? <CheckCircle2 size={16} aria-hidden="true" /> : <Circle size={16} aria-hidden="true" />}
              <span>
                {step.done ? (
                  <>
                    {step.label} <span className="rc-visually-hidden">(done)</span>
                  </>
                ) : (
                  <Link href={step.href}>{step.label}</Link>
                )}
              </span>
            </li>
          ))}
        </ol>
      </div>
    );
  }

  if (context.is_partial_profile) {
    const percent = Math.round(context.completeness_score * 100);
    return (
      <div className={styles.part}>
        <h3 className={styles.partTitle}>Your profile</h3>
        {/* The completeness score's own criteria (ResearcherProfileService); it does not change rankings. */}
        <p className={styles.text}>
          Your profile is {percent}% complete: your institution, department, a short bio, research keywords and an ORCID iD
          complete it. <Link href="/researcher">Complete your profile</Link>
        </p>
      </div>
    );
  }
  return null;
}
