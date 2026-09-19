"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  Banknote,
  BookOpen,
  Briefcase,
  Building,
  Check,
  CheckCircle2,
  ChevronRight,
  Clock,
  Compass,
  DollarSign,
  Globe,
  GraduationCap,
  HelpCircle,
  Laptop,
  Layers,
  MapPin,
  MinusCircle,
  Plus,
  RefreshCw,
  Save,
  ShieldAlert,
  Sliders,
  Sparkles,
  Tag,
  Trash2,
  Undo2,
  X,
  XCircle,
} from "lucide-react";
import type {
  BulkPreferenceItem,
  PreferenceCategory,
  PreferenceConflict,
  PreferenceState,
  PreferenceType,
  ResearcherPreferenceCreatePayload,
  ResearcherPreferenceItem,
  ResearcherProfile,
  StructuredPreferencesResponse,
} from "../../../types/researcher";
import {
  bulkUpdateResearcherPreferences,
  createResearcherPreference,
  deleteResearcherPreference,
  fetchResearcherProfile,
  fetchStructuredResearcherPreferences,
  updateResearcherPreference,
} from "../../../services/api";

const CANONICAL_OPP_TYPES = [
  { value: "CONFERENCE", label: "Conference" },
  { value: "WORKSHOP", label: "Workshop" },
  { value: "JOURNAL", label: "Journal" },
  { value: "CALL_FOR_PAPERS", label: "Call for Papers" },
  { value: "SPECIAL_ISSUE", label: "Special Issue" },
  { value: "FELLOWSHIP", label: "Fellowship" },
  { value: "GRANT", label: "Grant" },
  { value: "INTERNSHIP", label: "Internship" },
];

const CANONICAL_DELIVERY_MODES = [
  { value: "ONLINE", label: "Online / Remote" },
  { value: "OFFLINE", label: "In-Person (Offline)" },
  { value: "HYBRID", label: "Hybrid" },
];

const COMMON_REGIONS = [
  "North America",
  "Europe",
  "United Kingdom",
  "Asia-Pacific",
  "India",
  "Latin America",
  "Middle East & Africa",
];

const CAREER_STAGES = [
  { value: "EARLY_CAREER", label: "Early Career (< 5 years post-PhD)" },
  { value: "MID_CAREER", label: "Mid-Career (5–15 years post-PhD)" },
  { value: "SENIOR", label: "Senior / Principal Investigator" },
];

const ACADEMIC_LEVELS = [
  { value: "UNDERGRADUATE", label: "Undergraduate" },
  { value: "POSTGRADUATE", label: "Postgraduate / Master's" },
  { value: "PHD_STUDENT", label: "PhD Student" },
  { value: "POSTDOC", label: "Postdoctoral Researcher" },
  { value: "FACULTY", label: "Faculty / Professor" },
  { value: "INDUSTRY_RESEARCHER", label: "Industry Researcher" },
];

