"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CalendarPlus, ExternalLink, LogIn } from "lucide-react";
import { useApiResource } from "../../hooks/useApiResource";
import { isUuid } from "../../utils/ids";
import { fetchDefaultCalendar, fetchOpportunity, fetchOpportunityRiskExplanation, projectOpportunityToCalendar } from "../../services/api";
import type { WorkspaceItem } from "../../types/workspace";
import { callsOrigin } from "../../utils/callsState";
import { formatDeadlineDate } from "../../utils/date";
import { callStatusLabel, callTypeLabel, deliveryModeLabel, feeLabel } from "../../utils/research";
import { workspaceStatusMeta } from "../../utils/status";
import { workspaceDeadline } from "../../utils/workspace";
import { useSession } from "../auth/SessionProvider";
import { DeadlineCountdown } from "../research/DeadlineCountdown";
import { DeadlineMilestones } from "../research/DeadlineMilestones";
import { Fact, RiskDetails } from "../research/RiskDetails";
import { RiskIndicator } from "../research/RiskIndicator";
import { SaveCallButton } from "../research/SaveCallButton";
import { useTrackedCalls } from "../research/trackedCalls";
import { StatusBadge } from "../ui/Badge/Badge";
import { Breadcrumb } from "../ui/Breadcrumb/Breadcrumb";
import { Button, ButtonLink } from "../ui/Button/Button";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { Alert, ErrorState, Skeleton, SkeletonList, SkeletonText } from "../ui/State/State";
import styles from "./CallDetail.module.css";

type CalendarState = { state: "idle" } | { state: "working" } | { state: "done"; added: number; total: number } | { state: "failed" };

function eventDates(start: string | null, end: string | null): string | null {
  if (!start) return null;
  const from = formatDeadlineDate(start);
  return end && end !== start ? `${from} – ${formatDeadlineDate(end)}` : from;
}

function PageSkeleton() {
  return (
    <div className={styles.skeleton} aria-busy="true">
      {/* Text in the title face, so its font starts loading with the first paint rather than when
          the title arrives: a long title that re-wrapped when the font swapped in moved the page
          by 35px at 390px (P5, CLS 0.022). Hidden, and not read out. */}
      <span className={styles.fontPrimer} aria-hidden="true">
        Call for papers
      </span>
      <Skeleton width="8rem" height="1rem" />
      <Skeleton width="70%" height="2.25rem" />
      <SkeletonText lines={1} />
      <SkeletonList rows={3} lines={2} label="Loading the call for papers" />
    </div>
  );
}

/**
 * A call for papers (`/calls/[id]`, FRONTEND_REDESIGN_PLAN.md §11): what it is, its dates in order
 * (abstract → paper → notification → camera-ready, each in its own time zone), its venue risk with
 * the evidence, its workspace status when tracked, and the actions — save it, add its dates to the
 * calendar (the existing projection), open its source. Two requests, together: the call (which
 * carries its deadline intelligence) and its risk explanation; signed in, the tracked-calls lookup.
 * The call is public, like the list; the actions are for signed-in researchers. An id that cannot
 * be a call's is "not found" without asking the API; a missing call is "not found"; any other
 * failure can be retried; a risk explanation that fails leaves the rest of the page in place.
 */
