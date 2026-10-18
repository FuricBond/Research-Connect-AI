"use client";

import Link from "next/link";
import { useState } from "react";
import { useApiResource } from "../../hooks/useApiResource";
import { fetchSupervisorMatches } from "../../services/api";
import { SUPERVISOR_SIGNAL_LABELS } from "../../types/supervisor";
import { useSession } from "../auth/SessionProvider";
import { Checkbox } from "../ui/Field/Field";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { Alert, EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import { ResearcherCard } from "./ResearcherCard";
import styles from "./People.module.css";

const DESCRIPTION = "Faculty who share your research topics, publish close to your interests and are taking students.";

/**
 * P6 — Find a supervisor (student accounts). Faculty are suggested by the server from shared
 * topics, closeness in meaning, recent papers, related fields and supervision availability; only
 * faculty who chose to be discoverable appear. The backend answers any other role with 403, so
 * for them the page explains itself and asks nothing — hiding it in the navigation is a
 * convenience, not the permission.
 */
export function SupervisorsPage() {
  const { profileId, hasRole } = useSession();
  const isStudent = hasRole("STUDENT");
  const [excludeOwn, setExcludeOwn] = useState(false);
  const [openOnly, setOpenOnly] = useState(false);
  const matches = useApiResource(isStudent && profileId ? `supervisors:${profileId}:${excludeOwn}:${openOnly}` : null, (signal) =>
    fetchSupervisorMatches(profileId!, { limit: 25, excludeSameInstitution: excludeOwn || undefined, openPostingsOnly: openOnly || undefined }, signal)
  );

  if (!isStudent) {
    return (
      <>
        <PageHeader title="Find a supervisor" description={DESCRIPTION} />
        <EmptyState
          headingLevel={2}
          title="Find a supervisor is for student accounts."
          description={
            <>
              Faculty appear in students&apos; results when they choose to be discoverable on <Link href="/peers">Find peers</Link>.
            </>
          }
        />
      </>
    );
  }

  if (!profileId) {
    return (
      <>
        <PageHeader title="Find a supervisor" description={DESCRIPTION} />
        <EmptyState
          headingLevel={2}
          title="Set up your researcher profile first."
          description={
            <>
              Supervisors are matched to your research interests. <Link href="/researcher">Set up your profile</Link>.
            </>
          }
        />
      </>
    );
  }

  const data = matches.data;
  return (
    <>
      <PageHeader title="Find a supervisor" description={DESCRIPTION} />
      <div className={styles.page}>
        <form className={styles.filters} aria-label="Supervisor filters" onSubmit={(event) => event.preventDefault()}>
          <Checkbox label="Leave out my own institution" checked={excludeOwn} onChange={(event) => setExcludeOwn(event.target.checked)} />
          <Checkbox label="Only faculty with an open thesis topic, project or assistantship" checked={openOnly} onChange={(event) => setOpenOnly(event.target.checked)} />
        </form>

        <section className={styles.results} aria-labelledby="supervisor-results-heading" aria-busy={matches.status === "loading" || undefined}>
          <h2 id="supervisor-results-heading" className={styles.resultsTitle}>
            Suggested supervisors
          </h2>
          {matches.status === "loading" || matches.status === "idle" ? (
            <SkeletonList rows={3} lines={3} label="Finding supervisors" />
          ) : matches.status === "error" || !data ? (
            <ErrorState title="Supervisor suggestions could not be loaded" kind={matches.error?.kind === "forbidden" ? "permission" : matches.error?.kind === "network" ? "offline" : "failed"} onRetry={matches.retry} />
          ) : data.matches.length === 0 ? (
            <EmptyState
              variant={excludeOwn || openOnly ? "no-results" : "first-use"}
              title="No supervisors matched."
              description={
                <>
                  {data.guidance ? `${data.guidance} ` : ""}Faculty appear here only after they choose to be discoverable on <Link href="/peers">Find peers</Link>.
                </>
              }
            />
          ) : (
            <>
              <p className={styles.note} role="status">
                {data.returned_count} of {data.total_candidates_evaluated} discoverable faculty matched. Each suggestion is scored from your research topics, preferred topics and publications with
                fixed weights; only faculty who chose to be discoverable appear.
              </p>
              {!data.semantic_available && <Alert>Your interests could not be compared by meaning right now, so these suggestions are ranked on research topics only.</Alert>}
              <ul className={styles.list}>
                {data.matches.map((match) => (
                  <li key={match.supervisor.profile_id}>
                    <ResearcherCard
                      person={match.supervisor}
                      score={match.match_score}
                      tier={match.tier}
                      confidence={match.confidence}
                      reasons={match.explanation_reasons}
                      sharedTopics={match.shared_topics}
                      papers={match.matching_papers}
                      postings={match.open_postings}
                      signals={match.signals.map((signal) => ({
                        key: signal.signal_type,
                        label: SUPERVISOR_SIGNAL_LABELS[signal.signal_type],
                        rawScore: signal.raw_score,
                        contribution: signal.weighted_contribution,
                        explanation: signal.explanation,
                      }))}
                    />
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>
    </>
  );
}