export default function ResearcherPreferencesPage() {
  const [profile, setProfile] = useState<ResearcherProfile | null>(null);
  const [structuredPrefs, setStructuredPrefs] = useState<StructuredPreferencesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Local state for interactive editing
  const [newTopicInput, setNewTopicInput] = useState("");
  const [newTopicType, setNewTopicType] = useState<PreferenceType>("PREFERRED");
  const [newKeywordInput, setNewKeywordInput] = useState("");
  const [newRegionInput, setNewRegionInput] = useState("");
  const [newRegionType, setNewRegionType] = useState<PreferenceType>("PREFERRED");
  const [newInstitutionInput, setNewInstitutionInput] = useState("");
  const [newInstitutionType, setNewInstitutionType] = useState<PreferenceType>("PREFERRED");

  // Funding state
  const [fundingRequired, setFundingRequired] = useState(false);
  const [minFunding, setMinFunding] = useState<string>("");
  const [currency, setCurrency] = useState("USD");

  // Academic state
  const [academicLevel, setAcademicLevel] = useState<string>("");
  const [careerStage, setCareerStage] = useState<string>("");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Fetch current researcher profile
      const demoEmail = "researcher@university.edu";
      let prof: ResearcherProfile | null = null;
      try {
        prof = await fetchResearcherProfile(demoEmail);
        setProfile(prof);
      } catch {
        // Not found or network error
      }

      if (prof) {
        // 2. Fetch structured preferences
        const prefs = await fetchStructuredResearcherPreferences(prof.id);
        setStructuredPrefs(prefs);

        // Sync local form state
        setFundingRequired(prefs.funding.funding_required);
        setMinFunding(prefs.funding.min_funding_amount ? String(prefs.funding.min_funding_amount) : "");
        setCurrency(prefs.funding.currency || "USD");
        setAcademicLevel(prefs.academic.academic_level || "");
        setCareerStage(prefs.academic.career_stage || "");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load preferences";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Derive active preferences map
  const rawPreferences = structuredPrefs?.raw_preferences || [];

  const getOppTypeState = (val: string): PreferenceState => {
    const item = rawPreferences.find(
      (p) => p.category === "OPPORTUNITY_TYPE" && p.preference_value.toUpperCase() === val.toUpperCase() && p.is_active
    );
    if (!item) return "NEUTRAL";
    return item.preference_type === "EXCLUDED" ? "EXCLUDED" : "PREFERRED";
  };

  const getDeliveryModeState = (val: string): PreferenceState => {
    const item = rawPreferences.find(
      (p) => p.category === "DELIVERY_MODE" && p.preference_value.toUpperCase() === val.toUpperCase() && p.is_active
    );
    if (!item) return "NEUTRAL";
    return item.preference_type === "EXCLUDED" ? "EXCLUDED" : "PREFERRED";
  };

  // 3-state toggle handler for opportunity types
  const handleCycleOppType = async (val: string, label: string) => {
    if (!profile) return;
    const currentState = getOppTypeState(val);
    const existing = rawPreferences.find(
      (p) => p.category === "OPPORTUNITY_TYPE" && p.preference_value.toUpperCase() === val.toUpperCase()
    );

    setIsSaving(true);
    setSuccessMessage(null);
    try {
      if (currentState === "NEUTRAL") {
        // Cycle: NEUTRAL -> PREFERRED
        await createResearcherPreference(
          profile.id,
          {
            category: "OPPORTUNITY_TYPE",
            preference_type: "PREFERRED",
            preference_key: "opportunity_type",
            preference_value: val,
            display_label: label,
            strength: 1.0,
            is_active: true,
          },
          profile.user_id
        );
      } else if (currentState === "PREFERRED") {
        // Cycle: PREFERRED -> EXCLUDED
        if (existing) {
          await updateResearcherPreference(
            profile.id,
            existing.id,
            { preference_type: "EXCLUDED" },
            profile.user_id
          );
        }
      } else {
        // Cycle: EXCLUDED -> NEUTRAL (delete preference row)
        if (existing) {
          await deleteResearcherPreference(profile.id, existing.id, profile.user_id);
        }
      }
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to update preference");
    } finally {
      setIsSaving(false);
    }
  };

  // 3-state toggle handler for delivery modes
  const handleCycleDeliveryMode = async (val: string, label: string) => {
    if (!profile) return;
    const currentState = getDeliveryModeState(val);
    const existing = rawPreferences.find(
      (p) => p.category === "DELIVERY_MODE" && p.preference_value.toUpperCase() === val.toUpperCase()
    );

    setIsSaving(true);
    setSuccessMessage(null);
    try {
      if (currentState === "NEUTRAL") {
        await createResearcherPreference(
          profile.id,
          {
            category: "DELIVERY_MODE",
            preference_type: "PREFERRED",
            preference_key: "delivery_mode",
            preference_value: val,
            display_label: label,
            strength: 1.0,
            is_active: true,
          },
          profile.user_id
        );
      } else if (currentState === "PREFERRED") {
        if (existing) {
          await updateResearcherPreference(
            profile.id,
            existing.id,
            { preference_type: "EXCLUDED" },
            profile.user_id
          );
        }
      } else {
        if (existing) {
          await deleteResearcherPreference(profile.id, existing.id, profile.user_id);
        }
      }
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to update preference");
    } finally {
      setIsSaving(false);
    }
  };

  // Add topic with explicit preference_type
  const handleAddTopic = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const clean = newTopicInput.trim();
    if (!clean || !profile || isSaving) return;

    setIsSaving(true);
    setSuccessMessage(null);
    try {
      await createResearcherPreference(
        profile.id,
        {
          category: "TOPIC",
          preference_type: newTopicType,
          preference_key: "topic",
          preference_value: clean,
          display_label: clean,
          strength: 1.0,
          is_active: true,
        },
        profile.user_id
      );
      setNewTopicInput("");
      await loadData();
      setSuccessMessage(`Added "${clean}" as ${newTopicType.toLowerCase()} topic.`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to add topic");
    } finally {
      setIsSaving(false);
    }
  };

  // Add keyword
  const handleAddKeyword = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const clean = newKeywordInput.trim();
    if (!clean || !profile || isSaving) return;

    setIsSaving(true);
    setSuccessMessage(null);
    try {
      await createResearcherPreference(
        profile.id,
        {
          category: "KEYWORD",
          preference_type: "PREFERRED",
          preference_key: "keyword",
          preference_value: clean,
          display_label: clean,
          strength: 1.0,
          is_active: true,
        },
        profile.user_id
      );
      setNewKeywordInput("");
      await loadData();
      setSuccessMessage(`Added keyword "${clean}".`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to add keyword");
    } finally {
      setIsSaving(false);
    }
  };

  // Add region
  const handleAddRegion = async (val: string, type: PreferenceType) => {
    if (!val || !profile || isSaving) return;

    setIsSaving(true);
    setSuccessMessage(null);
    try {
      await createResearcherPreference(
        profile.id,
        {
          category: "REGION",
          preference_type: type,
          preference_key: "region",
          preference_value: val,
          display_label: val,
          strength: 1.0,
          is_active: true,
        },
        profile.user_id
      );
      setNewRegionInput("");
      await loadData();
      setSuccessMessage(`Configured region "${val}" as ${type.toLowerCase()}.`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to add region");
    } finally {
      setIsSaving(false);
    }
  };

  // Add institution
  const handleAddInstitution = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const clean = newInstitutionInput.trim();
    if (!clean || !profile || isSaving) return;

    setIsSaving(true);
    setSuccessMessage(null);
    try {
      await createResearcherPreference(
        profile.id,
        {
          category: "INSTITUTION",
          preference_type: newInstitutionType,
          preference_key: "institution",
          preference_value: clean,
          display_label: clean,
          strength: 1.0,
          is_active: true,
        },
        profile.user_id
      );
      setNewInstitutionInput("");
      await loadData();
      setSuccessMessage(`Configured institution "${clean}" as ${newInstitutionType.toLowerCase()}.`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to add institution");
    } finally {
      setIsSaving(false);
    }
  };

  // Save Funding & Academic settings
  const handleSaveFundingAndAcademic = async () => {
    if (!profile || isSaving) return;

    setIsSaving(true);
    setSuccessMessage(null);
    setError(null);
    try {
      const itemsToSync: BulkPreferenceItem[] = [];

      // Funding required
      itemsToSync.push({
        category: "FUNDING",
        preference_type: "PREFERRED",
        preference_key: "funding_required",
        preference_value: String(fundingRequired),
        display_label: fundingRequired ? "Funding Required" : "Funding Optional",
        strength: 1.0,
        is_active: true,
      });

      // Min funding
      if (minFunding.trim()) {
        itemsToSync.push({
          category: "FUNDING",
          preference_type: "PREFERRED",
          preference_key: "min_amount",
          preference_value: minFunding.trim(),
          display_label: `Min Funding: ${currency} ${minFunding.trim()}`,
          strength: 1.0,
          is_active: true,
        });
      }

      // Currency
      itemsToSync.push({
        category: "FUNDING",
        preference_type: "PREFERRED",
        preference_key: "currency",
        preference_value: currency,
        display_label: `Currency: ${currency}`,
        strength: 1.0,
        is_active: true,
      });

      // Academic level
      if (academicLevel) {
        const found = ACADEMIC_LEVELS.find((l) => l.value === academicLevel);
        itemsToSync.push({
          category: "ACADEMIC_LEVEL",
          preference_type: "PREFERRED",
          preference_key: "academic_level",
          preference_value: academicLevel,
          display_label: found ? found.label : academicLevel,
          strength: 1.0,
          is_active: true,
        });
      }

      // Career stage
      if (careerStage) {
        const found = CAREER_STAGES.find((s) => s.value === careerStage);
        itemsToSync.push({
          category: "CAREER_STAGE",
          preference_type: "PREFERRED",
          preference_key: "career_stage",
          preference_value: careerStage,
          display_label: found ? found.label : careerStage,
          strength: 1.0,
          is_active: true,
        });
      }

      await bulkUpdateResearcherPreferences(
        profile.id,
        {
          preferences: itemsToSync,
          replace_existing: false,
        },
        profile.user_id
      );

      await loadData();
      setSuccessMessage("Funding and academic preferences saved successfully.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setIsSaving(false);
    }
  };

  // Delete any preference item
  const handleDeleteItem = async (id: string) => {
    if (!profile || isSaving) return;
    setIsSaving(true);
    setSuccessMessage(null);
    try {
      await deleteResearcherPreference(profile.id, id, profile.user_id);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to delete preference");
    } finally {
      setIsSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ maxWidth: "1200px", margin: "40px auto", padding: "0 24px", textAlign: "center" }}>
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: "12px" }}>
          <RefreshCw size={24} className="animate-spin" color="var(--primary)" />
          <span style={{ fontSize: "16px", color: "var(--text-muted)", fontWeight: 500 }}>
            Loading researcher preference configuration...
          </span>
        </div>
      </div>
    );
  }

  const conflicts = structuredPrefs?.summary.has_conflicts;
  const completeness = structuredPrefs?.completeness;

  return (
    <div style={{ maxWidth: "1200px", margin: "32px auto", padding: "0 24px" }}>
      {/* Breadcrumb Navigation */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "20px" }}>
        <Link
          href="/researcher"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            fontSize: "13px",
            color: "var(--text-muted)",
            textDecoration: "none",
          }}
        >
          <ArrowLeft size={14} />
          <span>Researcher Profile</span>
        </Link>
        <ChevronRight size={14} color="var(--text-muted)" />
        <span style={{ fontSize: "13px", color: "var(--text-main)", fontWeight: 600 }}>
          Preference Center (Phase 5.1)
        </span>
      </div>

      {/* Hero Header */}
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "var(--radius-lg)",
          padding: "28px 32px",
          marginBottom: "24px",
          boxShadow: "var(--shadow-sm)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexWrap: "wrap",
          gap: "20px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "8px" }}>
            <div
              style={{
                width: "40px",
                height: "40px",
                borderRadius: "10px",
                background: "linear-gradient(135deg, #0ea5e9, #6366f1)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#fff",
              }}
            >
              <Sliders size={22} />
            </div>
            <div>
              <h1 style={{ margin: 0, fontSize: "24px", fontWeight: 700, color: "var(--text-main)" }}>
                Researcher Preferences Foundation
              </h1>
              <p style={{ margin: "2px 0 0 0", fontSize: "13px", color: "var(--text-muted)" }}>
                Explicit 3-state configuration: Preferred ≠ Excluded ≠ Neutral (Unspecified).
              </p>
            </div>
          </div>
        </div>

        {/* Status Indicators */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
          {completeness && (
            <div
              style={{
                padding: "8px 14px",
                background: "rgba(14, 165, 233, 0.08)",
                border: "1px solid rgba(14, 165, 233, 0.25)",
                borderRadius: "var(--radius-md)",
                fontSize: "13px",
                fontWeight: 600,
                color: "var(--primary)",
              }}
            >
              Completeness: {completeness.percentage}%
            </div>
          )}

          <button
            onClick={loadData}
            disabled={isSaving}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "8px 14px",
              background: "var(--bg-hover)",
              border: "1px solid var(--border-color)",
              borderRadius: "var(--radius-md)",
              fontSize: "13px",
              fontWeight: 500,
              color: "var(--text-main)",
              cursor: "pointer",
            }}
          >
            <RefreshCw size={14} className={isSaving ? "animate-spin" : ""} />
            <span>Reload</span>
          </button>
        </div>
      </div>

      {/* Notifications / Alerts */}
      {successMessage && (
        <div
          style={{
            padding: "12px 18px",
            background: "rgba(22, 163, 74, 0.1)",
            border: "1px solid rgba(22, 163, 74, 0.3)",
            borderRadius: "var(--radius-md)",
            marginBottom: "20px",
            display: "flex",
            alignItems: "center",
            gap: "10px",
            color: "#15803d",
            fontSize: "13px",
            fontWeight: 500,
          }}
        >
          <CheckCircle2 size={16} />
          <span>{successMessage}</span>
        </div>
      )}

      {error && (
        <div
          style={{
            padding: "12px 18px",
            background: "rgba(220, 38, 38, 0.1)",
            border: "1px solid rgba(220, 38, 38, 0.3)",
            borderRadius: "var(--radius-md)",
            marginBottom: "20px",
            display: "flex",
            alignItems: "center",
            gap: "10px",
            color: "#b91c1c",
            fontSize: "13px",
            fontWeight: 500,
          }}
        >
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* 3-State Legend */}
      <div
        style={{
          background: "var(--bg-hover)",
          border: "1px solid var(--border-color)",
          borderRadius: "var(--radius-md)",
          padding: "12px 18px",
          marginBottom: "24px",
          display: "flex",
          alignItems: "center",
          gap: "24px",
          flexWrap: "wrap",
          fontSize: "12px",
          color: "var(--text-muted)",
        }}
      >
        <span style={{ fontWeight: 600, color: "var(--text-main)" }}>State Legend:</span>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#16a34a" }} />
          <span><strong>Preferred:</strong> Explicitly desired opportunity attribute</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#6b7280" }} />
          <span><strong>Neutral:</strong> Unspecified (absence of preference ≠ negative preference)</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#dc2626" }} />
          <span><strong>Excluded:</strong> Explicitly filtered out dimension</span>
        </div>
      </div>

      {/* Grid of Preference Modules */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "24px" }}>
        
        {/* Module 1: Opportunity Types (3-State) */}
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-lg)",
            padding: "24px",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
            <Layers size={18} color="var(--primary)" />
            <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "var(--text-main)" }}>
              Opportunity Formats
            </h2>
          </div>
          <p style={{ margin: "0 0 16px 0", fontSize: "12px", color: "var(--text-muted)" }}>
            Click to cycle: <strong>Neutral</strong> &rarr; <strong>Preferred</strong> &rarr; <strong>Excluded</strong> &rarr; <strong>Neutral</strong>.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {CANONICAL_OPP_TYPES.map((t) => {
              const state = getOppTypeState(t.value);
              return (
                <div
                  key={t.value}
                  onClick={() => handleCycleOppType(t.value, t.label)}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "10px 14px",
                    borderRadius: "var(--radius-md)",
                    fontSize: "13px",
                    cursor: "pointer",
                    border:
                      state === "PREFERRED"
                        ? "1px solid rgba(22, 163, 74, 0.4)"
                        : state === "EXCLUDED"
                        ? "1px solid rgba(220, 38, 38, 0.4)"
                        : "1px solid var(--border-color)",
                    background:
                      state === "PREFERRED"
                        ? "rgba(22, 163, 74, 0.08)"
                        : state === "EXCLUDED"
                        ? "rgba(220, 38, 38, 0.08)"
                        : "var(--bg-hover)",
                    transition: "all 0.15s ease",
                  }}
                >
                  <span style={{ fontWeight: 600, color: "var(--text-main)" }}>{t.label}</span>
                  <span
                    style={{
                      fontSize: "11px",
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: "10px",
                      background:
                        state === "PREFERRED"
                          ? "#16a34a"
                          : state === "EXCLUDED"
                          ? "#dc2626"
                          : "var(--border-color)",
                      color: state === "NEUTRAL" ? "var(--text-muted)" : "#fff",
                    }}
                  >
                    {state}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Module 2: Delivery Modes (3-State) */}
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-lg)",
            padding: "24px",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
            <Laptop size={18} color="#8b5cf6" />
            <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "var(--text-main)" }}>
              Delivery Modes
            </h2>
          </div>
          <p style={{ margin: "0 0 16px 0", fontSize: "12px", color: "var(--text-muted)" }}>
            Participation format preference for conferences, workshops, and calls.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {CANONICAL_DELIVERY_MODES.map((m) => {
              const state = getDeliveryModeState(m.value);
              return (
                <div
                  key={m.value}
                  onClick={() => handleCycleDeliveryMode(m.value, m.label)}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "10px 14px",
                    borderRadius: "var(--radius-md)",
                    fontSize: "13px",
                    cursor: "pointer",
                    border:
                      state === "PREFERRED"
                        ? "1px solid rgba(139, 92, 246, 0.4)"
                        : state === "EXCLUDED"
                        ? "1px solid rgba(220, 38, 38, 0.4)"
                        : "1px solid var(--border-color)",
                    background:
                      state === "PREFERRED"
                        ? "rgba(139, 92, 246, 0.08)"
                        : state === "EXCLUDED"
                        ? "rgba(220, 38, 38, 0.08)"
                        : "var(--bg-hover)",
                    transition: "all 0.15s ease",
                  }}
                >
                  <span style={{ fontWeight: 600, color: "var(--text-main)" }}>{m.label}</span>
                  <span
                    style={{
                      fontSize: "11px",
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: "10px",
                      background:
                        state === "PREFERRED"
                          ? "#8b5cf6"
                          : state === "EXCLUDED"
                          ? "#dc2626"
                          : "var(--border-color)",
                      color: state === "NEUTRAL" ? "var(--text-muted)" : "#fff",
                    }}
                  >
                    {state}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Module 3: Research Interests & Topics */}
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-lg)",
            padding: "24px",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
            <Tag size={18} color="#10b981" />
            <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "var(--text-main)" }}>
              Topics & Keywords
            </h2>
          </div>
          <p style={{ margin: "0 0 16px 0", fontSize: "12px", color: "var(--text-muted)" }}>
            Target specific research areas or explicitly exclude incompatible subfields.
          </p>

          {/* Existing Topics */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "16px" }}>
            {rawPreferences
              .filter((p) => p.category === "TOPIC" && p.is_active)
              .map((top) => {
                const isExcl = top.preference_type === "EXCLUDED";
                return (
                  <span
                    key={top.id}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "6px",
                      padding: "4px 10px",
                      background: isExcl ? "rgba(220, 38, 38, 0.1)" : "rgba(16, 185, 129, 0.1)",
                      border: isExcl ? "1px solid rgba(220, 38, 38, 0.3)" : "1px solid rgba(16, 185, 129, 0.3)",
                      borderRadius: "14px",
                      fontSize: "12px",
                      fontWeight: 500,
                      color: isExcl ? "#b91c1c" : "#065f46",
                    }}
                  >
                    <span>{isExcl ? `Excluded: ${top.display_label}` : top.display_label}</span>
                    <X
                      size={13}
                      style={{ cursor: "pointer" }}
                      onClick={() => handleDeleteItem(top.id)}
                    />
                  </span>
                );
              })}
          </div>

          {/* Add Topic Input */}
          <form onSubmit={handleAddTopic} style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
            <input
              type="text"
              placeholder="e.g. reinforcement-learning"
              value={newTopicInput}
              onChange={(e) => setNewTopicInput(e.target.value)}
              disabled={isSaving}
              style={{
                flex: 1,
                padding: "8px 12px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border-color)",
                background: "var(--bg-hover)",
                color: "var(--text-main)",
                fontSize: "13px",
              }}
            />
            <select
              value={newTopicType}
              onChange={(e) => setNewTopicType(e.target.value as PreferenceType)}
              style={{
                padding: "8px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border-color)",
                background: "var(--bg-hover)",
                color: "var(--text-main)",
                fontSize: "12px",
                fontWeight: 600,
              }}
            >
              <option value="PREFERRED">Prefer</option>
              <option value="EXCLUDED">Exclude</option>
            </select>
            <button
              type="submit"
              disabled={isSaving || !newTopicInput.trim()}
              style={{
                padding: "8px 14px",
                borderRadius: "var(--radius-sm)",
                background: "var(--primary)",
                border: "none",
                color: "#fff",
                fontSize: "13px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Add
            </button>
          </form>

          {/* Keywords */}
          <div style={{ marginTop: "16px", borderTop: "1px solid var(--border-color)", paddingTop: "14px" }}>
            <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-main)" }}>Keywords:</span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", margin: "8px 0" }}>
              {rawPreferences
                .filter((p) => p.category === "KEYWORD" && p.is_active)
                .map((kw) => (
                  <span
                    key={kw.id}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "6px",
                      padding: "3px 8px",
                      background: "var(--bg-hover)",
                      border: "1px solid var(--border-color)",
                      borderRadius: "10px",
                      fontSize: "11px",
                      color: "var(--text-main)",
                    }}
                  >
                    <span>{kw.preference_value}</span>
                    <X
                      size={12}
                      style={{ cursor: "pointer" }}
                      onClick={() => handleDeleteItem(kw.id)}
                    />
                  </span>
                ))}
            </div>
            <form onSubmit={handleAddKeyword} style={{ display: "flex", gap: "8px" }}>
              <input
                type="text"
                placeholder="Add keyword (e.g. transformer, graph-nn)"
                value={newKeywordInput}
                onChange={(e) => setNewKeywordInput(e.target.value)}
                disabled={isSaving}
                style={{
                  flex: 1,
                  padding: "6px 10px",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--border-color)",
                  background: "var(--bg-hover)",
                  color: "var(--text-main)",
                  fontSize: "12px",
                }}
              />
              <button
                type="submit"
                disabled={isSaving || !newKeywordInput.trim()}
                style={{
                  padding: "6px 12px",
                  borderRadius: "var(--radius-sm)",
                  background: "var(--bg-hover)",
                  border: "1px solid var(--border-color)",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                +
              </button>
            </form>
          </div>
        </div>

        {/* Module 4: Geographic & Institutional */}
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-lg)",
            padding: "24px",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
            <Globe size={18} color="#0284c7" />
            <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "var(--text-main)" }}>
              Geographic & Institutions
            </h2>
          </div>
          <p style={{ margin: "0 0 16px 0", fontSize: "12px", color: "var(--text-muted)" }}>
            Target specific geographic regions or institutions.
          </p>

          {/* Quick Region Buttons */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "14px" }}>
            {COMMON_REGIONS.map((reg) => {
              const match = rawPreferences.find(
                (p) => (p.category === "REGION" || p.category === "LOCATION") && p.preference_value.toLowerCase() === reg.toLowerCase() && p.is_active
              );
              const isPref = match && match.preference_type === "PREFERRED";
              const isExcl = match && match.preference_type === "EXCLUDED";
              return (
                <button
                  key={reg}
                  onClick={() => {
                    if (match) {
                      handleDeleteItem(match.id);
                    } else {
                      handleAddRegion(reg, "PREFERRED");
                    }
                  }}
                  style={{
                    padding: "4px 10px",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "12px",
                    fontWeight: 500,
                    cursor: "pointer",
                    border: isPref
                      ? "1px solid #0284c7"
                      : isExcl
                      ? "1px solid #dc2626"
                      : "1px solid var(--border-color)",
                    background: isPref
                      ? "rgba(2, 132, 199, 0.12)"
                      : isExcl
                      ? "rgba(220, 38, 38, 0.12)"
                      : "var(--bg-hover)",
                    color: isPref ? "#0284c7" : isExcl ? "#dc2626" : "var(--text-main)",
                  }}
                >
                  {isPref && <Check size={12} style={{ display: "inline", marginRight: "4px" }} />}
                  {isExcl && <X size={12} style={{ display: "inline", marginRight: "4px" }} />}
                  <span>{reg}</span>
                </button>
              );
            })}
          </div>

          {/* Add Institution */}
          <form onSubmit={handleAddInstitution} style={{ display: "flex", gap: "8px", marginTop: "14px" }}>
            <input
              type="text"
              placeholder="Target / Exclude Institution..."
              value={newInstitutionInput}
              onChange={(e) => setNewInstitutionInput(e.target.value)}
              disabled={isSaving}
              style={{
                flex: 1,
                padding: "8px 12px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border-color)",
                background: "var(--bg-hover)",
                color: "var(--text-main)",
                fontSize: "13px",
              }}
            />
            <select
              value={newInstitutionType}
              onChange={(e) => setNewInstitutionType(e.target.value as PreferenceType)}
              style={{
                padding: "8px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border-color)",
                background: "var(--bg-hover)",
                color: "var(--text-main)",
                fontSize: "12px",
                fontWeight: 600,
              }}
            >
              <option value="PREFERRED">Prefer</option>
              <option value="EXCLUDED">Exclude</option>
            </select>
            <button
              type="submit"
              disabled={isSaving || !newInstitutionInput.trim()}
              style={{
                padding: "8px 14px",
                borderRadius: "var(--radius-sm)",
                background: "var(--primary)",
                border: "none",
                color: "#fff",
                fontSize: "13px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Add
            </button>
          </form>
        </div>

        {/* Module 5: Funding & Academic Stage */}
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-lg)",
            padding: "24px",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
            <Banknote size={18} color="#eab308" />
            <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "var(--text-main)" }}>
              Funding & Career Stage
            </h2>
          </div>
          <p style={{ margin: "0 0 16px 0", fontSize: "12px", color: "var(--text-muted)" }}>
            Specify funding requirements and your current career trajectory.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            {/* Funding Required Toggle */}
            <label style={{ display: "flex", alignItems: "center", gap: "10px", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={fundingRequired}
                onChange={(e) => setFundingRequired(e.target.checked)}
                style={{ width: "16px", height: "16px", cursor: "pointer" }}
              />
              <span style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-main)" }}>
                Funding Required for Opportunities
              </span>
            </label>

            {/* Min Funding Amount */}
            <div style={{ display: "flex", gap: "8px" }}>
              <input
                type="number"
                placeholder="Min Funding Amount"
                value={minFunding}
                onChange={(e) => setMinFunding(e.target.value)}
                style={{
                  flex: 1,
                  padding: "8px 12px",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--border-color)",
                  background: "var(--bg-hover)",
                  color: "var(--text-main)",
                  fontSize: "13px",
                }}
              />
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                style={{
                  padding: "8px 12px",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--border-color)",
                  background: "var(--bg-hover)",
                  color: "var(--text-main)",
                  fontSize: "13px",
                }}
              >
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="GBP">GBP</option>
                <option value="INR">INR</option>
              </select>
            </div>

            {/* Academic Level */}
            <div>
              <span style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-main)", marginBottom: "4px" }}>
                Academic Level:
              </span>
              <select
                value={academicLevel}
                onChange={(e) => setAcademicLevel(e.target.value)}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--border-color)",
                  background: "var(--bg-hover)",
                  color: "var(--text-main)",
                  fontSize: "13px",
                }}
              >
                <option value="">-- Select Academic Level --</option>
                {ACADEMIC_LEVELS.map((lvl) => (
                  <option key={lvl.value} value={lvl.value}>
                    {lvl.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Career Stage */}
            <div>
              <span style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-main)", marginBottom: "4px" }}>
                Career Stage:
              </span>
              <select
                value={careerStage}
                onChange={(e) => setCareerStage(e.target.value)}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--border-color)",
                  background: "var(--bg-hover)",
                  color: "var(--text-main)",
                  fontSize: "13px",
                }}
              >
                <option value="">-- Select Career Stage --</option>
                {CAREER_STAGES.map((stg) => (
                  <option key={stg.value} value={stg.value}>
                    {stg.label}
                  </option>
                ))}
              </select>
            </div>

            <button
              onClick={handleSaveFundingAndAcademic}
              disabled={isSaving}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "8px",
                padding: "10px",
                background: "var(--primary)",
                border: "none",
                borderRadius: "var(--radius-md)",
                color: "#fff",
                fontSize: "13px",
                fontWeight: 600,
                cursor: "pointer",
                marginTop: "6px",
              }}
            >
              <Save size={15} />
              <span>Save Funding & Academic Settings</span>
            </button>
          </div>
        </div>

        {/* Module 6: Explicit Exclusions Summary */}
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid rgba(220, 38, 38, 0.3)",
            borderRadius: "var(--radius-lg)",
            padding: "24px",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
            <ShieldAlert size={18} color="#dc2626" />
            <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "var(--text-main)" }}>
              Explicit Exclusions
            </h2>
          </div>
          <p style={{ margin: "0 0 16px 0", fontSize: "12px", color: "var(--text-muted)" }}>
            These attributes are explicitly excluded from your discovery profile. Click the remove button to reset to neutral.
          </p>

          {rawPreferences.filter((p) => p.preference_type === "EXCLUDED" && p.is_active).length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {rawPreferences
                .filter((p) => p.preference_type === "EXCLUDED" && p.is_active)
                .map((excl) => (
                  <div
                    key={excl.id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "8px 12px",
                      background: "rgba(220, 38, 38, 0.06)",
                      border: "1px solid rgba(220, 38, 38, 0.2)",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "12px",
                    }}
                  >
                    <div>
                      <span style={{ fontWeight: 600, color: "#dc2626" }}>[{excl.category}]</span>{" "}
                      <span style={{ color: "var(--text-main)" }}>{excl.display_label}</span>
                    </div>
                    <button
                      onClick={() => handleDeleteItem(excl.id)}
                      style={{
                        background: "none",
                        border: "none",
                        cursor: "pointer",
                        color: "var(--text-muted)",
                      }}
                      title="Reset to neutral"
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
            </div>
          ) : (
            <p style={{ fontSize: "13px", color: "var(--text-muted)", fontStyle: "italic", margin: 0 }}>
              No explicit exclusions configured. All unselected options remain neutral.
            </p>
          )}
        </div>

      </div>
    </div>
  );
}