export function CallDetail({ id }: { id: string }) {
  const valid = isUuid(id);
  const { status: sessionStatus } = useSession();
  const call = useApiResource(valid ? `call:${id}` : null, (signal) => fetchOpportunity(id, signal), { scope: "public" });
  const risk = useApiResource(valid ? `call-risk:${id}` : null, (signal) => fetchOpportunityRiskExplanation(id, signal), { scope: "public" });
  const tracked = useTrackedCalls();
  const [savedItem, setSavedItem] = useState<WorkspaceItem | null>(null);
  const [calendar, setCalendar] = useState<CalendarState>({ state: "idle" });
  const [backHref, setBackHref] = useState("/browse");

  useEffect(() => setBackHref(callsOrigin()), []);
  useEffect(() => {
    if (call.data) document.title = `${call.data.title} — ResearchConnect AI`;
  }, [call.data]);

  const crumbs = [{ label: "Calls for papers", href: backHref }];

  if (!valid || (call.status === "error" && call.error?.kind === "not-found")) {
    return (
      <>
        <Breadcrumb items={crumbs} current="Call not found" />
        <ErrorState
          kind="not-found"
          headingLevel={1}
          title="Call for papers not found"
          description="It may have been removed, or the link may be wrong."
          actions={<ButtonLink href="/browse">Browse calls for papers</ButtonLink>}
        />
      </>
    );
  }
  if (call.status === "error") {
    const forbidden = call.error?.kind === "forbidden";
    return (
      <>
        <Breadcrumb items={crumbs} current="Call for papers" />
        <ErrorState
          kind={forbidden ? "permission" : call.error?.kind === "network" ? "offline" : "failed"}
          headingLevel={1}
          title={forbidden ? "You don't have access to this call" : "This call could not be loaded"}
          description={
            forbidden
              ? "This call is only available to some accounts."
              : call.error?.kind === "network"
                ? "The server could not be reached. Check your connection and try again."
                : "Something went wrong while loading. Try again in a moment."
          }
          onRetry={forbidden ? undefined : call.retry}
          announce={call.retries > 0}
        />
      </>
    );
  }
  if (call.status !== "success" || !call.data) {
    return (
      <>
        <Breadcrumb items={crumbs} current="Call for papers" />
        <PageSkeleton />
      </>
    );
  }

  const data = call.data;
  const item = savedItem ?? tracked.byCall.get(data.id) ?? null;
  const deadline = workspaceDeadline(data);
  const facts = [data.organizer || data.publisher, data.location, deliveryModeLabel(data.delivery_mode)].filter(Boolean).join(" · ");
  const indexing = (data.indexing ?? []).filter((name) => typeof name === "string" && name.trim());
  const signedIn = sessionStatus === "authenticated";

  const addToCalendar = async () => {
    if (calendar.state === "working") return;
    setCalendar({ state: "working" });
    try {
      const target = await fetchDefaultCalendar();
      const result = await projectOpportunityToCalendar(target.id, { opportunity_id: data.id });
      setCalendar({ state: "done", added: result.created_count, total: result.projected_events.length });
    } catch {
      setCalendar({ state: "failed" });
    }
  };

  return (
    <article className={styles.page} aria-labelledby="call-title">
      <Breadcrumb items={crumbs} current="Call details" />
      <PageHeader
        eyebrow={callTypeLabel(data.opportunity_type)}
        title={<span id="call-title">{data.title}</span>}
        description={facts || undefined}
        actions={
          <>
            {signedIn ? (
              <SaveCallButton opportunityId={data.id} isSaved={item !== null} onSaved={setSavedItem} variant="primary" size="md" />
            ) : (
              sessionStatus === "unauthenticated" && (
                <ButtonLink href={`/login?next=${encodeURIComponent(`/calls/${data.id}`)}`} variant="primary" leadingIcon={<LogIn size={16} aria-hidden="true" />}>
                  Sign in to save
                </ButtonLink>
              )
            )}
            {signedIn && (
              <Button onClick={addToCalendar} loading={calendar.state === "working"} leadingIcon={<CalendarPlus size={16} aria-hidden="true" />}>
                Add dates to calendar
              </Button>
            )}
            {data.website_url && (
              <a href={data.website_url} className={styles.external} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={16} aria-hidden="true" />
                Source
                <span className="rc-visually-hidden"> (opens in new tab)</span>
              </a>
            )}
            {data.submission_url && (
              <a href={data.submission_url} className={styles.external} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={16} aria-hidden="true" />
                Submission site
                <span className="rc-visually-hidden"> (opens in new tab)</span>
              </a>
            )}
          </>
        }
      />

      <div className={styles.status}>
        <DeadlineCountdown deadline={deadline.deadline} daysRemaining={deadline.daysRemaining} status={deadline.status} urgencyTier={deadline.urgencyTier} />
        <RiskIndicator level={risk.data?.risk_level ?? data.risk_level} isPredatory={risk.data?.is_predatory_flag ?? data.is_predatory_flag} />
        {item && (
          <span className={styles.tracked}>
            In your workspace: <StatusBadge meta={workspaceStatusMeta(item.status)} />
            <Link href={`/workspace/${item.id}`} className={styles.link}>
              Open in workspace
            </Link>
          </span>
        )}
      </div>

      {calendar.state === "done" && (
        <Alert tone="success" announce action={<Link href="/calendar" className={styles.link}>Open calendar</Link>}>
          {calendar.total === 0
            ? "This call has no dates to add."
            : calendar.added > 0
              ? `Added ${calendar.added} date${calendar.added === 1 ? "" : "s"} to your calendar.`
              : "Your calendar already has this call's dates."}
        </Alert>
      )}
      {calendar.state === "failed" && (
        <Alert tone="danger" announce>
          The dates could not be added to your calendar. Try again.
        </Alert>
      )}

      <div className={styles.columns}>
        <div className={styles.main}>
          <section className={styles.section} aria-labelledby="call-about">
            <h2 id="call-about" className={styles.sectionTitle}>
              About this call
            </h2>
            {data.summary && <p className={styles.lead}>{data.summary}</p>}
            {data.description && data.description !== data.summary && <p className={styles.reading}>{data.description}</p>}
            {!data.summary && !data.description && <p className={styles.muted}>The source gives no description.</p>}
          </section>

          <section className={styles.section} aria-labelledby="call-dates">
            <h2 id="call-dates" className={styles.sectionTitle}>
              Dates
            </h2>
            <DeadlineMilestones intelligence={data.deadline_intelligence} dates={data} />
          </section>

          <section className={styles.section} aria-labelledby="call-risk" aria-busy={risk.status === "loading" || undefined}>
            <h2 id="call-risk" className={styles.sectionTitle}>
              Venue risk
            </h2>
            {risk.status === "loading" && <SkeletonList rows={2} label="Loading the venue risk assessment" />}
            {risk.status === "error" && (
              <Alert tone="warning" announce={risk.retries > 0} action={<Button size="sm" onClick={risk.retry}>Try again</Button>}>
                The full risk assessment could not be loaded. The level shown above comes from the call itself.
              </Alert>
            )}
            {risk.status === "success" && <RiskDetails explanation={risk.data ?? null} headingLevel={3} />}
          </section>
        </div>

        <aside className={styles.aside} aria-labelledby="call-facts">
          <h2 id="call-facts" className={styles.sectionTitle}>
            Facts
          </h2>
          <dl className={styles.facts}>
            <Fact term="Type" value={callTypeLabel(data.opportunity_type)} />
            {data.organizer && <Fact term="Organiser" value={data.organizer} />}
            {data.publisher && data.publisher !== data.organizer && <Fact term="Publisher" value={data.publisher} />}
            {data.series_name && <Fact term="Series" value={data.series_name} />}
            {data.edition && <Fact term="Edition" value={data.edition} />}
            {data.location && <Fact term="Location" value={data.location} />}
            {deliveryModeLabel(data.delivery_mode) && <Fact term="Attendance" value={deliveryModeLabel(data.delivery_mode)} />}
            {eventDates(data.event_start_date, data.event_end_date) && <Fact term="Event" value={eventDates(data.event_start_date, data.event_end_date)} />}
            {indexing.length > 0 && <Fact term="Indexed in" value={indexing.join(", ")} />}
            {feeLabel(data.apc_or_fee) && <Fact term="Fee" value={feeLabel(data.apc_or_fee)} />}
            {callStatusLabel(data.status) && <Fact term="Status" value={callStatusLabel(data.status)} />}
            {data.last_verified_at && <Fact term="Last checked" value={formatDeadlineDate(data.last_verified_at)} />}
          </dl>
        </aside>
      </div>
    </article>
  );
}
