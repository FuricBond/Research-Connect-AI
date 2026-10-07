"use client";

import React, { useState } from "react";
import {
  Brain,
  ChevronDown,
  ChevronUp,
  Clock,
  Compass,
  ExternalLink,
  Flame,
  Info,
  Layers,
  Lightbulb,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import type {
  ExpertiseClassification,
  ResearcherIntelligenceResponse,
  ResearcherInterestItem,
} from "../../types/researcher";

interface ResearcherIntelligenceViewProps {
  intelligence: ResearcherIntelligenceResponse | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  isRefreshing: boolean;
}

export function ResearcherIntelligenceView({
  intelligence,
  loading,
  error,
  onRefresh,
  isRefreshing,
}: ResearcherIntelligenceViewProps) {
  const [activeTab, setActiveTab] = useState<"ALL" | "PRIMARY" | "EMERGING" | "SECONDARY">("ALL");
  const [expandedTopics, setExpandedTopics] = useState<Record<string, boolean>>({});

  const toggleExpand = (topicKey: string) => {
    setExpandedTopics((prev) => ({
      ...prev,
      [topicKey]: !prev[topicKey],
    }));
  };

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
            Analyzing scholarly corpus and extracting researcher intelligence...
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
          border: "1px solid var(--rc-danger-border)",
          borderRadius: "var(--radius-lg)",
          padding: "24px",
          marginTop: "24px",
          boxShadow: "var(--shadow-sm)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", color: "var(--rc-danger)" }}>
            <Info size={18} />
            <span style={{ fontSize: "14px", fontWeight: 600 }}>Failed to load research intelligence</span>
          </div>
          <button
            onClick={onRefresh}
            style={{
              padding: "6px 12px",
              background: "var(--rc-danger-subtle)",
              border: "1px solid var(--rc-danger-border)",
              color: "var(--rc-danger)",
              borderRadius: "var(--radius-sm)",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Retry
          </button>
        </div>
        <p style={{ fontSize: "13px", color: "var(--rc-danger)", margin: "8px 0 0 0" }}>{error}</p>
      </div>
    );
  }

  if (!intelligence || intelligence.interests.length === 0) {
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
        <Brain size={36} color="var(--text-muted)" style={{ margin: "0 auto 12px auto" }} />
        <h2 style={{ fontSize: "16px", fontWeight: 700, margin: "0 0 6px 0" }}>
          No Research Intelligence Inferred Yet
        </h2>
        <p style={{ fontSize: "13px", color: "var(--text-muted)", margin: "0 0 16px 0", maxWidth: "500px", marginLeft: "auto", marginRight: "auto" }}>
          Link an ORCID or OpenAlex author identifier in your Profile section to automatically aggregate topics, publication signals, and expertise from your authored works.
        </p>
      </div>
    );
  }

  // Filter interests by active tab
  const filteredInterests = intelligence.interests.filter((item) => {
    if (activeTab === "PRIMARY") return item.classification === "PRIMARY_EXPERTISE";
    if (activeTab === "EMERGING") return item.classification === "EMERGING_INTEREST";
    if (activeTab === "SECONDARY") return item.classification === "SECONDARY_EXPERTISE";
    return true;
  });

  const getBadgeStyle = (classification: ExpertiseClassification) => {
    switch (classification) {
      case "PRIMARY_EXPERTISE":
        return {
          bg: "var(--rc-brand-subtle)",
          border: "var(--rc-brand-border)",
          text: "var(--rc-brand-text)",
          label: "Primary Expertise",
          icon: <Brain size={12} />,
        };
      case "SECONDARY_EXPERTISE":
        return {
          bg: "var(--rc-info-subtle)",
          border: "var(--rc-info-border)",
          text: "var(--rc-info)",
          label: "Secondary Expertise",
          icon: <Layers size={12} />,
        };
      case "EMERGING_INTEREST":
        return {
          bg: "var(--rc-success-subtle)",
          border: "var(--rc-success-border)",
          text: "var(--rc-success)",
          label: "Emerging Interest",
          icon: <Flame size={12} />,
        };
      case "WEAK_INTEREST":
        return {
          bg: "var(--rc-bg)",
          border: "var(--rc-border)",
          text: "var(--rc-text-secondary)",
          label: "Declared / Incidental",
          icon: <Compass size={12} />,
        };
      case "INSUFFICIENT_EVIDENCE":
      default:
        return {
          bg: "var(--rc-warning-subtle)",
          border: "var(--rc-warning-border)",
          text: "var(--rc-warning)",
          label: "Sparse Evidence",
          icon: <Info size={12} />,
        };
    }
  };

  return (
    <div
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "var(--radius-lg)",
        padding: "24px",
        marginTop: "24px",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {/* Header with Strict Phase Demarcation */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          borderBottom: "1px solid var(--border-color)",
          paddingBottom: "16px",
          marginBottom: "20px",
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: "28px",
                height: "28px",
                borderRadius: "var(--radius-md)",
                background: "var(--rc-brand-subtle)",
                color: "var(--rc-brand-text)",
              }}
            >
              <Brain size={16} />
            </span>
            <h2 style={{ fontSize: "18px", fontWeight: 700, margin: 0 }}>
              Researcher Interest & Expertise Intelligence
            </h2>
          </div>
          <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: 0, lineHeight: "1.4" }}>
            Deterministic scholarly representation inferred from authored works, concepts, publication recency, and citation authority.
            <strong style={{ marginLeft: "4px", color: "var(--text-main)" }}>
              (Independent of personalized ranking or user preferences)
            </strong>
          </p>
        </div>

        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            padding: "6px 12px",
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--border-color)",
            background: "var(--bg-main)",
            color: "var(--text-main)",
            fontSize: "12px",
            fontWeight: 600,
            cursor: "pointer",
            transition: "all 0.15s ease",
          }}
        >
          <RefreshCw size={13} className={isRefreshing ? "animate-spin" : ""} />
          {isRefreshing ? "Recomputing..." : "Refresh Intelligence"}
        </button>
      </div>

      {/* Summary Metrics Bar */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "12px",
          marginBottom: "20px",
        }}
      >
        <div
          style={{
            background: "var(--bg-main)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-md)",
            padding: "12px",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: "20px", fontWeight: 700, color: "var(--primary)" }}>
            {intelligence.summary.total_topics_analyzed}
          </div>
          <div style={{ fontSize: "var(--rc-text-label-size)", color: "var(--text-muted)", fontWeight: 500, marginTop: "2px" }}>
            Total Topics Analyzed
          </div>
        </div>

        <div
          style={{
            background: "var(--rc-brand-subtle)",
            border: "1px solid var(--rc-brand-border)",
            borderRadius: "var(--radius-md)",
            padding: "12px",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: "20px", fontWeight: 700, color: "var(--rc-brand-text)" }}>
            {intelligence.summary.primary_expertise_count}
          </div>
          <div style={{ fontSize: "var(--rc-text-label-size)", color: "var(--rc-brand-text)", fontWeight: 500, marginTop: "2px" }}>
            Primary Expertise
          </div>
        </div>

        <div
          style={{
            background: "var(--rc-success-subtle)",
            border: "1px solid var(--rc-success-border)",
            borderRadius: "var(--radius-md)",
            padding: "12px",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: "20px", fontWeight: 700, color: "var(--rc-success)" }}>
            {intelligence.summary.emerging_interest_count}
          </div>
          <div style={{ fontSize: "var(--rc-text-label-size)", color: "var(--rc-success)", fontWeight: 500, marginTop: "2px" }}>
            Emerging Interests
          </div>
        </div>

        <div
          style={{
            background: "var(--bg-main)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-md)",
            padding: "12px",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: "20px", fontWeight: 700, color: "var(--text-main)" }}>
            {intelligence.summary.total_works_analyzed}
          </div>
          <div style={{ fontSize: "var(--rc-text-label-size)", color: "var(--text-muted)", fontWeight: 500, marginTop: "2px" }}>
            Analyzed Publications
          </div>
        </div>

        {intelligence.summary.active_years_span && (
          <div
            style={{
              background: "var(--bg-main)",
              border: "1px solid var(--border-color)",
              borderRadius: "var(--radius-md)",
              padding: "12px",
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: "16px", fontWeight: 700, color: "var(--text-main)", marginTop: "2px" }}>
              {intelligence.summary.active_years_span}
            </div>
            <div style={{ fontSize: "var(--rc-text-label-size)", color: "var(--text-muted)", fontWeight: 500, marginTop: "4px" }}>
              Active Scholarly Span
            </div>
          </div>
        )}
      </div>

      {/* Filter Tabs */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "8px",
          marginBottom: "16px",
          borderBottom: "1px solid var(--border-color)",
          paddingBottom: "8px",
        }}
      >
        <button
          onClick={() => setActiveTab("ALL")}
          style={{
            padding: "6px 14px",
            borderRadius: "var(--radius-full)",
            border: "none",
            background: activeTab === "ALL" ? "var(--primary)" : "transparent",
            color: activeTab === "ALL" ? "var(--rc-text-on-brand)" : "var(--text-muted)",
            fontSize: "12px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          All Topics ({intelligence.interests.length})
        </button>

        <button
          onClick={() => setActiveTab("PRIMARY")}
          style={{
            padding: "6px 14px",
            borderRadius: "var(--radius-full)",
            border: "none",
            background: activeTab === "PRIMARY" ? "var(--rc-brand)" : "transparent",
            color: activeTab === "PRIMARY" ? "var(--rc-text-on-brand)" : "var(--text-muted)",
            fontSize: "12px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Primary Expertise ({intelligence.summary.primary_expertise_count})
        </button>

        <button
          onClick={() => setActiveTab("EMERGING")}
          style={{
            padding: "6px 14px",
            borderRadius: "var(--radius-full)",
            border: "none",
            background: activeTab === "EMERGING" ? "var(--rc-brand)" : "transparent",
            color: activeTab === "EMERGING" ? "var(--rc-text-on-brand)" : "var(--text-muted)",
            fontSize: "12px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Emerging Interests ({intelligence.summary.emerging_interest_count})
        </button>

        <button
          onClick={() => setActiveTab("SECONDARY")}
          style={{
            padding: "6px 14px",
            borderRadius: "var(--radius-full)",
            border: "none",
            background: activeTab === "SECONDARY" ? "var(--rc-brand)" : "transparent",
            color: activeTab === "SECONDARY" ? "var(--rc-text-on-brand)" : "var(--text-muted)",
            fontSize: "12px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Secondary ({intelligence.summary.secondary_expertise_count})
        </button>
      </div>

      {/* Structured Topic Intelligence Cards */}
      <div style={{ display: "grid", gap: "12px" }}>
        {filteredInterests.map((item, idx) => {
          const badge = getBadgeStyle(item.classification);
          const isExpanded = !!expandedTopics[item.topic_slug];

          return (
            <div
              key={`${item.topic_slug}-${idx}`}
              style={{
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius-md)",
                background: "var(--bg-main)",
                overflow: "hidden",
                transition: "border-color 0.15s ease",
              }}
            >
              {/* Card Summary Row */}
              <div
                style={{
                  padding: "14px 16px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: "12px",
                }}
              >
                {/* Topic Title & Tier Badge */}
                <div style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: "220px" }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontSize: "14px", fontWeight: 700, color: "var(--text-main)" }}>
                        {item.topic_name}
                      </span>
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "4px",
                          fontSize: "var(--rc-text-label-size)",
                          fontWeight: 600,
                          padding: "2px 8px",
                          borderRadius: "var(--radius-full)",
                          background: badge.bg,
                          border: `1px solid ${badge.border}`,
                          color: badge.text,
                        }}
                      >
                        {badge.icon}
                        {badge.label}
                      </span>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "12px", marginTop: "4px", fontSize: "var(--rc-text-label-size)", color: "var(--text-muted)" }}>
                      <span>
                        <strong>{item.evidence_count}</strong> {item.evidence_count === 1 ? "work" : "works"}
                      </span>
                      {item.last_observed_year && (
                        <span>
                          {item.first_observed_year && item.first_observed_year !== item.last_observed_year
                            ? `${item.first_observed_year}–${item.last_observed_year}`
                            : `Activity: ${item.last_observed_year}`}
                        </span>
                      )}
                      <span>Source: {item.source}</span>
                    </div>
                  </div>
                </div>

                {/* Quantitative Metric Gauges */}
                <div style={{ display: "flex", alignItems: "center", gap: "20px", flexWrap: "wrap" }}>
                  {/* Strength Bar */}
                  <div style={{ minWidth: "120px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "var(--rc-text-label-size)", marginBottom: "3px" }}>
                      <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>Strength</span>
                      <strong style={{ color: "var(--text-main)" }}>{(item.strength * 100).toFixed(1)}%</strong>
                    </div>
                    <div style={{ height: "6px", background: "var(--border-color)", borderRadius: "3px", overflow: "hidden" }}>
                      <div
                        style={{
                          height: "100%",
                          width: `${Math.round(item.strength * 100)}%`,
                          background: "var(--rc-data-meter-fill)",
                          borderRadius: "3px",
                        }}
                      />
                    </div>
                  </div>

                  {/* Confidence Badge */}
                  <div style={{ minWidth: "100px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "var(--rc-text-label-size)", marginBottom: "3px" }}>
                      <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>Confidence</span>
                      <strong style={{ color: "var(--text-main)" }}>{(item.confidence * 100).toFixed(0)}%</strong>
                    </div>
                    <div style={{ height: "6px", background: "var(--border-color)", borderRadius: "3px", overflow: "hidden" }}>
                      <div
                        style={{
                          height: "100%",
                          width: `${Math.round(item.confidence * 100)}%`,
                          background: "var(--rc-success)",
                          borderRadius: "3px",
                        }}
                      />
                    </div>
                  </div>

                  {/* Recency Score Pill */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                      fontSize: "var(--rc-text-label-size)",
                      padding: "4px 8px",
                      borderRadius: "var(--radius-sm)",
                      background: item.recency_score >= 0.75 ? "var(--rc-success-subtle)" : "var(--rc-surface-sunken)",
                      color: item.recency_score >= 0.75 ? "var(--rc-success)" : "var(--rc-text-secondary)",
                      fontWeight: 600,
                    }}
                  >
                    <Clock size={11} />
                    <span>Recency: {(item.recency_score * 100).toFixed(0)}%</span>
                  </div>

                  {/* Provenance Accordion Toggle */}
                  <button
                    onClick={() => toggleExpand(item.topic_slug)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                      background: "transparent",
                      border: "none",
                      color: "var(--primary)",
                      fontSize: "12px",
                      fontWeight: 600,
                      cursor: "pointer",
                      padding: "4px 8px",
                    }}
                  >
                    <span>{isExpanded ? "Hide Evidence" : "Why this area?"}</span>
                    {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </button>
                </div>
              </div>

              {/* Expandable Provenance & Supporting Works Drawer */}
              {isExpanded && (
                <div
                  style={{
                    borderTop: "1px solid var(--border-color)",
                    background: "var(--bg-card)",
                    padding: "16px 20px",
                  }}
                >
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
                    {/* Left: Deterministic Provenance Reasons */}
                    <div>
                      <h4 style={{ fontSize: "12px", fontWeight: 700, margin: "0 0 8px 0", color: "var(--text-muted)", letterSpacing: "0.5px" }}>
                        Scholarly Provenance & Evidence
                      </h4>
                      <ul style={{ margin: 0, paddingLeft: "16px", display: "grid", gap: "6px" }}>
                        {item.provenance_reasons.map((reason, rIdx) => (
                          <li key={rIdx} style={{ fontSize: "12px", color: "var(--text-main)", lineHeight: "1.4" }}>
                            {reason}
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* Right: Supporting Publications */}
                    <div>
                      <h4 style={{ fontSize: "12px", fontWeight: 700, margin: "0 0 8px 0", color: "var(--text-muted)", letterSpacing: "0.5px" }}>
                        Supporting Authored Works ({item.supporting_works.length})
                      </h4>
                      {item.supporting_works.length === 0 ? (
                        <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: 0 }}>
                          Declared in profile keywords without direct indexed works.
                        </p>
                      ) : (
                        <div style={{ display: "grid", gap: "8px", maxHeight: "180px", overflowY: "auto" }}>
                          {item.supporting_works.slice(0, 5).map((work) => (
                            <div
                              key={work.id}
                              style={{
                                padding: "8px 10px",
                                background: "var(--bg-main)",
                                border: "1px solid var(--border-color)",
                                borderRadius: "var(--radius-sm)",
                                fontSize: "12px",
                              }}
                            >
                              <div style={{ fontWeight: 600, color: "var(--text-main)", marginBottom: "2px" }}>
                                {work.title}
                              </div>
                              <div style={{ display: "flex", gap: "10px", fontSize: "var(--rc-text-label-size)", color: "var(--text-muted)" }}>
                                {work.publication_year && <span>{work.publication_year}</span>}
                                {work.cited_by_count > 0 && <span>{work.cited_by_count} citations</span>}
                                {work.author_position && <span>Role: {work.author_position}</span>}
                                {work.doi && (
                                  <a
                                    href={`https://doi.org/${work.doi}`}
                                    target="_blank"
                                    rel="noreferrer"
                                    style={{ color: "var(--primary)", display: "inline-flex", alignItems: "center", gap: "2px" }}
                                  >
                                    DOI <ExternalLink size={10} />
                                  </a>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
