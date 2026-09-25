"use client";

import React, { useCallback, useEffect, useState } from "react";
import "../../styles/postings.css";
import "../../styles/peers.css";
import { AlertCircle, Info, RefreshCw, ShieldCheck, Users } from "lucide-react";
import { PeerMatchCard } from "../../components/peers/PeerMatchCard";
import type {
  CollaborationInterest,
  CollaborationStatus,
  DiscoverySettings,
  PeerMatchResponse,
} from "../../types/peer";
import {
  ALL_COLLABORATION_INTERESTS,
  ALL_COLLABORATION_STATUSES,
  COLLABORATION_INTEREST_LABELS,
  COLLABORATION_STATUS_LABELS,
} from "../../types/peer";
import {
  fetchDiscoverySettings,
  fetchPeerMatches,
  updateDiscoverySettings,
} from "../../services/api";
import { getStoredIdentity } from "../../services/auth";

export default function PeerDiscoveryPage() {
  const [profileId, setProfileId] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | undefined>(undefined);

  const [settings, setSettings] = useState<DiscoverySettings | null>(null);
  const [result, setResult] = useState<PeerMatchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [interestFilter, setInterestFilter] = useState<CollaborationInterest | "">("");
  const [excludeSameInstitution, setExcludeSameInstitution] = useState(false);

  useEffect(() => {
    const identity = getStoredIdentity();
    setProfileId(identity.profileId);
    setUserId(identity.userId ?? undefined);
  }, []);

  const load = useCallback(async () => {
    if (!profileId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [loadedSettings, matches] = await Promise.all([
        fetchDiscoverySettings(profileId, userId),
        fetchPeerMatches(
          profileId,
          {
            limit: 25,
            collaborationInterest: interestFilter || undefined,
            excludeSameInstitution: excludeSameInstitution || undefined,
          },
          userId
        ),
      ]);
      setSettings(loadedSettings);
      setResult(matches);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load peer discovery");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [profileId, userId, interestFilter, excludeSameInstitution]);

  useEffect(() => {
    load();
  }, [load]);

  const patchSettings = async (changes: Partial<DiscoverySettings>) => {
    if (!profileId) return;
    setSavingSettings(true);
    setError(null);
    try {
      const updated = await updateDiscoverySettings(
        profileId,
        {
          is_discoverable: changes.is_discoverable,
          collaboration_status: changes.collaboration_status,
          collaboration_interests: changes.collaboration_interests,
          show_institution: changes.show_institution,
          show_contact_email: changes.show_contact_email,
          collaboration_note: changes.collaboration_note,
        },
        userId
      );
      setSettings(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update your settings");
    } finally {
      setSavingSettings(false);
    }
  };

  const toggleInterest = (interest: CollaborationInterest) => {
    if (!settings) return;
    const current = settings.collaboration_interests;
    const next = current.includes(interest)
      ? current.filter((i) => i !== interest)
      : [...current, interest];
    patchSettings({ collaboration_interests: next });
  };

  if (!profileId) {
    return (
      <div className="postings-page">
        <h1>Peer &amp; Co-Author Discovery</h1>
        <div className="postings-empty">
          Set up a researcher profile first — peer matching compares recorded research topics, so
          it needs a profile to compare from.
        </div>
      </div>
    );
  }

  return (
    <div className="postings-page">
      <header className="postings-header">
        <div className="postings-title-group">
          <h1>Peer &amp; Co-Author Discovery</h1>
          <p className="postings-subtitle">
            Researchers are suggested from shared expertise, expertise you do not yet have,
            related fields in the taxonomy, overlapping methods and stated availability. Only
            researchers who chose to be discoverable appear here, and each suggestion shows exactly
            how it was scored.
          </p>
        </div>
        <button type="button" className="posting-btn" onClick={load} disabled={loading}>
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

      {settings && (
        <section className="peer-consent-panel">
          <div className="peer-consent-head">
            <h2>
              <ShieldCheck size={16} aria-hidden="true" /> Your discoverability
            </h2>
            <label className="peer-switch">
              <input
                type="checkbox"
                checked={settings.is_discoverable}
                disabled={savingSettings}
                onChange={(e) => patchSettings({ is_discoverable: e.target.checked })}
              />
              <span>{settings.is_discoverable ? "Discoverable" : "Not discoverable"}</span>
            </label>
          </div>

          <p className="posting-owner-note">
            Peer discovery is opt-in. While this is off you can still search for peers, but you
            will not appear in anyone else&apos;s results.
            {settings.consent_updated_at && (
              <> Last changed {new Date(settings.consent_updated_at).toLocaleDateString()}.</>
            )}
          </p>

          <div className="posting-form-grid">
            <div className="posting-field">
              <label htmlFor="collab-status">Availability shown to peers</label>
              <select
                id="collab-status"
                value={settings.collaboration_status}
                disabled={savingSettings}
                onChange={(e) =>
                  patchSettings({ collaboration_status: e.target.value as CollaborationStatus })
                }
              >
                {ALL_COLLABORATION_STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {COLLABORATION_STATUS_LABELS[status]}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="posting-field">
            <label>What peers may see</label>
            <label className="postings-checkbox">
              <input
                type="checkbox"
                checked={settings.show_institution}
                disabled={savingSettings}
                onChange={(e) => patchSettings({ show_institution: e.target.checked })}
              />
              Show my institution and department
            </label>
            <label className="postings-checkbox">
              <input
                type="checkbox"
                checked={settings.show_contact_email}
                disabled={savingSettings}
                onChange={(e) => patchSettings({ show_contact_email: e.target.checked })}
              />
              Show my email address
            </label>
          </div>

          <div className="posting-field">
            <label>Collaboration I will consider</label>
            <div className="peer-interest-chips">
              {ALL_COLLABORATION_INTERESTS.map((interest) => {
                const active = settings.collaboration_interests.includes(interest);
                return (
                  <button
                    key={interest}
                    type="button"
                    className={`peer-chip${active ? " active" : ""}`}
                    disabled={savingSettings}
                    aria-pressed={active}
                    onClick={() => toggleInterest(interest)}
                  >
                    {COLLABORATION_INTEREST_LABELS[interest]}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="posting-field">
            <label htmlFor="collab-note">
              Note shown to peers <span className="posting-field-hint">optional</span>
            </label>
            <input
              id="collab-note"
              maxLength={1000}
              defaultValue={settings.collaboration_note ?? ""}
              disabled={savingSettings}
              onBlur={(e) => {
                const value = e.target.value.trim();
                if (value !== (settings.collaboration_note ?? "")) {
                  patchSettings({ collaboration_note: value || null });
                }
              }}
              placeholder="Looking for co-authors on retrieval evaluation."
            />
          </div>
        </section>
      )}

      <div className="postings-filters">
        <select
          value={interestFilter}
          onChange={(e) => setInterestFilter(e.target.value as CollaborationInterest | "")}
          aria-label="Filter by collaboration interest"
        >
          <option value="">Any collaboration type</option>
          {ALL_COLLABORATION_INTERESTS.map((interest) => (
            <option key={interest} value={interest}>
              {COLLABORATION_INTEREST_LABELS[interest]}
            </option>
          ))}
        </select>
        <label className="postings-checkbox">
          <input
            type="checkbox"
            checked={excludeSameInstitution}
            onChange={(e) => setExcludeSameInstitution(e.target.checked)}
          />
          Exclude my own institution
        </label>
      </div>

      {loading ? (
        <div className="postings-loading">Finding peers…</div>
      ) : result && result.matches.length > 0 ? (
        <>
          <p className="postings-subtitle">
            <Users size={13} aria-hidden="true" /> {result.returned_count} of{" "}
            {result.total_candidates_evaluated} discoverable researchers matched
          </p>
          <div className="postings-list">
            {result.matches.map((match) => (
              <PeerMatchCard key={match.peer.profile_id} match={match} />
            ))}
          </div>
        </>
      ) : (
        <div className="postings-empty">
          <Info size={15} aria-hidden="true" />
          <p>
            {result?.guidance ??
              "No peers matched. Peer discovery is opt-in, so results appear as colleagues choose to be found."}
          </p>
        </div>
      )}
    </div>
  );
}
