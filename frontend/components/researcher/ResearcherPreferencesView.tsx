"use client";

import React, { useState } from "react";
import {
  AlertTriangle,
  BookmarkCheck,
  Check,
  CheckCircle2,
  Clock,
  Compass,
  Globe,
  HelpCircle,
  Laptop,
  Layers,
  MapPin,
  Plus,
  RefreshCw,
  Sliders,
  Sparkles,
  Tag,
  Trash2,
  Unlock,
  X,
} from "lucide-react";
import type {
  PreferenceCategory,
  ResearcherPreferenceCreatePayload,
  ResearcherPreferenceIntelligenceResponse,
  ResearcherPreferenceItem,
} from "../../types/researcher";

interface ResearcherPreferencesViewProps {
  intelligence: ResearcherPreferenceIntelligenceResponse | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  isRefreshing: boolean;
  onAddPreference: (payload: ResearcherPreferenceCreatePayload) => Promise<void>;
  onDeletePreference: (preferenceId: string) => Promise<void>;
  userId?: string;
}

const CANONICAL_OPP_TYPES = [
  { value: "CONFERENCE", label: "Conference" },
  { value: "WORKSHOP", label: "Workshop" },
  { value: "JOURNAL", label: "Journal" },
  { value: "CALL_FOR_PAPERS", label: "Call for Papers" },
  { value: "SPECIAL_ISSUE", label: "Special Issue" },
];

const CANONICAL_DELIVERY_MODES = [
  { value: "ONLINE", label: "Online / Remote" },
  { value: "OFFLINE", label: "In-Person (Offline)" },
  { value: "HYBRID", label: "Hybrid" },
];

const COMMON_REGIONS = ["India", "Europe", "United States", "United Kingdom", "Canada", "Asia"];

const DEADLINE_OPTIONS = [
  { value: "7", label: "At least 7 days notice" },
  { value: "14", label: "At least 14 days notice" },
  { value: "30", label: "At least 30 days notice" },
  { value: "60", label: "At least 60 days notice" },
];

