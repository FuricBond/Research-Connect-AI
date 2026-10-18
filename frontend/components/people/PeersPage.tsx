"use client";

import Link from "next/link";
import { useState } from "react";
import { useApiResource } from "../../hooks/useApiResource";
import { fetchDiscoverySettings, fetchPeerMatches } from "../../services/api";
import type { CollaborationInterest, DiscoverySettings } from "../../types/peer";
import { ALL_COLLABORATION_INTERESTS, COLLABORATION_INTEREST_LABELS, PEER_SIGNAL_LABELS } from "../../types/peer";
import { useSession } from "../auth/SessionProvider";
import { Checkbox, Select } from "../ui/Field/Field";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import { Discoverability } from "./Discoverability";
import { ResearcherCard } from "./ResearcherCard";
import styles from "./People.module.css";

const DESCRIPTION = "Researchers who share your expertise, add expertise you do not have, or work in related fields and are open to collaboration.";

/**
 * P6 — Find peers (Phase 5.12): your own discoverability first (opt-in), then researchers the
 * server suggests from shared and complementary expertise, related fields, methods and stated
 * availability. Only researchers who chose to be discoverable appear.
 */
export function PeersPage() {
  const { profileId } = useSession();
  const [interest, setInterest] = useState<CollaborationInterest | "">("");
  const [excludeOwn, setExcludeOwn] = useState(false);
  const settings = useApiResource(profileId ? `peers:settings:${profileId}` : null, (signal) => fetchDiscoverySettings(profileId!, undefined, signal));
  const matches = useApiResource(profileId ? `peers:${profileId}:${interest}:${excludeOwn}` : null, (signal) =>
    fetchPeerMatches(profileId!, { limit: 25, collaborationInterest: interest || undefined, excludeSameInstitution: excludeOwn || undefined }, undefined, signal)
  );
  const [saved, setSaved] = useState<DiscoverySettings | null>(null);
  const shownSettings = saved ?? settings.data;

  if (!profileId) {
    return (
      <>
        <PageHeader title="Find peers" description={DESCRIPTION} />
        <EmptyState
          headingLevel={2}
          title="Set up your researcher profile first."
          description={
            <>
              Peers are matched on recorded research topics. <Link href="/researcher">Set up your profile</Link>.
            </>
          }
        />
      </>
    );
  }

  const data = matches.data;
  return (
    <>
      <PageHeader title="Find peers" description={DESCRIPTION} />
      <div className={styles.page}>
        {settings.status === "loading" || settings.status === "idle" ? (
          <SkeletonList rows={2} label="Loading your discoverability" announce={false} />
        ) : shownSettings ? (
          <Discoverability profileId={profileId} settings={shownSettings} onSaved={setSaved} />
        ) : (
          <ErrorState headingLevel={2} title="Your discoverability could not be loaded" onRetry={settings.retry} />
        )}

        <form className={styles.filters} aria-label="Peer filters" onSubmit={(event) => event.preventDefault()}>
          <Select label="Collaboration type" value={interest} onChange={(event) => setInterest(event.target.value as CollaborationInterest | "")}>
            <option value="">Any</option>
            {ALL_COLLABORATION_INTERESTS.map((value) => (
              <option key={value} value={value}>
                {COLLABORATION_INTEREST_LABELS[value]}
              </option>
            ))}
          </Select>
          <Checkbox label="Leave out my own institution" checked={excludeOwn} onChange={(event) => setExcludeOwn(event.target.checked)} />
        </form>

        <section className={styles.results} aria-labelledby="peer-results-heading" aria-busy={matches.status === "loading" || undefined}>
          <h2 id="peer-results-heading" className={styles.resultsTitle}>
            Suggested peers
          </h2>
          {matches.status === "loading" || matches.status === "idle" ? (
            <SkeletonList rows={3} lines={3} label="Finding peers" />
          ) : matches.status === "error" || !data ? (
            <ErrorState title="Peer suggestions could not be loaded" kind={matches.error?.kind === "network" ? "offline" : "failed"} onRetry={matches.retry} />
          ) : data.matches.length === 0 ? (
            <EmptyState
              variant={interest || excludeOwn ? "no-results" : "first-use"}
              title="No peers matched."
              description={data.guidance ?? "Peer discovery is opt-in, so results appear as colleagues choose to be found."}
            />
          ) : (
            <>
              <p className={styles.note} role="status">
                {data.returned_count} of {data.total_candidates_evaluated} discoverable researchers matched. Each suggestion is scored from recorded research topics with fixed weights; a thin
                profile can match highly by coincidence, which the confidence under each score shows.
              </p>
              <ul className={styles.list}>
                {data.matches.map((match) => (
                  <li key={match.peer.profile_id}>
                    <ResearcherCard
                      person={match.peer}
                      score={match.match_score}
                      tier={match.tier}
                      confidence={match.confidence}
                      reasons={match.explanation_reasons}
                      sharedTopics={match.shared_topics}
                      complementaryTopics={match.complementary_topics}
                      signals={match.signals.map((signal) => ({
                        key: signal.signal_type,
                        label: PEER_SIGNAL_LABELS[signal.signal_type],
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
