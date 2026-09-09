"use client";

import React, { useEffect, useState } from "react";
import type { ResearcherProfile, ResearcherWorkSummary } from "../../types/researcher";
import { ResearcherProfileView } from "../../components/researcher/ResearcherProfileView";
import { createResearcherProfile, fetchResearcherProfile, fetchResearcherWorks } from "../../services/api";
import { AlertCircle, Loader2, Sparkles, UserPlus } from "lucide-react";

// Default demo ID or fallback initialization for developer/preview usage
const DEFAULT_DEMO_EMAIL = "researcher@university.edu";

export default function ResearcherPage() {
  const [profile, setProfile] = useState<ResearcherProfile | null>(null);
  const [works, setWorks] = useState<ResearcherWorkSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isInitializing, setIsInitializing] = useState(false);

  // New profile creation state
  const [initName, setInitName] = useState("Dr. Alex Rivera");
  const [initEmail, setInitEmail] = useState(DEFAULT_DEMO_EMAIL);
  const [initInstitution, setInitInstitution] = useState("Tech University");
  const [initDept, setInitDept] = useState("Computer Science");
  const [initStatus, setInitStatus] = useState("FACULTY");

  useEffect(() => {
    let cancelled = false;

    async function loadActiveProfile() {
      setLoading(true);
      setError(null);

      // Attempt to load from stored profile ID in localStorage if available
      const storedId = typeof window !== "undefined" ? localStorage.getItem("researchconnect_active_profile_id") : null;

      if (storedId) {
        try {
          const loaded = await fetchResearcherProfile(storedId);
          if (!cancelled) {
            setProfile(loaded);
            if (loaded.canonical_researcher_id) {
              const loadedWorks = await fetchResearcherWorks(loaded.id).catch(() => []);
              if (!cancelled) setWorks(loadedWorks);
            }
            setLoading(false);
            return;
          }
        } catch {
          // If stored ID not found on server, clear and fall through to initialization prompt
          if (typeof window !== "undefined") {
            localStorage.removeItem("researchconnect_active_profile_id");
          }
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
  }, []);

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

      if (typeof window !== "undefined") {
        localStorage.setItem("researchconnect_active_profile_id", created.id);
      }
      setProfile(created);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to initialize profile";
      setError(msg);
    } finally {
      setIsInitializing(false);
    }
  };

  const handleProfileUpdated = (updated: ResearcherProfile) => {
    setProfile(updated);
    if (typeof window !== "undefined") {
      localStorage.setItem("researchconnect_active_profile_id", updated.id);
    }
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
    <ResearcherProfileView
      profile={profile}
      initialWorks={works}
      onProfileUpdated={handleProfileUpdated}
    />
  );
}
