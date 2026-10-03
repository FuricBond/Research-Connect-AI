"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import "../../styles/postings.css";
import "../../styles/peers.css";
import { AlertCircle, GraduationCap, Info, RefreshCw } from "lucide-react";
import { SupervisorMatchCard } from "../../components/supervisors/SupervisorMatchCard";
import type { SupervisorMatchResponse } from "../../types/supervisor";
import { fetchSupervisorMatches } from "../../services/api";
import { useSession } from "../../components/auth/SessionProvider";
import { RequireAuth } from "../../components/auth/RequireAuth";

function SupervisorDiscoveryPage() {
  const { profileId, hasRole } = useSession();
  // The backend answers 403 for any other role; this only avoids showing a page that cannot load.
  const isStudent = hasRole("STUDENT");

  const [result, setResult] = useState<SupervisorMatchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [excludeSameInstitution, setExcludeSameInstitution] = useState(false);
  const [openPostingsOnly, setOpenPostingsOnly] = useState(false);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!profileId || !isStudent) {
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const matches = await fetchSupervisorMatches(
          profileId,
          {
            limit: 25,
            excludeSameInstitution: excludeSameInstitution || undefined,
            openPostingsOnly: openPostingsOnly || undefined,
          },
          signal
        );
        if (signal?.aborted) return;
        setResult(matches);
      } catch (err) {
        if (signal?.aborted) return;
        setError(err instanceof Error ? err.message : "Failed to load supervisor matches");
        setResult(null);
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [profileId, isStudent, excludeSameInstitution, openPostingsOnly]
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  if (!isStudent) {
    return (
      <div className="postings-page">
        <h1>Find a Supervisor</h1>
        <div className="postings-empty" role="note">
          <Info size={15} aria-hidden="true" />
          <p>
            Find a Supervisor is for student accounts. Faculty members appear in students&apos;
            results when they choose to be discoverable on{" "}
            <Link href="/peers">Find Peers</Link>.
          </p>
        </div>
      </div>
    );
  }

  if (!profileId) {
    return (
      <div className="postings-page">
        <h1>Find a Supervisor</h1>
        <div className="postings-empty">
          Set up a researcher profile first — supervisor matching compares your research interests
          with faculty research, so it needs a profile to compare from.
        </div>
      </div>
    );
  }

  return (
    <div className="postings-page">
      <header className="postings-header">
        <div className="postings-title-group">
          <h1>Find a Supervisor</h1>
          <p className="postings-subtitle">
            Faculty members are suggested from the research topics you share, how close their
            publications are in meaning to your interests, their recent papers, related fields in
            the taxonomy and whether they are taking students. Only faculty who chose to be
            discoverable appear here, and each suggestion shows exactly how it was scored.
          </p>
        </div>
        <button type="button" className="posting-btn" onClick={() => load()} disabled={loading}>
          <RefreshCw size={13} aria-hidden="true" />
          Refresh
        </button>
      </header>

      {error && (
        <div className="postings-error" role="alert">
          <AlertCircle size={15} aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <div className="postings-filters">
        <label className="postings-checkbox">
          <input
            type="checkbox"
            checked={excludeSameInstitution}
            onChange={(e) => setExcludeSameInstitution(e.target.checked)}
          />
          Exclude my own institution
        </label>
        <label className="postings-checkbox">
          <input
            type="checkbox"
            checked={openPostingsOnly}
            onChange={(e) => setOpenPostingsOnly(e.target.checked)}
          />
          Only faculty with an open thesis topic, project or assistantship
        </label>
      </div>

      {loading ? (
        <div className="postings-loading">Finding supervisors…</div>
      ) : result && result.matches.length > 0 ? (
        <>
          <p className="postings-subtitle">
            <GraduationCap size={13} aria-hidden="true" /> {result.returned_count} of{" "}
            {result.total_candidates_evaluated} discoverable faculty members matched
          </p>
          {!result.semantic_available && (
            <p className="posting-owner-note">
              Your interests could not be compared by meaning right now, so these suggestions are
              ranked on research topics only.
            </p>
          )}
          <div className="postings-list">
            {result.matches.map((match) => (
              <SupervisorMatchCard key={match.supervisor.profile_id} match={match} />
            ))}
          </div>
        </>
      ) : (
        <div className="postings-empty">
          <Info size={15} aria-hidden="true" />
          <p>{result?.guidance ?? "No supervisors matched."}</p>
          <p>
            Faculty members appear here only after they choose to be discoverable on{" "}
            <Link href="/peers">Find Peers</Link>, the same opt-in peer discovery uses.
          </p>
        </div>
      )}
    </div>
  );
}

export default function SupervisorDiscoveryPageRoute() {
  return (
    <RequireAuth>
      <SupervisorDiscoveryPage />
    </RequireAuth>
  );
}