export function ResearcherPreferencesView({
  intelligence,
  loading,
  error,
  onRefresh,
  isRefreshing,
  onAddPreference,
  onDeletePreference,
}: ResearcherPreferencesViewProps) {
  const [newTopicInput, setNewTopicInput] = useState("");
  const [newLocationInput, setNewLocationInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (loading) {
    return (
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "var(--radius-lg)",
          padding: "32px",
          marginTop: "24px",
          boxShadow: "var(--shadow-sm)",
          textAlign: "center",
        }}
      >
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: "10px" }}>
          <RefreshCw size={20} className="animate-spin" color="var(--primary)" />
          <span style={{ fontSize: "14px", color: "var(--text-muted)", fontWeight: 500 }}>
            Analyzing personal preference intelligence and conflict detection...
          </span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid #fecaca",
          borderRadius: "var(--radius-lg)",
          padding: "24px",
          marginTop: "24px",
          boxShadow: "var(--shadow-sm)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", color: "#991b1b" }}>
            <AlertTriangle size={18} />
            <span style={{ fontSize: "14px", fontWeight: 600 }}>Failed to load personal preferences</span>
          </div>
          <button
            onClick={onRefresh}
            style={{
              padding: "6px 12px",
              background: "#fee2e2",
              border: "1px solid #fca5a5",
              color: "#991b1b",
              borderRadius: "var(--radius-sm)",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const explicitPrefs = intelligence?.explicit_preferences || [];
  const inferredPrefs = intelligence?.inferred_preferences || [];
  const derivedCandidates = intelligence?.derived_candidates || [];
  const conflicts = intelligence?.conflicts || [];
  const completeness = intelligence?.completeness;
  const summary = intelligence?.summary;

  // Helper sets for quick active lookup
  const activeOppTypes = new Set(
    explicitPrefs
      .filter((p) => p.category === "OPPORTUNITY_TYPE" && p.is_active)
      .map((p) => p.preference_value)
  );

  const activeDeliveryModes = new Set(
    explicitPrefs
      .filter((p) => p.category === "DELIVERY_MODE" && p.is_active)
      .map((p) => p.preference_value)
  );

  const activeTopics = explicitPrefs.filter((p) => p.category === "TOPIC" && p.is_active);

  const activeLocations = explicitPrefs.filter((p) => p.category === "LOCATION" && p.is_active);
  const activeLocationVals = new Set(activeLocations.map((p) => p.preference_value));

  const activeDeadlines = explicitPrefs.filter((p) => p.category === "DEADLINE_WINDOW" && p.is_active);
  const activeDeadlineVal = activeDeadlines.length > 0 ? activeDeadlines[0].preference_value : null;

  const openAccessPref = explicitPrefs.find((p) => p.category === "OPEN_ACCESS" && p.is_active);
  const isOpenAccessPreferred = openAccessPref?.preference_value === "true";

  // Toggle Opportunity Type
  const handleToggleOppType = async (typeVal: string, typeLabel: string) => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      const existing = explicitPrefs.find(
        (p) => p.category === "OPPORTUNITY_TYPE" && p.preference_value === typeVal
      );
      if (existing) {
        await onDeletePreference(existing.id);
      } else {
        await onAddPreference({
          category: "OPPORTUNITY_TYPE" as PreferenceCategory,
          preference_key: "opportunity_type",
          preference_value: typeVal,
          display_label: typeLabel,
          strength: 1.0,
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Toggle Delivery Mode
  const handleToggleDeliveryMode = async (modeVal: string, modeLabel: string) => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      const existing = explicitPrefs.find(
        (p) => p.category === "DELIVERY_MODE" && p.preference_value === modeVal
      );
      if (existing) {
        await onDeletePreference(existing.id);
      } else {
        await onAddPreference({
          category: "DELIVERY_MODE" as PreferenceCategory,
          preference_key: "delivery_mode",
          preference_value: modeVal,
          display_label: modeLabel,
          strength: 1.0,
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Add Topic
  const handleAddTopic = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const clean = newTopicInput.trim();
    if (!clean || isSubmitting) return;

    setIsSubmitting(true);
    try {
      await onAddPreference({
        category: "TOPIC" as PreferenceCategory,
        preference_key: "topic",
        preference_value: clean,
        display_label: clean,
        strength: 1.0,
      });
      setNewTopicInput("");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Toggle Location
  const handleToggleLocation = async (locName: string) => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      const existing = explicitPrefs.find(
        (p) => p.category === "LOCATION" && p.preference_value.toLowerCase() === locName.toLowerCase()
      );
      if (existing) {
        await onDeletePreference(existing.id);
      } else {
        await onAddPreference({
          category: "LOCATION" as PreferenceCategory,
          preference_key: "location",
          preference_value: locName,
          display_label: locName,
          strength: 1.0,
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Select Deadline Window
  const handleSelectDeadline = async (val: string, label: string) => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      // Remove any existing deadline pref
      for (const d of activeDeadlines) {
        await onDeletePreference(d.id);
      }
      if (activeDeadlineVal !== val) {
        await onAddPreference({
          category: "DEADLINE_WINDOW" as PreferenceCategory,
          preference_key: "min_days_before_deadline",
          preference_value: val,
          display_label: label,
          strength: 1.0,
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Toggle Open Access
  const handleToggleOpenAccess = async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      if (openAccessPref) {
        await onDeletePreference(openAccessPref.id);
      } else {
        await onAddPreference({
          category: "OPEN_ACCESS" as PreferenceCategory,
          preference_key: "prefer_open_access",
          preference_value: "true",
          display_label: "Prefer Open Access",
          strength: 1.0,
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Adopt derived candidate from Phase 3.2 expertise
  const handleAdoptCandidate = async (candidate: ResearcherPreferenceItem) => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await onAddPreference({
        category: candidate.category as PreferenceCategory,
        preference_key: candidate.preference_key,
        preference_value: candidate.preference_value,
        display_label: candidate.display_label,
        canonical_id: candidate.canonical_id,
        strength: 1.0,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "var(--radius-lg)",
        padding: "32px",
        marginTop: "24px",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexWrap: "wrap",
          gap: "16px",
          marginBottom: "24px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "8px",
                background: "linear-gradient(135deg, #0ea5e9, #38bdf8)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#fff",
              }}
            >
              <Sliders size={20} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: "20px", fontWeight: 700, color: "var(--text-main)" }}>
                Personal Preferences
              </h3>
              <span style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                Phase 3.3 — Canonical preference intelligence and attribute affinity
              </span>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          {summary && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                padding: "6px 12px",
                background: "var(--bg-hover)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--border-color)",
                fontSize: "12px",
                fontWeight: 600,
                color: "var(--text-main)",
              }}
            >
              <span>Confidence:</span>
              <span
                style={{
                  color:
                    summary.confidence_level === "HIGH"
                      ? "#16a34a"
                      : summary.confidence_level === "MEDIUM"
                      ? "#ca8a04"
                      : "#6b7280",
                }}
              >
                {summary.confidence_level}
              </span>
            </div>
          )}

          <button
            onClick={onRefresh}
            disabled={isRefreshing || loading}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "7px 14px",
              background: "var(--bg-hover)",
              border: "1px solid var(--border-color)",
              borderRadius: "var(--radius-md)",
              fontSize: "13px",
              fontWeight: 500,
              color: "var(--text-main)",
              cursor: isRefreshing ? "not-allowed" : "pointer",
            }}
          >
            <RefreshCw size={14} className={isRefreshing ? "animate-spin" : ""} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Completeness Bar */}
      {completeness && (
        <div
          style={{
            background: "linear-gradient(135deg, rgba(14, 165, 233, 0.05), rgba(56, 189, 248, 0.02))",
            border: "1px solid rgba(14, 165, 233, 0.2)",
            borderRadius: "var(--radius-md)",
            padding: "16px 20px",
            marginBottom: "28px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <span style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-main)" }}>
              Preference Completeness: {completeness.percentage}%
            </span>
            <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
              {completeness.is_complete ? "Profile fully configured" : `${completeness.missing_dimensions.length} dimensions unconfigured`}
            </span>
          </div>

          <div
            style={{
              width: "100%",
              height: "8px",
              background: "var(--border-color)",
              borderRadius: "4px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${completeness.percentage}%`,
                height: "100%",
                background: "linear-gradient(90deg, #0ea5e9, #38bdf8)",
                borderRadius: "4px",
                transition: "width 0.4s ease",
              }}
            />
          </div>

          {completeness.missing_dimensions.length > 0 && (
            <div style={{ marginTop: "10px", display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Recommended to configure:</span>
              {completeness.missing_dimensions.map((dim) => (
                <span
                  key={dim}
                  style={{
                    fontSize: "11px",
                    padding: "2px 8px",
                    background: "#f1f5f9",
                    color: "#475569",
                    borderRadius: "12px",
                    border: "1px solid #cbd5e1",
                  }}
                >
                  {dim}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Conflicts Alert */}
      {conflicts.length > 0 && (
        <div
          style={{
            background: "#fffbeb",
            border: "1px solid #fde68a",
            borderRadius: "var(--radius-md)",
            padding: "16px",
            marginBottom: "28px",
          }}
        >
          <div style={{ display: "flex", alignItems: "flex-start", gap: "10px" }}>
            <AlertTriangle size={18} color="#d97706" style={{ marginTop: "2px", flexShrink: 0 }} />
            <div>
              <h4 style={{ margin: "0 0 4px 0", fontSize: "14px", fontWeight: 700, color: "#92400e" }}>
                Contradictory Preferences Detected
              </h4>
              {conflicts.map((c, i) => (
                <p key={i} style={{ margin: "2px 0", fontSize: "13px", color: "#b45309" }}>
                  • {c.reason}
                </p>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Grid of Preferences */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "24px" }}>
        {/* Opportunity Types */}
        <div
          style={{
            background: "var(--bg-hover)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-md)",
            padding: "20px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "14px" }}>
            <Layers size={16} color="var(--primary)" />
            <h4 style={{ margin: 0, fontSize: "15px", fontWeight: 600, color: "var(--text-main)" }}>
              Opportunity Types
            </h4>
          </div>
          <p style={{ margin: "0 0 14px 0", fontSize: "12px", color: "var(--text-muted)" }}>
            Select the formats of research opportunities you actively seek.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
            {CANONICAL_OPP_TYPES.map((t) => {
              const active = activeOppTypes.has(t.value);
              return (
                <button
                  key={t.value}
                  onClick={() => handleToggleOppType(t.value, t.label)}
                  disabled={isSubmitting}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "6px 12px",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "12px",
                    fontWeight: 500,
                    cursor: "pointer",
                    border: active ? "1px solid var(--primary)" : "1px solid var(--border-color)",
                    background: active ? "rgba(14, 165, 233, 0.15)" : "var(--bg-card)",
                    color: active ? "var(--primary)" : "var(--text-main)",
                    transition: "all 0.15s ease",
                  }}
                >
                  {active && <Check size={13} />}
                  <span>{t.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Delivery Modes */}
        <div
          style={{
            background: "var(--bg-hover)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-md)",
            padding: "20px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "14px" }}>
            <Laptop size={16} color="#8b5cf6" />
            <h4 style={{ margin: 0, fontSize: "15px", fontWeight: 600, color: "var(--text-main)" }}>
              Delivery Mode
            </h4>
          </div>
          <p style={{ margin: "0 0 14px 0", fontSize: "12px", color: "var(--text-muted)" }}>
            Participation format preference for events and conferences.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
            {CANONICAL_DELIVERY_MODES.map((m) => {
              const active = activeDeliveryModes.has(m.value);
              return (
                <button
                  key={m.value}
                  onClick={() => handleToggleDeliveryMode(m.value, m.label)}
                  disabled={isSubmitting}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "6px 12px",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "12px",
                    fontWeight: 500,
                    cursor: "pointer",
                    border: active ? "1px solid #8b5cf6" : "1px solid var(--border-color)",
                    background: active ? "rgba(139, 92, 246, 0.15)" : "var(--bg-card)",
                    color: active ? "#7c3aed" : "var(--text-main)",
                    transition: "all 0.15s ease",
                  }}
                >
                  {active && <Check size={13} />}
                  <span>{m.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Topic Preferences */}
        <div
          style={{
            background: "var(--bg-hover)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-md)",
            padding: "20px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "14px" }}>
            <Tag size={16} color="#10b981" />
            <h4 style={{ margin: 0, fontSize: "15px", fontWeight: 600, color: "var(--text-main)" }}>
              Preferred Topics
            </h4>
          </div>
          <p style={{ margin: "0 0 14px 0", fontSize: "12px", color: "var(--text-muted)" }}>
            Academic topics you explicitly target for future submissions.
          </p>

          {activeTopics.length > 0 ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "14px" }}>
              {activeTopics.map((top) => (
                <span
                  key={top.id}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "4px 10px",
                    background: "rgba(16, 185, 129, 0.1)",
                    border: "1px solid rgba(16, 185, 129, 0.3)",
                    borderRadius: "14px",
                    fontSize: "12px",
                    fontWeight: 500,
                    color: "#065f46",
                  }}
                >
                  <span>{top.display_label}</span>
                  <X
                    size={13}
                    style={{ cursor: "pointer" }}
                    onClick={() => onDeletePreference(top.id)}
                  />
                </span>
              ))}
            </div>
          ) : (
            <p style={{ fontSize: "12px", color: "var(--text-muted)", fontStyle: "italic", margin: "0 0 12px 0" }}>
              No explicit topic preferences yet.
            </p>
          )}

          {/* Add topic input */}
          <form onSubmit={handleAddTopic} style={{ display: "flex", gap: "6px" }}>
            <input
              type="text"
              value={newTopicInput}
              onChange={(e) => setNewTopicInput(e.target.value)}
              placeholder="e.g. Computer Vision"
              style={{
                flex: 1,
                padding: "6px 10px",
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius-sm)",
                fontSize: "12px",
                background: "var(--bg-card)",
                color: "var(--text-main)",
              }}
            />
            <button
              type="submit"
              disabled={isSubmitting || !newTopicInput.trim()}
              style={{
                padding: "6px 12px",
                background: "var(--primary)",
                color: "#fff",
                border: "none",
                borderRadius: "var(--radius-sm)",
                fontSize: "12px",
                fontWeight: 600,
                cursor: !newTopicInput.trim() ? "not-allowed" : "pointer",
                display: "flex",
                alignItems: "center",
                gap: "4px",
              }}
            >
              <Plus size={13} />
              <span>Add</span>
            </button>
          </form>
        </div>

        {/* Location Preferences */}
        <div
          style={{
            background: "var(--bg-hover)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-md)",
            padding: "20px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "14px" }}>
            <MapPin size={16} color="#f59e0b" />
            <h4 style={{ margin: 0, fontSize: "15px", fontWeight: 600, color: "var(--text-main)" }}>
              Locations & Regions
            </h4>
          </div>
          <p style={{ margin: "0 0 14px 0", fontSize: "12px", color: "var(--text-muted)" }}>
            Preferred host destinations for conferences and gatherings.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "14px" }}>
            {COMMON_REGIONS.map((reg) => {
              const active = activeLocationVals.has(reg);
              return (
                <button
                  key={reg}
                  onClick={() => handleToggleLocation(reg)}
                  disabled={isSubmitting}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "5px 10px",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "12px",
                    fontWeight: 500,
                    cursor: "pointer",
                    border: active ? "1px solid #f59e0b" : "1px solid var(--border-color)",
                    background: active ? "rgba(245, 158, 11, 0.15)" : "var(--bg-card)",
                    color: active ? "#b45309" : "var(--text-main)",
                    transition: "all 0.15s ease",
                  }}
                >
                  {active && <Check size={12} />}
                  <span>{reg}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Deadline Window */}
        <div
          style={{
            background: "var(--bg-hover)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-md)",
            padding: "20px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "14px" }}>
            <Clock size={16} color="#ec4899" />
            <h4 style={{ margin: 0, fontSize: "15px", fontWeight: 600, color: "var(--text-main)" }}>
              Deadline Preparation Window
            </h4>
          </div>
          <p style={{ margin: "0 0 14px 0", fontSize: "12px", color: "var(--text-muted)" }}>
            Minimum preparation time required before opportunity submission cut-off.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {DEADLINE_OPTIONS.map((opt) => {
              const active = activeDeadlineVal === opt.value;
              return (
                <button
                  key={opt.value}
                  onClick={() => handleSelectDeadline(opt.value, opt.label)}
                  disabled={isSubmitting}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "8px 12px",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "12px",
                    fontWeight: 500,
                    cursor: "pointer",
                    border: active ? "1px solid #ec4899" : "1px solid var(--border-color)",
                    background: active ? "rgba(236, 72, 153, 0.1)" : "var(--bg-card)",
                    color: active ? "#be185d" : "var(--text-main)",
                    textAlign: "left",
                  }}
                >
                  <span>{opt.label}</span>
                  {active && <CheckCircle2 size={14} color="#be185d" />}
                </button>
              );
            })}
          </div>
        </div>

        {/* Open Access & Publishing Policy */}
        <div
          style={{
            background: "var(--bg-hover)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-md)",
            padding: "20px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "14px" }}>
            <Unlock size={16} color="#6366f1" />
            <h4 style={{ margin: 0, fontSize: "15px", fontWeight: 600, color: "var(--text-main)" }}>
              Publishing & Access Policy
            </h4>
          </div>
          <p style={{ margin: "0 0 14px 0", fontSize: "12px", color: "var(--text-muted)" }}>
            Filter or prioritize publications supporting open-access archiving.
          </p>
          <button
            onClick={handleToggleOpenAccess}
            disabled={isSubmitting}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "12px 14px",
              borderRadius: "var(--radius-sm)",
              fontSize: "13px",
              fontWeight: 600,
              cursor: "pointer",
              border: isOpenAccessPreferred ? "1px solid #6366f1" : "1px solid var(--border-color)",
              background: isOpenAccessPreferred ? "rgba(99, 102, 241, 0.15)" : "var(--bg-card)",
              color: isOpenAccessPreferred ? "#4f46e5" : "var(--text-main)",
              textAlign: "left",
            }}
          >
            <span>Prefer Open Access Opportunities</span>
            {isOpenAccessPreferred ? (
              <CheckCircle2 size={16} color="#4f46e5" />
            ) : (
              <div
                style={{
                  width: "16px",
                  height: "16px",
                  borderRadius: "4px",
                  border: "1px solid var(--border-color)",
                }}
              />
            )}
          </button>
        </div>
      </div>

      {/* Inferred Preferences Section (From Saved Opportunities) */}
      <div
        style={{
          marginTop: "32px",
          padding: "24px",
          background: "var(--bg-hover)",
          border: "1px solid var(--border-color)",
          borderRadius: "var(--radius-md)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px", marginBottom: "12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <BookmarkCheck size={18} color="#0284c7" />
            <h4 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "var(--text-main)" }}>
              Inferred Preferences
            </h4>
            <span
              style={{
                fontSize: "11px",
                fontWeight: 600,
                padding: "2px 8px",
                background: "#e0f2fe",
                color: "#0369a1",
                borderRadius: "10px",
              }}
            >
              Inferred from Activity
            </span>
          </div>
          <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
            Strictly derived from your saved opportunities • No mock history
          </span>
        </div>

        {inferredPrefs.length > 0 ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "12px", marginTop: "16px" }}>
            {inferredPrefs.map((pref) => (
              <div
                key={pref.id}
                style={{
                  background: "var(--bg-card)",
                  border: "1px solid var(--border-color)",
                  borderRadius: "var(--radius-sm)",
                  padding: "14px",
                  boxShadow: "var(--shadow-sm)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "6px" }}>
                  <span style={{ fontSize: "13px", fontWeight: 700, color: "var(--text-main)" }}>
                    {pref.display_label}
                  </span>
                  <span
                    style={{
                      fontSize: "11px",
                      fontWeight: 600,
                      color: "#0284c7",
                      background: "#f0f9ff",
                      padding: "2px 6px",
                      borderRadius: "4px",
                    }}
                  >
                    Strength: {(pref.strength * 100).toFixed(0)}%
                  </span>
                </div>
                <div style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "8px" }}>
                  {pref.provenance_reasons.join(", ")}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "11px", color: "var(--text-muted)" }}>
                  <span>Confidence: {(pref.confidence * 100).toFixed(0)}%</span>
                  <span>Recency: {(pref.recency_score * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ padding: "20px", textAlign: "center", color: "var(--text-muted)", fontSize: "13px" }}>
            <p style={{ margin: "0 0 4px 0", fontWeight: 500 }}>No saved opportunity activity yet.</p>
            <p style={{ margin: 0, fontSize: "12px" }}>
              As you bookmark and save research opportunities, behavioral preference signals will appear here with deterministic evidence.
            </p>
          </div>
        )}
      </div>

      {/* Derived Candidates from Phase 3.2 Expertise */}
      {derivedCandidates.length > 0 && (
        <div
          style={{
            marginTop: "24px",
            padding: "24px",
            background: "linear-gradient(135deg, rgba(16, 185, 129, 0.03), rgba(5, 150, 105, 0.01))",
            border: "1px solid rgba(16, 185, 129, 0.2)",
            borderRadius: "var(--radius-md)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px", marginBottom: "12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <Sparkles size={18} color="#059669" />
              <h4 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "var(--text-main)" }}>
                Derived Candidates from Scholarly Expertise
              </h4>
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 600,
                  padding: "2px 8px",
                  background: "#d1fae5",
                  color: "#065f46",
                  borderRadius: "10px",
                }}
              >
                Expertise != Preference
              </span>
            </div>
            <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
              One-click adopt your academic research areas into personal preferences
            </span>
          </div>

          <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginTop: "14px" }}>
            {derivedCandidates.map((cand) => {
              const alreadyDeclared = activeTopics.some((t) => t.preference_value === cand.preference_value);
              return (
                <div
                  key={cand.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    padding: "6px 12px",
                    background: "var(--bg-card)",
                    border: "1px solid var(--border-color)",
                    borderRadius: "var(--radius-sm)",
                    boxShadow: "var(--shadow-sm)",
                    fontSize: "13px",
                  }}
                >
                  <span style={{ fontWeight: 600, color: "var(--text-main)" }}>{cand.display_label}</span>
                  <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                    ({(cand.strength * 100).toFixed(0)}% signal)
                  </span>
                  {alreadyDeclared ? (
                    <span style={{ display: "flex", alignItems: "center", gap: "3px", color: "#16a34a", fontSize: "11px", fontWeight: 600 }}>
                      <Check size={12} /> Adopted
                    </span>
                  ) : (
                    <button
                      onClick={() => handleAdoptCandidate(cand)}
                      disabled={isSubmitting}
                      style={{
                        padding: "3px 8px",
                        background: "rgba(16, 185, 129, 0.15)",
                        border: "1px solid rgba(16, 185, 129, 0.3)",
                        color: "#065f46",
                        borderRadius: "4px",
                        fontSize: "11px",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      + Add
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
