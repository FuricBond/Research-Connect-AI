"use client";

import React, { useState, useEffect, useCallback } from "react";
import { fetchPersonalizationSummary } from "../../services/api";
import type { LearnedSignalItem, PersonalizationSummaryResponse } from "../../types/researcher";
import {
  Activity,
  ArrowRight,
  Award,
  BookmarkCheck,
  CheckCircle2,
  Clock,
  Compass,
  Info,
  Layers,
  RefreshCw,
  Sliders,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Zap,
} from "lucide-react";

interface PersonalizationSummaryViewProps {
  profileId: string;
  userId?: string;
  onNavigateToPreferences?: () => void;
  onNavigateToInterests?: () => void;
  onNavigateToFeed?: () => void;
  refreshTrigger?: number;
}

export function PersonalizationSummaryView({
  profileId,
  userId,
  onNavigateToPreferences,
  onNavigateToInterests,
  onNavigateToFeed,
  refreshTrigger = 0,
}: PersonalizationSummaryViewProps) {
  const [loading, setLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<PersonalizationSummaryResponse | null>(null);

  const loadSummary = useCallback(
    async (isManualRefresh = false) => {
      if (!profileId) return;
      if (isManualRefresh) setIsRefreshing(true);
      else setLoading(true);
      setError(null);

      try {
        const data = await fetchPersonalizationSummary(profileId, userId);
        setSummary(data);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed to load personalization summary.";
        setError(msg);
      } finally {
        setLoading(false);
        setIsRefreshing(false);
      }
    },
    [profileId, userId]
  );

  useEffect(() => {
    loadSummary();
  }, [loadSummary, refreshTrigger]);

  const getConfidenceBadge = (confidence: string) => {
    switch (confidence) {
      case "High":
        return {
          bg: "#ecfdf5",
          color: "#047857",
          border: "#a7f3d0",
          label: "High Confidence",
        };
      case "Moderate":
        return {
          bg: "#eff6ff",
          color: "#1d4ed8",
          border: "#bfdbfe",
          label: "Moderate Confidence",
        };
      case "Low":
        return {
          bg: "#fffbeb",
          color: "#b45309",
          border: "#fde68a",
          label: "Low Confidence",
        };
      case "Cold Start":
      default:
        return {
          bg: "#f3f4f6",
          color: "#4b5563",
          border: "#e5e7eb",
          label: "Cold Start",
        };
    }
  };

  if (loading) {
    return (
      <div
        style={{
          background: "var(--bg-card, #ffffff)",
          border: "1px solid var(--border-color, #e2e8f0)",
          borderRadius: "var(--radius-lg, 12px)",
          padding: "32px",
          textAlign: "center",
          color: "var(--text-muted, #64748b)",
        }}
      >
        <div style={{ display: "inline-block", animation: "spin 1s linear infinite", marginBottom: "8px" }}>
          <RefreshCw size={24} />
        </div>
        <div>Loading personalization intelligence...</div>
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div
        style={{
          background: "var(--bg-card, #ffffff)",
          border: "1px solid var(--border-color, #e2e8f0)",
          borderRadius: "var(--radius-lg, 12px)",
          padding: "24px",
          color: "#b91c1c",
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: "8px" }}>Could not load personalization state</div>
        <div style={{ fontSize: "13px", color: "var(--text-muted, #64748b)", marginBottom: "16px" }}>
          {error || "Researcher summary data is currently unavailable."}
        </div>
        <button
          onClick={() => loadSummary(true)}
          style={{
            padding: "6px 14px",
            fontSize: "12px",
            fontWeight: 600,
            borderRadius: "6px",
            border: "1px solid var(--border-color, #cbd5e1)",
            background: "var(--bg-card, #ffffff)",
            cursor: "pointer",
          }}
        >
          Try Again
        </button>
      </div>
    );
  }

  const confBadge = getConfidenceBadge(summary.personalization_confidence);

  return (
    <div
      style={{
        background: "var(--bg-card, #ffffff)",
        border: "1px solid var(--border-color, #e2e8f0)",
        borderRadius: "var(--radius-lg, 12px)",
        padding: "24px",
        boxShadow: "0 1px 3px rgba(0, 0, 0, 0.05)",
        display: "flex",
        flexDirection: "column",
        gap: "24px",
      }}
    >
      {/* ── Header ── */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
            <Sparkles size={20} color="var(--primary, #2563eb)" />
            <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700, color: "var(--text-main, #0f172a)" }}>
              Your Research Personalization
            </h3>
          </div>
          <p style={{ margin: 0, fontSize: "13px", color: "var(--text-muted, #64748b)" }}>
            Real-time breakdown of declared preferences, verified research expertise, and learned behavioral signals.
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span
            style={{
              fontSize: "12px",
              fontWeight: 700,
              padding: "4px 10px",
              borderRadius: "20px",
              background: confBadge.bg,
              color: confBadge.color,
              border: `1px solid ${confBadge.border}`,
              display: "flex",
              alignItems: "center",
              gap: "5px",
            }}
          >
            <Zap size={13} />
            {confBadge.label} ({(summary.confidence_score * 100).toFixed(0)}%)
          </span>
          <button
            onClick={() => loadSummary(true)}
            disabled={isRefreshing}
            aria-label="Refresh personalization summary"
            style={{
              padding: "6px 12px",
              fontSize: "12px",
              fontWeight: 600,
              borderRadius: "6px",
              border: "1px solid var(--border-color, #cbd5e1)",
              background: "var(--bg-main, #f8fafc)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              color: "var(--text-main, #334155)",
            }}
          >
            <RefreshCw size={13} className={isRefreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* ── KPI Grid ── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "12px",
        }}
      >
        <div
          style={{
            padding: "16px",
            background: "var(--bg-main, #f8fafc)",
            borderRadius: "8px",
            border: "1px solid var(--border-color, #e2e8f0)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#64748b", fontSize: "12px", fontWeight: 600 }}>
            <Layers size={14} color="#3b82f6" /> Research Interests
          </div>
          <div style={{ fontSize: "24px", fontWeight: 800, marginTop: "6px", color: "var(--text-main, #0f172a)" }}>
            {summary.active_interests_count}
          </div>
          <div style={{ fontSize: "11px", color: "var(--text-muted, #64748b)", marginTop: "2px" }}>
            Active topics tracked
          </div>
        </div>

        <div
          style={{
            padding: "16px",
            background: "var(--bg-main, #f8fafc)",
            borderRadius: "8px",
            border: "1px solid var(--border-color, #e2e8f0)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#64748b", fontSize: "12px", fontWeight: 600 }}>
            <Award size={14} color="#10b981" /> Strong Expertise
          </div>
          <div style={{ fontSize: "24px", fontWeight: 800, marginTop: "6px", color: "var(--text-main, #0f172a)" }}>
            {summary.strong_expertise_count}
          </div>
          <div style={{ fontSize: "11px", color: "var(--text-muted, #64748b)", marginTop: "2px" }}>
            Verified domains
          </div>
        </div>

        <div
          style={{
            padding: "16px",
            background: "var(--bg-main, #f8fafc)",
            borderRadius: "8px",
            border: "1px solid var(--border-color, #e2e8f0)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#64748b", fontSize: "12px", fontWeight: 600 }}>
            <BookmarkCheck size={14} color="#8b5cf6" /> Explicit Preferences
          </div>
          <div style={{ fontSize: "24px", fontWeight: 800, marginTop: "6px", color: "var(--text-main, #0f172a)" }}>
            {summary.explicit_preferences_count}
          </div>
          <div style={{ fontSize: "11px", color: "var(--text-muted, #64748b)", marginTop: "2px" }}>
            Configured rules
          </div>
        </div>

        <div
          style={{
            padding: "16px",
            background: "var(--bg-main, #f8fafc)",
            borderRadius: "8px",
            border: "1px solid var(--border-color, #e2e8f0)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#64748b", fontSize: "12px", fontWeight: 600 }}>
            <Activity size={14} color="#f59e0b" /> Behavioral Signals
          </div>
          <div style={{ fontSize: "24px", fontWeight: 800, marginTop: "6px", color: "var(--text-main, #0f172a)" }}>
            {summary.behavioral_signals_count}
          </div>
          <div style={{ fontSize: "11px", color: "var(--text-muted, #64748b)", marginTop: "2px" }}>
            Learned from {summary.total_feedback_count} actions
          </div>
        </div>
      </div>

      {/* ── Cold Start Callout Banner (If applicable) ── */}
      {summary.is_cold_start && (
        <div
          style={{
            padding: "18px 20px",
            background: "#eff6ff",
            border: "1px solid #bfdbfe",
            borderRadius: "8px",
            display: "flex",
            alignItems: "flex-start",
            gap: "14px",
          }}
        >
          <Compass size={22} color="#2563eb" style={{ flexShrink: 0, marginTop: "2px" }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: "14px", color: "#1e3a8a", marginBottom: "4px" }}>
              Cold-Start Mode: Building Your Personalization Foundation
            </div>
            <div style={{ fontSize: "13px", color: "#1e40af", lineHeight: "1.5", marginBottom: "12px" }}>
              Your recommendations are currently based mainly on research relevance. We have not yet recorded enough
              interests or explicit preferences to customize candidate ranking.
            </div>
            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
              {onNavigateToInterests && (
                <button
                  onClick={onNavigateToInterests}
                  style={{
                    padding: "6px 14px",
                    fontSize: "12px",
                    fontWeight: 600,
                    borderRadius: "6px",
                    background: "#2563eb",
                    color: "#ffffff",
                    border: "none",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  Add Research Interests <ArrowRight size={13} />
                </button>
              )}
              {onNavigateToPreferences && (
                <button
                  onClick={onNavigateToPreferences}
                  style={{
                    padding: "6px 14px",
                    fontSize: "12px",
                    fontWeight: 600,
                    borderRadius: "6px",
                    background: "#ffffff",
                    color: "#2563eb",
                    border: "1px solid #bfdbfe",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  Set Preferences <Sliders size={13} />
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── No Feedback Guidance (If has interests/prefs but no feedback) ── */}
      {!summary.is_cold_start && !summary.has_feedback && (
        <div
          style={{
            padding: "14px 18px",
            background: "#fefce8",
            border: "1px solid #fef08a",
            borderRadius: "8px",
            display: "flex",
            alignItems: "center",
            gap: "12px",
            fontSize: "13px",
            color: "#854d0e",
          }}
        >
          <Clock size={18} color="#a16207" style={{ flexShrink: 0 }} />
          <div>
            <strong>We&apos;re still learning your preferences:</strong> Save or dismiss opportunities in your
            recommendation feed to help our deterministic ranker tune future proposals to your preferences.
          </div>
        </div>
      )}

      {/* ── Explicit vs Learned Comparison & Breakdown ── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: "16px",
        }}
      >
        {/* Explicit Drivers Panel */}
        <div
          style={{
            border: "1px solid var(--border-color, #e2e8f0)",
            borderRadius: "8px",
            padding: "16px",
            background: "var(--bg-main, #f8fafc)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontWeight: 700, fontSize: "13px", color: "var(--text-main, #0f172a)" }}>
              <BookmarkCheck size={16} color="#2563eb" />
              <span>Explicit Preferences</span>
            </div>
            <span style={{ fontSize: "11px", color: "#64748b", background: "#ffffff", padding: "2px 8px", borderRadius: "10px", border: "1px solid #e2e8f0" }}>
              Researcher Managed
            </span>
          </div>
          {summary.top_positive_signals.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {summary.top_positive_signals.map((sig, idx) => (
                <div
                  key={idx}
                  style={{
                    fontSize: "12px",
                    padding: "6px 10px",
                    background: "#ffffff",
                    borderRadius: "6px",
                    border: "1px solid #e2e8f0",
                    color: "#334155",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  <CheckCircle2 size={13} color="#16a34a" />
                  <span>{sig}</span>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: "12px", color: "var(--text-muted, #64748b)", padding: "10px 0" }}>
              No explicit opportunity type, mode, or career stage preferences configured yet.
            </div>
          )}
          {onNavigateToPreferences && (
            <div style={{ marginTop: "12px" }}>
              <button
                onClick={onNavigateToPreferences}
                style={{
                  fontSize: "11px",
                  fontWeight: 600,
                  color: "#2563eb",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  padding: 0,
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                }}
              >
                Configure explicit preferences <ArrowRight size={11} />
              </button>
            </div>
          )}
        </div>

        {/* Learned from Activity Panel */}
        <div
          style={{
            border: "1px solid var(--border-color, #e2e8f0)",
            borderRadius: "8px",
            padding: "16px",
            background: "var(--bg-main, #f8fafc)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontWeight: 700, fontSize: "13px", color: "var(--text-main, #0f172a)" }}>
              <TrendingUp size={16} color="#8b5cf6" />
              <span>Learned from Activity</span>
            </div>
            <span style={{ fontSize: "11px", color: "#64748b", background: "#ffffff", padding: "2px 8px", borderRadius: "10px", border: "1px solid #e2e8f0" }}>
              Phase 3.6 Behavioral
            </span>
          </div>

          {summary.behavioral_signals_count > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {/* Learned Topics */}
              {summary.learned_topics.length > 0 && (
                <div>
                  <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748b", textTransform: "uppercase", marginBottom: "4px" }}>
                    Topics & Themes
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                    {summary.learned_topics.map((item, idx) => (
                      <SignalBadge key={idx} item={item} />
                    ))}
                  </div>
                </div>
              )}

              {/* Learned Opportunity Types */}
              {summary.learned_opportunity_types.length > 0 && (
                <div>
                  <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748b", textTransform: "uppercase", marginBottom: "4px" }}>
                    Opportunity Formats
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                    {summary.learned_opportunity_types.map((item, idx) => (
                      <SignalBadge key={idx} item={item} />
                    ))}
                  </div>
                </div>
              )}

              {/* Learned Delivery Modes */}
              {summary.learned_delivery_modes.length > 0 && (
                <div>
                  <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748b", textTransform: "uppercase", marginBottom: "4px" }}>
                    Delivery Modes
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                    {summary.learned_delivery_modes.map((item, idx) => (
                      <SignalBadge key={idx} item={item} />
                    ))}
                  </div>
                </div>
              )}

              {/* Suppressed / Demotion signals */}
              {summary.top_negative_signals.length > 0 && (
                <div>
                  <div style={{ fontSize: "11px", fontWeight: 700, color: "#b91c1c", textTransform: "uppercase", marginBottom: "4px" }}>
                    Learned Demotions (From Dismissals)
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    {summary.top_negative_signals.map((neg, idx) => (
                      <div
                        key={idx}
                        style={{
                          fontSize: "11px",
                          color: "#991b1b",
                          background: "#fef2f2",
                          padding: "4px 8px",
                          borderRadius: "4px",
                          display: "flex",
                          alignItems: "center",
                          gap: "4px",
                        }}
                      >
                        <TrendingDown size={12} color="#dc2626" />
                        <span>{neg}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ fontSize: "12px", color: "var(--text-muted, #64748b)", padding: "10px 0" }}>
              No behavioral preferences learned yet. As you save, view, or dismiss opportunities, patterns will emerge
              here.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SignalBadge({ item }: { item: LearnedSignalItem }) {
  const isPositive = item.direction === "POSITIVE";
  const badgeBg = isPositive ? "#f0fdf4" : "#fef2f2";
  const badgeBorder = isPositive ? "#bbf7d0" : "#fecaca";
  const badgeColor = isPositive ? "#166534" : "#991b1b";

  return (
    <span
      style={{
        fontSize: "11px",
        fontWeight: 600,
        padding: "3px 8px",
        borderRadius: "6px",
        background: badgeBg,
        border: `1px solid ${badgeBorder}`,
        color: badgeColor,
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
      }}
      title={`Confidence: ${(item.confidence * 100).toFixed(0)}%, Events: ${item.supporting_event_count}`}
    >
      {isPositive ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
      <span>{item.display_label}</span>
      <span style={{ fontSize: "10px", opacity: 0.8 }}>({item.strength})</span>
    </span>
  );
}
