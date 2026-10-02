"use client";

/**
 * Research refresh (step 4/6) — data freshness on the admin console.
 *
 * Shows whether the scheduled OpenAlex research refresh is on, when it last ran and how
 * that went, how many papers it added in the last 24 hours, when it should run next, and
 * its last five passes. Reads `GET /api/v1/admin/ingestion-runs`, which is ADMIN only; the
 * admin page renders this card only for administrators.
 */

import React, { useCallback, useEffect, useState } from "react";
import { AlertCircle, Database, Loader2, RefreshCw } from "lucide-react";
import type { IngestionRunListResponse, IngestionRunRead } from "../../types/admin";
import { ApiError, fetchIngestionRuns } from "../../services/api";

const RECENT_RUNS = 5;

/** "3 hours ago" / "in 5 hours", in whole units, from `now`. */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const seconds = Math.round((new Date(iso).getTime() - now.getTime()) / 1000);
  const units: [string, number][] = [
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  for (const [unit, size] of units) {
    const count = Math.trunc(Math.abs(seconds) / size);
    if (count >= 1) {
      const label = `${count} ${unit}${count === 1 ? "" : "s"}`;
      return seconds < 0 ? `${label} ago` : `in ${label}`;
    }
  }
  return seconds < 0 ? "just now" : "any moment";
}

function formatAbsolute(iso: string): string {
  return new Date(iso).toLocaleString();
}

function formatInterval(seconds: number): string {
  const hours = seconds / 3600;
  return `every ${Number.isInteger(hours) ? hours : hours.toFixed(1)} h`;
}

/** Lane and subfield from a `research_refresh:{run_tag}:{lane}:{subfield}` label. */
function passOf(run: IngestionRunRead): { lane: string; subfield: string } {
  const parts = (run.topic ?? "").split(":");
  if (parts[0] === "research_refresh" && parts.length >= 4) {
    return { lane: parts[2], subfield: parts[3] };
  }
  return { lane: "—", subfield: run.topic ?? "—" };
}

function statusLabel(status: string | null, error: string | null = null): string {
  if (status === null) return "No runs yet";
  const label = status.charAt(0) + status.slice(1).toLowerCase();
  return error ? `${label} (${error})` : label;
}

export function DataFreshnessCard() {
  const [data, setData] = useState<IngestionRunListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchIngestionRuns({ limit: RECENT_RUNS }, signal));
    } catch (err: unknown) {
      if (signal?.aborted) return;
      setError(
        err instanceof ApiError && err.status < 500
          ? err.detail ?? err.message
          : "Could not load data freshness."
      );
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const refresh = data?.research_refresh ?? null;
  const runs = data?.items.slice(0, RECENT_RUNS) ?? [];

  return (
    <section className="auth-admin" aria-labelledby="data-freshness-title">
      <header className="auth-admin-head">
        <div>
          <h2 id="data-freshness-title">
            <Database size={16} aria-hidden="true" /> Data freshness
          </h2>
          <p className="auth-admin-subtitle">Scheduled OpenAlex research refresh.</p>
        </div>
        <button type="button" className="auth-menu-btn" onClick={() => load()} disabled={loading}>
          <RefreshCw size={13} aria-hidden="true" />
          Refresh
        </button>
      </header>

      {error !== null && (
        <div className="auth-error" role="alert">
          <AlertCircle size={15} aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {loading && data === null ? (
        <div className="auth-pending" role="status">
          <Loader2 size={18} className="auth-spinner" aria-hidden="true" />
          <span>Loading data freshness…</span>
        </div>
      ) : refresh !== null ? (
        <>
          <table className="auth-admin-table" aria-label="Research refresh status">
            <tbody>
              <tr>
                <th scope="row">Scheduled refresh</th>
                <td>{refresh.enabled ? `On, ${formatInterval(refresh.interval_seconds)}` : "Off"}</td>
              </tr>
              <tr>
                <th scope="row">Last run</th>
                <td>
                  {refresh.last_run_started_at ? (
                    <>
                      <span className="auth-admin-name">{formatRelative(refresh.last_run_started_at)}</span>
                      <span className="auth-admin-email">{formatAbsolute(refresh.last_run_started_at)}</span>
                    </>
                  ) : (
                    "Never"
                  )}
                </td>
              </tr>
              <tr>
                <th scope="row">Last run status</th>
                <td>{statusLabel(refresh.last_run_status)}</td>
              </tr>
              <tr>
                <th scope="row">Papers added (24 h)</th>
                <td>{refresh.works_added_last_24h}</td>
              </tr>
              <tr>
                <th scope="row">Next run</th>
                <td>
                  {refresh.next_run_estimate ? (
                    <>
                      <span className="auth-admin-name">{formatRelative(refresh.next_run_estimate)}</span>
                      <span className="auth-admin-email">{formatAbsolute(refresh.next_run_estimate)}</span>
                    </>
                  ) : (
                    "Not scheduled"
                  )}
                </td>
              </tr>
            </tbody>
          </table>

          {runs.length === 0 ? (
            <div className="auth-admin-empty">No research refresh has run yet.</div>
          ) : (
            <table className="auth-admin-table" aria-label="Recent research refresh runs">
              <thead>
                <tr>
                  <th scope="col">Lane</th>
                  <th scope="col">Subfield</th>
                  <th scope="col">Inserted</th>
                  <th scope="col">Updated</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const { lane, subfield } = passOf(run);
                  return (
                    <tr key={run.id}>
                      <td>{lane}</td>
                      <td>{subfield}</td>
                      <td>{run.records_inserted}</td>
                      <td>{run.records_updated}</td>
                      <td>{statusLabel(run.status, run.error_message)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </>
      ) : null}
    </section>
  );
}

export default DataFreshnessCard;
