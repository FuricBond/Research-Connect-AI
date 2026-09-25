"use client";

import React, { useEffect, useState } from "react";
import type {
  PersonalizedCandidateSetResponse,
  ResearcherIntelligenceResponse,
  ResearcherPreferenceCreatePayload,
  ResearcherPreferenceIntelligenceResponse,
  ResearcherProfile,
  ResearcherWorkSummary,
} from "../../types/researcher";
import { ResearcherProfileView } from "../../components/researcher/ResearcherProfileView";
import { ResearcherIntelligenceView } from "../../components/researcher/ResearcherIntelligenceView";
import { ResearcherPreferencesView } from "../../components/researcher/ResearcherPreferencesView";
import { PersonalizedCandidatePreview } from "../../components/researcher/PersonalizedCandidatePreview";
import { PersonalizedRankingPreview } from "../../components/researcher/PersonalizedRankingPreview";
import { PersonalizationSummaryView } from "../../components/researcher/PersonalizationSummaryView";
import { FeedbackHistoryView } from "../../components/researcher/FeedbackHistoryView";
import { RecommendationHistoryView } from "../../components/researcher/RecommendationHistoryView";
import { UnifiedResearchIntelligenceView } from "../../components/researcher/UnifiedResearchIntelligenceView";
import {

  createResearcherPreference,
  createResearcherProfile,
  deleteResearcherPreference,
  fetchPersonalizedCandidates,
  fetchResearcherIntelligence,
  fetchResearcherPreferenceIntelligence,
  fetchResearcherProfile,
  fetchResearcherWorks,
} from "../../services/api";
import { useSession } from "../../components/auth/SessionProvider";
import { AlertCircle, Loader2, Sparkles, UserPlus } from "lucide-react";
import { RequireAuth } from "../../components/auth/RequireAuth";


// Default demo ID or fallback initialization for developer/preview usage
const DEFAULT_DEMO_EMAIL = "researcher@university.edu";

