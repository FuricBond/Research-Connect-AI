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
          bg: "var(--rc-success-subtle)",
          color: "var(--rc-success)",
          border: "var(--rc-success-border)",
          label: "High Confidence",
        };
      case "Moderate":
        return {
          bg: "var(--rc-info-subtle)",
          color: "var(--rc-info)",
          border: "var(--rc-info-border)",
          label: "Moderate Confidence",
        };
      case "Low":
        return {
          bg: "var(--rc-warning-subtle)",
          color: "var(--rc-warning)",
          border: "var(--rc-warning-border)",
          label: "Low Confidence",
        };
      case "Cold Start":
      default:
        return {
          bg: "var(--rc-surface-sunken)",
          color: "var(--rc-text-secondary)",
          border: "var(--rc-border)",
          label: "Cold Start",
        };
    }
  };

  if (loading) {
    return (
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "var(--radius-lg, 12px)",
          padding: "32px",
          textAlign: "center",
          color: "var(--text-muted)",
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
          background: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "var(--radius-lg, 12px)",
          padding: "24px",
          color: "var(--rc-danger)",
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: "8px" }}>Could not load personalization state</div>
        <div style={{ fontSize: "13px", color: "var(--text-muted)", marginBottom: "16px" }}>
          {error || "Researcher summary data is currently unavailable."}
        </div>
        <button
          onClick={() => loadSummary(true)}
          style={{
            padding: "6px 14px",
            fontSize: "12px",
            fontWeight: 600,
            borderRadius: "6px",
            border: "1px solid var(--border-color)",
            background: "var(--bg-card)",
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
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "var(--radius-lg, 12px)",
        padding: "24px",
        boxShadow: "none",
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
            <Sparkles size={20} color="var(--primary)" />
            <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700, color: "var(--text-main)" }}>
              Your Research Personalization
            </h3>
          </div>
          <p style={{ margin: 0, fontSize: "13px", color: "var(--text-muted)" }}>
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
              border: "1px solid var(--border-color)",
              background: "var(--bg-main)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              color: "var(--text-main)",
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
            background: "var(--bg-main)",
            borderRadius: "8px",
            border: "1px solid var(--border-color)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--rc-text-muted)", fontSize: "12px", fontWeight: 600 }}>
            <Layers size={14} color="var(--rc-info)" /> Research Interests
          </div>
          <div style={{ fontSize: "24px", fontWeight: 800, marginTop: "6px", color: "var(--text-main)" }}>
            {summary.active_interests_count}
          </div>
          <div style={{ fontSize: "var(--rc-text-label-size)", color: "var(--text-muted)", marginTop: "2px" }}>
            Active topics tracked
          </div>
        </div>

        <div
          style={{
            padding: "16px",
            background: "var(--bg-main)",
            borderRadius: "8px",
            border: "1px solid var(--border-color)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--rc-text-muted)", fontSize: "12px", fontWeight: 600 }}>
            <Award size={14} color="var(--rc-success)" /> Strong Expertise
          </div>
          <div style={{ fontSize: "24px", fontWeight: 800, marginTop: "6px", color: "var(--text-main)" }}>
            {summary.strong_expertise_count}
          </div>
          <div style={{ fontSize: "var(--rc-text-label-size)", color: "var(--text-muted)", marginTop: "2px" }}>
            Verified domains
          </div>
        </div>

        <div
          style={{
            padding: "16px",
            background: "var(--bg-main)",
            borderRadius: "8px",
            border: "1px solid var(--border-color)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--rc-text-muted)", fontSize: "12px", fontWeight: 600 }}>
            <BookmarkCheck size={14} color="var(--rc-brand-text)" /> Explicit Preferences
          </div>
          <div style={{ fontSize: "24px", fontWeight: 800, marginTop: "6px", color: "var(--text-main)" }}>
            {summary.explicit_preferences_count}
          </div>
          <div style={{ fontSize: "var(--rc-text-label-size)", color: "var(--text-muted)", marginTop: "2px" }}>
            Configured rules
          </div>
        </div>

        <div
          style={{
            padding: "16px",
            background: "var(--bg-main)",
            borderRadius: "8px",
            border: "1px solid var(--border-color)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--rc-text-muted)", fontSize: "12px", fontWeight: 600 }}>
            <Activity size={14} color="var(--rc-warning)" /> Behavioral Signals
          </div>
          <div style={{ fontSize: "24px", fontWeight: 800, marginTop: "6px", color: "var(--text-main)" }}>
            {summary.behavioral_signals_count}
          </div>
          <div style={{ fontSize: "var(--rc-text-label-size)", color: "var(--text-muted)", marginTop: "2px" }}>
            Learned from {summary.total_feedback_count} actions
          </div>
        </div>
      </div>

      {/* ── Cold Start Callout Banner (If applicable) ── */}
      {summary.is_cold_start && (
        <div
          style={{
            padding: "18px 20px",
            background: "var(--rc-info-subtle)",
            border: "1px solid var(--rc-info-border)",
            borderRadius: "8px",
            display: "flex",
            alignItems: "flex-start",
            gap: "14px",
          }}
        >
          <Compass size={22} color="var(--rc-info)" style={{ flexShrink: 0, marginTop: "2px" }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: "14px", color: "var(--rc-info)", marginBottom: "4px" }}>
              Cold-Start Mode: Building Your Personalization Foundation
            </div>
            <div style={{ fontSize: "13px", color: "var(--rc-info)", lineHeight: "1.5", marginBottom: "12px" }}>
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
                    background: "var(--rc-brand)",
                    color: "var(--rc-text-on-brand)",
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
                    background: "var(--rc-surface)",
                    color: "var(--rc-info)",
                    border: "1px solid var(--rc-info-border)",
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
            background: "var(--rc-warning-subtle)",
            border: "1px solid var(--rc-warning-border)",
            borderRadius: "8px",
            display: "flex",
            alignItems: "center",
            gap: "12px",
            fontSize: "13px",
            color: "var(--rc-warning)",
          }}
        >
          <Clock size={18} color="var(--rc-warning)" style={{ flexShrink: 0 }} />
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
          gridTemplateColumns: "repeat(auto-fit, minmax(min(280px, 100%), 1fr))",
          gap: "16px",
        }}
      >
        {/* Explicit Drivers Panel */}
        <div
          style={{
            border: "1px solid var(--border-color)",
            borderRadius: "8px",
            padding: "16px",
            background: "var(--bg-main)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontWeight: 700, fontSize: "13px", color: "var(--text-main)" }}>
              <BookmarkCheck size={16} color="var(--rc-info)" />
              <span>Explicit Preferences</span>
            </div>
            <span style={{ fontSize: "var(--rc-text-label-size)", color: "var(--rc-text-muted)", background: "var(--rc-surface)", padding: "2px 8px", borderRadius: "10px", border: "1px solid var(--rc-border)" }}>
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
                    background: "var(--rc-surface)",
                    borderRadius: "6px",
                    border: "1px solid var(--rc-border)",
                    color: "var(--rc-text-secondary)",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  <CheckCircle2 size={13} color="var(--rc-success)" />
                  <span>{sig}</span>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: "12px", color: "var(--text-muted)", padding: "10px 0" }}>
              No explicit opportunity type, mode, or career stage preferences configured yet.
            </div>
          )}
          {onNavigateToPreferences && (
            <div style={{ marginTop: "12px" }}>
              <button
                onClick={onNavigateToPreferences}
                style={{
                  fontSize: "var(--rc-text-label-size)",
                  fontWeight: 600,
                  color: "var(--rc-info)",
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
            border: "1px solid var(--border-color)",
            borderRadius: "8px",
            padding: "16px",
            background: "var(--bg-main)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontWeight: 700, fontSize: "13px", color: "var(--text-main)" }}>
              <TrendingUp size={16} color="var(--rc-brand-text)" />
              <span>Learned from Activity</span>
            </div>
          </div>

          {summary.behavioral_signals_count > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {/* Learned Topics */}
              {summary.learned_topics.length > 0 && (
                <div>
                  <div style={{ fontSize: "var(--rc-text-label-size)", fontWeight: 700, color: "var(--rc-text-muted)", marginBottom: "4px" }}>
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
                  <div style={{ fontSize: "var(--rc-text-label-size)", fontWeight: 700, color: "var(--rc-text-muted)", marginBottom: "4px" }}>
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
                  <div style={{ fontSize: "var(--rc-text-label-size)", fontWeight: 700, color: "var(--rc-text-muted)", marginBottom: "4px" }}>
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
                  <div style={{ fontSize: "var(--rc-text-label-size)", fontWeight: 700, color: "var(--rc-danger)", marginBottom: "4px" }}>
                    Learned Demotions (From Dismissals)
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    {summary.top_negative_signals.map((neg, idx) => (
                      <div
                        key={idx}
                        style={{
                          fontSize: "var(--rc-text-label-size)",
                          color: "var(--rc-danger)",
                          background: "var(--rc-danger-subtle)",
                          padding: "4px 8px",
                          borderRadius: "4px",
                          display: "flex",
                          alignItems: "center",
                          gap: "4px",
                        }}
                      >
                        <TrendingDown size={12} color="var(--rc-danger)" />
                        <span>{neg}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ fontSize: "12px", color: "var(--text-muted)", padding: "10px 0" }}>
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
  const badgeBg = isPositive ? "var(--rc-success-subtle)" : "var(--rc-danger-subtle)";
  const badgeBorder = isPositive ? "var(--rc-success-border)" : "var(--rc-danger-border)";
  const badgeColor = isPositive ? "var(--rc-success)" : "var(--rc-danger)";

  return (
    <span
      style={{
        fontSize: "var(--rc-text-label-size)",
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
      <span style={{ fontSize: "var(--rc-text-label-size)" }}>({item.strength})</span>
    </span>
  );
}