function ResearcherPage() {
  // The signed-in account's profile, created with the account at registration.
  const { profileId } = useSession();
  const [profile, setProfile] = useState<ResearcherProfile | null>(null);
  const [works, setWorks] = useState<ResearcherWorkSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isInitializing, setIsInitializing] = useState(false);

  // Intelligence State (Phase 3.2)
  const [intelligence, setIntelligence] = useState<ResearcherIntelligenceResponse | null>(null);
  const [intelligenceLoading, setIntelligenceLoading] = useState(false);
  const [intelligenceError, setIntelligenceError] = useState<string | null>(null);
  const [isRefreshingIntelligence, setIsRefreshingIntelligence] = useState(false);

  // Preferences State (Phase 3.3)
  const [preferences, setPreferences] = useState<ResearcherPreferenceIntelligenceResponse | null>(null);
  const [preferencesLoading, setPreferencesLoading] = useState(false);
  const [preferencesError, setPreferencesError] = useState<string | null>(null);
  const [isRefreshingPreferences, setIsRefreshingPreferences] = useState(false);

  // Personalized Candidates State (Phase 3.4)
  const [candidates, setCandidates] = useState<PersonalizedCandidateSetResponse | null>(null);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [candidatesError, setCandidatesError] = useState<string | null>(null);
  const [isRefreshingCandidates, setIsRefreshingCandidates] = useState(false);
  const [feedbackRefreshKey, setFeedbackRefreshKey] = useState<number>(0);

  // New profile creation state
  const [initName, setInitName] = useState("Dr. Alex Rivera");
  const [initEmail, setInitEmail] = useState(DEFAULT_DEMO_EMAIL);
  const [initInstitution, setInitInstitution] = useState("Tech University");
  const [initDept, setInitDept] = useState("Computer Science");
  const [initStatus, setInitStatus] = useState("FACULTY");

  const loadCandidates = async (
    profileId: string,
    options?: {
      limit?: number;
      includeInferred?: boolean;
      includeExpertise?: boolean;
      includeFallback?: boolean;
    },
    refresh = false
  ) => {
    if (refresh) {
      setIsRefreshingCandidates(true);
    } else {
      setCandidatesLoading(true);
    }
    setCandidatesError(null);

    try {
      const data = await fetchPersonalizedCandidates(
        profileId,
        options,
        profile?.user_id
      );
      setCandidates(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load personalized candidates";
      setCandidatesError(msg);
    } finally {
      setCandidatesLoading(false);
      setIsRefreshingCandidates(false);
    }
  };


  const loadIntelligence = async (profileId: string, refresh = false) => {
    if (refresh) {
      setIsRefreshingIntelligence(true);
    } else {
      setIntelligenceLoading(true);
    }
    setIntelligenceError(null);

    try {
      const data = await fetchResearcherIntelligence(profileId, refresh);
      setIntelligence(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load research intelligence";
      setIntelligenceError(msg);
    } finally {
      setIntelligenceLoading(false);
      setIsRefreshingIntelligence(false);
    }
  };

  const loadPreferences = async (profileId: string, refresh = false) => {
    if (refresh) {
      setIsRefreshingPreferences(true);
    } else {
      setPreferencesLoading(true);
    }
    setPreferencesError(null);

    try {
      const data = await fetchResearcherPreferenceIntelligence(profileId);
      setPreferences(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load preferences";
      setPreferencesError(msg);
    } finally {
      setPreferencesLoading(false);
      setIsRefreshingPreferences(false);
    }
  };

  const handleAddPreference = async (payload: ResearcherPreferenceCreatePayload) => {
    if (!profile) return;
    try {
      await createResearcherPreference(profile.id, payload, profile.user_id);
      await loadPreferences(profile.id, false);
      await loadCandidates(profile.id, undefined, false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to add preference";
      setPreferencesError(msg);
    }
  };

  const handleDeletePreference = async (preferenceId: string) => {
    if (!profile) return;
    try {
      await deleteResearcherPreference(profile.id, preferenceId, profile.user_id);
      await loadPreferences(profile.id, false);
      await loadCandidates(profile.id, undefined, false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to delete preference";
      setPreferencesError(msg);
    }
  };


  useEffect(() => {
    let cancelled = false;

    async function loadActiveProfile() {
      setLoading(true);
      setError(null);

      if (profileId) {
        try {
          const loaded = await fetchResearcherProfile(profileId);
          if (!cancelled) {
            setProfile(loaded);
            if (loaded.canonical_researcher_id) {
              const loadedWorks = await fetchResearcherWorks(loaded.id).catch(() => []);
              if (!cancelled) setWorks(loadedWorks);
            }
            // Load Phase 3.2 Intelligence
            loadIntelligence(loaded.id, false);
            // Load Phase 3.3 Preferences
            loadPreferences(loaded.id, false);
            // Load Phase 3.4 Personalized Candidates
            loadCandidates(loaded.id, undefined, false);
            setLoading(false);
            return;
          }
        } catch {
          // The account has no readable profile: fall through to the initialization
          // prompt. The session itself is still valid, so it must not be cleared here —
          // only a rejected credential clears a session, and the API client reports that.
        }
      }

      if (!cancelled) {
        setLoading(false);
      }
    }

    loadActiveProfile();
    return () => {
      cancelled = true;
    };
  }, [profileId]);


  const handleCreateDefaultProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsInitializing(true);
    setError(null);

    try {
      const created = await createResearcherProfile({
        full_name: initName.trim(),
        email: initEmail.trim(),
        institution_name: initInstitution.trim() || undefined,
        department: initDept.trim() || undefined,
        academic_status: initStatus as any,
        keywords: ["natural language processing", "information retrieval"],
        bio: "Faculty researcher exploring academic discovery systems and hybrid retrieval.",
      });

      setProfile(created);
      loadIntelligence(created.id, true);
      loadPreferences(created.id, true);
      loadCandidates(created.id, undefined, true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to initialize profile";
      setError(msg);
    } finally {
      setIsInitializing(false);
    }
  };

  const handleProfileUpdated = (updated: ResearcherProfile) => {
    setProfile(updated);
    loadIntelligence(updated.id, true);
    loadPreferences(updated.id, true);
    loadCandidates(updated.id, undefined, true);
  };



  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "60vh", gap: "10px" }}>
        <Loader2 size={24} className="animate-spin" color="var(--primary)" />
        <span style={{ fontSize: "14px", color: "var(--text-muted)" }}>Loading canonical researcher profile...</span>
      </div>
    );
  }

  if (!profile) {
    return (
      <div style={{ maxWidth: "600px", margin: "40px auto", padding: "0 16px" }}>
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-lg)",
            padding: "32px",
            boxShadow: "var(--shadow-md)",
            textAlign: "center",
          }}
        >
          <div
            style={{
              width: "56px",
              height: "56px",
              borderRadius: "var(--radius-full)",
              background: "var(--primary-subtle)",
              color: "var(--primary)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 16px auto",
            }}
          >
            <UserPlus size={28} />
          </div>

          <h2 style={{ fontSize: "20px", fontWeight: 700, margin: "0 0 8px 0" }}>
            Initialize Canonical Researcher Identity
          </h2>
          <p style={{ fontSize: "13px", color: "var(--text-muted)", margin: "0 0 24px 0", lineHeight: "1.5" }}>
            Phase 3.1 establishes your authoritative academic identity, institutional affiliation, and external scholarly identifiers (ORCID / OpenAlex).
          </p>

          {error && (
            <div
              style={{
                background: "#fef2f2",
                border: "1px solid #fecaca",
                color: "#991b1b",
                padding: "10px 14px",
                borderRadius: "var(--radius-sm)",
                marginBottom: "20px",
                fontSize: "13px",
                display: "flex",
                alignItems: "center",
                gap: "8px",
                textAlign: "left",
              }}
            >
              <AlertCircle size={16} />
              {error}
            </div>
          )}

          <form onSubmit={handleCreateDefaultProfile} style={{ display: "grid", gap: "14px", textAlign: "left" }}>
            <div>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
                Full Display Name
              </label>
              <input
                type="text"
                value={initName}
                onChange={(e) => setInitName(e.target.value)}
                style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border-color)", borderRadius: "var(--radius-sm)" }}
                required
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
                Academic Email Address
              </label>
              <input
                type="email"
                value={initEmail}
                onChange={(e) => setInitEmail(e.target.value)}
                style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border-color)", borderRadius: "var(--radius-sm)" }}
                required
              />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
                  Academic Stage
                </label>
                <select
                  value={initStatus}
                  onChange={(e) => setInitStatus(e.target.value)}
                  style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border-color)", borderRadius: "var(--radius-sm)", background: "#ffffff" }}
                >
                  <option value="UNDERGRADUATE">UNDERGRADUATE</option>
                  <option value="POSTGRADUATE">POSTGRADUATE</option>
                  <option value="PHD">PHD</option>
                  <option value="POSTDOC">POSTDOC</option>
                  <option value="FACULTY">FACULTY</option>
                  <option value="RESEARCHER">RESEARCHER</option>
                  <option value="OTHER">OTHER</option>
                </select>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
                  Institution Name
                </label>
                <input
                  type="text"
                  value={initInstitution}
                  onChange={(e) => setInitInstitution(e.target.value)}
                  placeholder="e.g. Stanford University"
                  style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border-color)", borderRadius: "var(--radius-sm)" }}
                />
              </div>
            </div>

            <div>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
                Department
              </label>
              <input
                type="text"
                value={initDept}
                onChange={(e) => setInitDept(e.target.value)}
                placeholder="e.g. Computer Science"
                style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border-color)", borderRadius: "var(--radius-sm)" }}
              />
            </div>

            <button
              type="submit"
              disabled={isInitializing}
              style={{
                marginTop: "8px",
                padding: "10px 18px",
                borderRadius: "var(--radius-sm)",
                border: "none",
                background: "var(--primary)",
                color: "#ffffff",
                fontWeight: 600,
                fontSize: "14px",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "8px",
              }}
            >
              <Sparkles size={16} />
              {isInitializing ? "Creating Profile..." : "Initialize Researcher Identity"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div>
      <ResearcherProfileView
        profile={profile}
        initialWorks={works}
        onProfileUpdated={handleProfileUpdated}
      />
      <div style={{ maxWidth: "1000px", margin: "0 auto", padding: "0 16px 40px 16px" }}>
        <ResearcherIntelligenceView
          intelligence={intelligence}
          loading={intelligenceLoading}
          error={intelligenceError}
          onRefresh={() => profile && loadIntelligence(profile.id, true)}
          isRefreshing={isRefreshingIntelligence}
        />
        <ResearcherPreferencesView
          intelligence={preferences}
          loading={preferencesLoading}
          error={preferencesError}
          onRefresh={() => profile && loadPreferences(profile.id, true)}
          isRefreshing={isRefreshingPreferences}
          onAddPreference={handleAddPreference}
          onDeletePreference={handleDeletePreference}
          userId={profile.user_id}
        />
        {/* Phase 4.7: Unified Research Intelligence & Recommendations */}
        <div style={{ marginTop: "36px" }}>
          <UnifiedResearchIntelligenceView
            key={`unified-intel-${feedbackRefreshKey}`}
            profileId={profile.id}
            userId={profile.user_id}
          />
        </div>
        <div style={{ marginTop: "36px" }}>
          <PersonalizedCandidatePreview
            candidatesResponse={candidates}
            loading={candidatesLoading}
            error={candidatesError}
            onRefresh={(options) => profile && loadCandidates(profile.id, options, true)}
            isRefreshing={isRefreshingCandidates}
          />
        </div>
        <div style={{ marginTop: "36px" }}>
          <PersonalizationSummaryView
            key={`pers-summary-${feedbackRefreshKey}`}
            profileId={profile.id}
            userId={profile.user_id}
            refreshTrigger={feedbackRefreshKey}
          />
        </div>
        <div style={{ marginTop: "36px" }}>
          <PersonalizedRankingPreview
            key={`ranking-${feedbackRefreshKey}`}
            profileId={profile.id}
            userId={profile.user_id}
            onFeedbackRecorded={() => setFeedbackRefreshKey((k) => k + 1)}
          />
        </div>
        <div style={{ marginTop: "36px" }}>
          <FeedbackHistoryView
            key={`feedback-${feedbackRefreshKey}`}
            profileId={profile.id}
            userId={profile.user_id}
            onFeedbackChanged={() => setFeedbackRefreshKey((k) => k + 1)}
          />
        </div>
        <div style={{ marginTop: "36px" }}>
          <RecommendationHistoryView
            key={`history-${feedbackRefreshKey}`}
            profileId={profile.id}
            userId={profile.user_id}
            refreshTrigger={feedbackRefreshKey}
          />
        </div>
      </div>
    </div>
  );
}


export default function ResearcherPageRoute() {
  return (
    <RequireAuth>
      <ResearcherPage  />
    </RequireAuth>
  );
}
