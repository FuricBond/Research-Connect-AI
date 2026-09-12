"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  fetchRecommendationEvaluation,
  fetchRecommendationHistory,
  fetchRecommendationSnapshotDetail,
} from "../../services/api";
import type {
  EvaluationMetrics,
  RecommendationEvaluationResponse,
  RecommendationHistoryResponse,
  RecommendationItemSnapshot,
  RecommendationSnapshotDetail,
  RecommendationSnapshotSummary,
} from "../../types/researcher";
import {
  Activity,
  AlertCircle,
  Award,
  BarChart3,
  Calendar,
  CheckCircle2,
  ChevronRight,
  Clock,
  ExternalLink,
  Eye,
  FileText,
  History,
  Info,
  Layers,
  Percent,
  RefreshCw,
  Scale,
  Shield,
  Sparkles,
  TrendingUp,
  X,
} from "lucide-react";

interface RecommendationHistoryViewProps {
  profileId: string;
  userId?: string;
  refreshTrigger?: number;
}

export function RecommendationHistoryView({
  profileId,
  userId,
  refreshTrigger = 0,
}: RecommendationHistoryViewProps) {
  const [loading, setLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [evaluation, setEvaluation] = useState<RecommendationEvaluationResponse | null>(null);
  const [history, setHistory] = useState<RecommendationSnapshotSummary[]>([]);
  const [totalHistory, setTotalHistory] = useState<number>(0);
  const [versionFilter, setVersionFilter] = useState<string>("");

  // Inspect Snapshot Modal state
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string | null>(null);
  const [snapshotDetail, setSnapshotDetail] = useState<RecommendationSnapshotDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);

  const loadData = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) setIsRefreshing(true);
      else setLoading(true);
      setError(null);

      try {
        const [evalRes, histRes] = await Promise.all([
          fetchRecommendationEvaluation(
            profileId,
            { rankingVersion: versionFilter || undefined, includeComparison: true },
            userId
          ),
          fetchRecommendationHistory(
            profileId,
            { limit: 20, offset: 0, rankingVersion: versionFilter || undefined },
            userId
          ),
        ]);

        setEvaluation(evalRes);
        setHistory(histRes.items);
        setTotalHistory(histRes.total);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed to load recommendation history.";
        setError(msg);
      } finally {
        setLoading(false);
        setIsRefreshing(false);
      }
    },
    [profileId, userId, versionFilter]
  );

  useEffect(() => {
    loadData();
  }, [loadData, refreshTrigger]);

  const handleInspectSnapshot = async (snapshotId: string) => {
    setSelectedSnapshotId(snapshotId);
    setDetailLoading(true);
    try {
      const detail = await fetchRecommendationSnapshotDetail(profileId, snapshotId, userId);
      setSnapshotDetail(detail);
    } catch (err: unknown) {
      console.error("Failed to load snapshot detail", err);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeSnapshotModal = () => {
    setSelectedSnapshotId(null);
    setSnapshotDetail(null);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "SUFFICIENT_DATA":
        return {
          bg: "#ecfdf5",
          color: "#059669",
          border: "#a7f3d0",
          label: "Sufficient Data",
          icon: <CheckCircle2 size={13} />,
        };
      case "INSUFFICIENT_DATA":
        return {
          bg: "#fffbeb",
          color: "#d97706",
          border: "#fde68a",
          label: "Insufficient Data",
          icon: <Info size={13} />,
        };
      case "NO_FEEDBACK":
        return {
          bg: "#fef3c7",
          color: "#b45309",
          border: "#fcd34d",
          label: "No Feedback Recorded",
          icon: <Clock size={13} />,
        };
      case "NO_HISTORY":
      default:
        return {
          bg: "#f3f4f6",
          color: "#6b7280",
          border: "#e5e7eb",
          label: "No History",
          icon: <History size={13} />,
        };
    }
  };

  const formatMetric = (val?: number | null, isPercent = false): string => {
    if (val === undefined || val === null) return "—";
    if (isPercent) return `${(val * 100).toFixed(1)}%`;
    return val.toFixed(3);
  };

  return (
    <div
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "var(--radius-lg)",
        padding: "24px",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {/* ── Section Header ── */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexWrap: "wrap",
          gap: "12px",
          marginBottom: "20px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <History size={20} color="var(--primary)" />
            <h3 style={{ margin: 0, fontSize: "17px", fontWeight: 700 }}>
              Recommendation History & Evaluation
            </h3>
            <span
              style={{
                fontSize: "11px",
                fontWeight: 600,
                background: "var(--primary-subtle)",
                color: "var(--primary)",
                padding: "2px 8px",
                borderRadius: "10px",
              }}
            >
              Phase 3.7
            </span>
          </div>
          <p
            style={{
              margin: "4px 0 0 0",
              fontSize: "13px",
              color: "var(--text-muted)",
              lineHeight: "1.4",
            }}
          >
            Point-in-time recommendation snapshots, ranking algorithm versioning, and offline Information Retrieval metrics.
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <select
            value={versionFilter}
            onChange={(e) => setVersionFilter(e.target.value)}
            style={{
              fontSize: "12px",
              padding: "6px 10px",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border-color)",
              background: "var(--bg-main)",
              color: "var(--text-main)",
            }}
          >
            <option value="">All Ranking Versions</option>
            <option value="phase3.7-v1">Phase 3.7 (Behavioral Personalization)</option>
            <option value="phase3.5-personalized">Phase 3.5 (Personalized Ranking)</option>
            <option value="phase2-baseline">Phase 2 (Baseline Relevance)</option>
          </select>

          <button
            onClick={() => loadData(true)}
            disabled={loading || isRefreshing}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "12px",
              fontWeight: 600,
              padding: "6px 12px",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border-color)",
              background: "var(--bg-card)",
              color: "var(--text-main)",
              cursor: "pointer",
            }}
          >
            <RefreshCw size={13} className={isRefreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: "12px 16px",
            borderRadius: "var(--radius-sm)",
            background: "#fee2e2",
            color: "#991b1b",
            fontSize: "13px",
            marginBottom: "16px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* ── Evaluation Metrics Dashboard ── */}
      {evaluation && (
        <div style={{ marginBottom: "28px" }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "8px",
              marginBottom: "12px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <BarChart3 size={16} color="var(--primary)" />
              <span style={{ fontSize: "14px", fontWeight: 700 }}>
                Offline Recommendation Quality
              </span>
            </div>

            {/* Evidence Level Badge */}
            {(() => {
              const b = getStatusBadge(evaluation.data_status);
              return (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "5px",
                    padding: "3px 10px",
                    borderRadius: "12px",
                    background: b.bg,
                    color: b.color,
                    border: `1px solid ${b.border}`,
                    fontSize: "12px",
                    fontWeight: 600,
                  }}
                >
                  {b.icon}
                  <span>{b.label}</span>
                </div>
              );
            })()}
          </div>

          {/* Metric Cards Grid */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
              gap: "10px",
            }}
          >
            <div
              style={{
                background: "var(--bg-main)",
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius-sm)",
                padding: "12px",
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>
                Precision@5
              </div>
              <div style={{ fontSize: "18px", fontWeight: 700, marginTop: "4px", color: "var(--primary)" }}>
                {formatMetric(evaluation.metrics.precision_at_5, true)}
              </div>
              <div style={{ fontSize: "10px", color: "var(--text-muted)", marginTop: "2px" }}>Top 5 relevance</div>
            </div>

            <div
              style={{
                background: "var(--bg-main)",
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius-sm)",
                padding: "12px",
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>
                Precision@10
              </div>
              <div style={{ fontSize: "18px", fontWeight: 700, marginTop: "4px", color: "var(--primary)" }}>
                {formatMetric(evaluation.metrics.precision_at_10, true)}
              </div>
              <div style={{ fontSize: "10px", color: "var(--text-muted)", marginTop: "2px" }}>Top 10 relevance</div>
            </div>

            <div
              style={{
                background: "var(--bg-main)",
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius-sm)",
                padding: "12px",
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>
                Recall@10
              </div>
              <div style={{ fontSize: "18px", fontWeight: 700, marginTop: "4px", color: "#0284c7" }}>
                {formatMetric(evaluation.metrics.recall_at_10, true)}
              </div>
              <div style={{ fontSize: "10px", color: "var(--text-muted)", marginTop: "2px" }}>Known relevant</div>
            </div>

            <div
              style={{
                background: "var(--bg-main)",
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius-sm)",
                padding: "12px",
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>
                NDCG@10
              </div>
              <div style={{ fontSize: "18px", fontWeight: 700, marginTop: "4px", color: "#7c3aed" }}>
                {formatMetric(evaluation.metrics.ndcg_at_10)}
              </div>
              <div style={{ fontSize: "10px", color: "var(--text-muted)", marginTop: "2px" }}>Graded gain</div>
            </div>

            <div
              style={{
                background: "var(--bg-main)",
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius-sm)",
                padding: "12px",
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>
                Hit Rate@5
              </div>
              <div style={{ fontSize: "18px", fontWeight: 700, marginTop: "4px", color: "#059669" }}>
                {formatMetric(evaluation.metrics.hit_rate_at_5, true)}
              </div>
              <div style={{ fontSize: "10px", color: "var(--text-muted)", marginTop: "2px" }}>≥1 hit in top 5</div>
            </div>

            <div
              style={{
                background: "var(--bg-main)",
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius-sm)",
                padding: "12px",
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>
                Save Rate
              </div>
              <div style={{ fontSize: "18px", fontWeight: 700, marginTop: "4px", color: "#2563eb" }}>
                {formatMetric(evaluation.metrics.save_rate, true)}
              </div>
              <div style={{ fontSize: "10px", color: "var(--text-muted)", marginTop: "2px" }}>Bookmarked</div>
            </div>

            <div
              style={{
                background: "var(--bg-main)",
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius-sm)",
                padding: "12px",
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>
                Engagement
              </div>
              <div style={{ fontSize: "18px", fontWeight: 700, marginTop: "4px", color: "#d97706" }}>
                {formatMetric(evaluation.metrics.engagement_rate, true)}
              </div>
              <div style={{ fontSize: "10px", color: "var(--text-muted)", marginTop: "2px" }}>View/Save/Apply</div>
            </div>

            <div
              style={{
                background: "var(--bg-main)",
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius-sm)",
                padding: "12px",
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>
                Dismissal
              </div>
              <div style={{ fontSize: "18px", fontWeight: 700, marginTop: "4px", color: "#dc2626" }}>
                {formatMetric(evaluation.metrics.dismissal_rate, true)}
              </div>
              <div style={{ fontSize: "10px", color: "var(--text-muted)", marginTop: "2px" }}>Hidden / rejected</div>
            </div>
          </div>

          {evaluation.metrics.notes && (
            <div
              style={{
                marginTop: "10px",
                fontSize: "12px",
                color: "var(--text-muted)",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              <Info size={13} />
              <span>{evaluation.metrics.notes}</span>
            </div>
          )}
        </div>
      )}

      {/* ── Version Comparison (R0 vs R1 vs R2) ── */}
      {evaluation?.ranking_comparison &&
        Object.keys(evaluation.ranking_comparison).length > 1 && (
          <div
            style={{
              marginBottom: "28px",
              padding: "16px",
              background: "var(--bg-main)",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border-color)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                marginBottom: "12px",
                fontSize: "13px",
                fontWeight: 700,
              }}
            >
              <Scale size={15} color="var(--primary)" />
              <span>Ranking Algorithm Version Comparison</span>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                gap: "12px",
              }}
            >
              {Object.entries(evaluation.ranking_comparison).map(([vKey, vComp]) => (
                <div
                  key={vKey}
                  style={{
                    background: "var(--bg-card)",
                    border: "1px solid var(--border-color)",
                    borderRadius: "var(--radius-sm)",
                    padding: "12px",
                  }}
                >
                  <div style={{ fontSize: "12px", fontWeight: 700, marginBottom: "8px" }}>
                    {vComp.display_name}
                  </div>
                  <div style={{ fontSize: "11px", color: "var(--text-muted)", display: "flex", flexDirection: "column", gap: "4px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span>Precision@5:</span>
                      <strong>{formatMetric(vComp.metrics.precision_at_5, true)}</strong>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span>NDCG@10:</span>
                      <strong>{formatMetric(vComp.metrics.ndcg_at_10)}</strong>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span>Save Rate:</span>
                      <strong>{formatMetric(vComp.metrics.save_rate, true)}</strong>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span>Sample Size:</span>
                      <span>{vComp.sample_size} items</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

      {/* ── Recommendation Snapshot Timeline ── */}
      <div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "12px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <FileText size={16} color="var(--primary)" />
            <span style={{ fontSize: "14px", fontWeight: 700 }}>
              Historical Recommendation Snapshots ({totalHistory})
            </span>
          </div>
        </div>

        {loading ? (
          <div style={{ padding: "20px", textAlign: "center", color: "var(--text-muted)", fontSize: "13px" }}>
            Loading recommendation history...
          </div>
        ) : history.length === 0 ? (
          <div
            style={{
              padding: "24px",
              textAlign: "center",
              color: "var(--text-muted)",
              background: "var(--bg-main)",
              borderRadius: "var(--radius-sm)",
              fontSize: "13px",
            }}
          >
            No recommendation snapshots found. When recommendations are generated, point-in-time snapshots are automatically captured here for audit and offline evaluation.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "12px",
                textAlign: "left",
              }}
            >
              <thead>
                <tr
                  style={{
                    borderBottom: "2px solid var(--border-color)",
                    color: "var(--text-muted)",
                    fontWeight: 600,
                  }}
                >
                  <th style={{ padding: "8px 10px" }}>Date & Time</th>
                  <th style={{ padding: "8px 10px" }}>Version</th>
                  <th style={{ padding: "8px 10px" }}>Candidates</th>
                  <th style={{ padding: "8px 10px" }}>Top Recommendations Preview</th>
                  <th style={{ padding: "8px 10px", textAlign: "right" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {history.map((snap) => (
                  <tr
                    key={snap.id}
                    style={{
                      borderBottom: "1px solid var(--border-color)",
                    }}
                  >
                    <td style={{ padding: "10px", whiteSpace: "nowrap" }}>
                      <div style={{ fontWeight: 600 }}>
                        {new Date(snap.created_at).toLocaleDateString()}
                      </div>
                      <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                        {new Date(snap.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </div>
                    </td>
                    <td style={{ padding: "10px" }}>
                      <span
                        style={{
                          fontSize: "11px",
                          fontFamily: "monospace",
                          background: "var(--bg-main)",
                          padding: "2px 6px",
                          borderRadius: "4px",
                          border: "1px solid var(--border-color)",
                        }}
                      >
                        {snap.ranking_version}
                      </span>
                    </td>
                    <td style={{ padding: "10px", whiteSpace: "nowrap" }}>
                      <strong>{snap.returned_count}</strong>
                      <span style={{ color: "var(--text-muted)", fontSize: "11px" }}> / {snap.candidate_count}</span>
                    </td>
                    <td style={{ padding: "10px" }}>
                      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                        {snap.top_opportunity_titles.slice(0, 2).map((t, idx) => (
                          <span
                            key={idx}
                            style={{
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                              maxWidth: "320px",
                              fontSize: "12px",
                            }}
                          >
                            {idx + 1}. {t}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td style={{ padding: "10px", textAlign: "right", whiteSpace: "nowrap" }}>
                      <button
                        onClick={() => handleInspectSnapshot(snap.id)}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "4px",
                          padding: "4px 8px",
                          fontSize: "11px",
                          fontWeight: 600,
                          borderRadius: "var(--radius-sm)",
                          border: "1px solid var(--border-color)",
                          background: "var(--bg-card)",
                          color: "var(--primary)",
                          cursor: "pointer",
                        }}
                      >
                        <Eye size={12} />
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Inspect Snapshot Modal ── */}
      {selectedSnapshotId && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: "20px",
          }}
        >
          <div
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border-color)",
              borderRadius: "var(--radius-lg)",
              width: "100%",
              maxWidth: "850px",
              maxHeight: "85vh",
              display: "flex",
              flexDirection: "column",
              boxShadow: "var(--shadow-lg)",
              overflow: "hidden",
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "16px 20px",
                borderBottom: "1px solid var(--border-color)",
              }}
            >
              <div>
                <h4 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>
                  Recommendation Snapshot Detail
                </h4>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "2px" }}>
                  Snapshot ID: {selectedSnapshotId}
                </div>
              </div>
              <button
                onClick={closeSnapshotModal}
                style={{
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--text-muted)",
                }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Modal Body */}
            <div style={{ padding: "20px", overflowY: "auto", flex: 1 }}>
              {detailLoading ? (
                <div style={{ padding: "40px", textAlign: "center", color: "var(--text-muted)" }}>
                  Loading point-in-time recommendation items...
                </div>
              ) : snapshotDetail ? (
                <div>
                  <div
                    style={{
                      display: "flex",
                      gap: "16px",
                      marginBottom: "16px",
                      padding: "12px",
                      background: "var(--bg-main)",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "12px",
                    }}
                  >
                    <div>
                      <span style={{ color: "var(--text-muted)" }}>Recorded At: </span>
                      <strong>{new Date(snapshotDetail.created_at).toLocaleString()}</strong>
                    </div>
                    <div>
                      <span style={{ color: "var(--text-muted)" }}>Version: </span>
                      <strong style={{ fontFamily: "monospace" }}>{snapshotDetail.ranking_version}</strong>
                    </div>
                    <div>
                      <span style={{ color: "var(--text-muted)" }}>Returned Items: </span>
                      <strong>{snapshotDetail.returned_count}</strong>
                    </div>
                  </div>

                  <table
                    style={{
                      width: "100%",
                      borderCollapse: "collapse",
                      fontSize: "12px",
                      textAlign: "left",
                    }}
                  >
                    <thead>
                      <tr
                        style={{
                          borderBottom: "2px solid var(--border-color)",
                          color: "var(--text-muted)",
                        }}
                      >
                        <th style={{ padding: "8px" }}>Rank</th>
                        <th style={{ padding: "8px" }}>Opportunity</th>
                        <th style={{ padding: "8px", textAlign: "right" }}>Base</th>
                        <th style={{ padding: "8px", textAlign: "right" }}>Pers.</th>
                        <th style={{ padding: "8px", textAlign: "right" }}>Beh.</th>
                        <th style={{ padding: "8px", textAlign: "right" }}>Final</th>
                        <th style={{ padding: "8px" }}>Feedback Outcome</th>
                      </tr>
                    </thead>
                    <tbody>
                      {snapshotDetail.items.map((item) => (
                        <tr
                          key={item.id}
                          style={{ borderBottom: "1px solid var(--border-color)" }}
                        >
                          <td style={{ padding: "8px", fontWeight: 700 }}>#{item.rank}</td>
                          <td style={{ padding: "8px" }}>
                            <div style={{ fontWeight: 600 }}>
                              {item.opportunity?.title || `Opportunity ${item.opportunity_id.slice(0, 8)}`}
                            </div>
                            <div style={{ fontSize: "10px", color: "var(--text-muted)" }}>
                              {item.opportunity?.opportunity_type} • {item.opportunity?.delivery_mode}
                            </div>
                          </td>
                          <td style={{ padding: "8px", textAlign: "right", fontFamily: "monospace" }}>
                            {item.base_relevance_score.toFixed(3)}
                          </td>
                          <td style={{ padding: "8px", textAlign: "right", fontFamily: "monospace" }}>
                            {item.personalization_score.toFixed(3)}
                          </td>
                          <td style={{ padding: "8px", textAlign: "right", fontFamily: "monospace" }}>
                            {item.behavioral_adjustment >= 0 ? `+${item.behavioral_adjustment.toFixed(3)}` : item.behavioral_adjustment.toFixed(3)}
                          </td>
                          <td style={{ padding: "8px", textAlign: "right", fontWeight: 700, fontFamily: "monospace", color: "var(--primary)" }}>
                            {item.final_score.toFixed(3)}
                          </td>
                          <td style={{ padding: "8px" }}>
                            {item.user_feedback.length > 0 ? (
                              <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
                                {item.user_feedback.map((fb, idx) => (
                                  <span
                                    key={idx}
                                    style={{
                                      fontSize: "10px",
                                      fontWeight: 600,
                                      padding: "2px 6px",
                                      borderRadius: "4px",
                                      background:
                                        fb === "APPLY" || fb === "SAVE" || fb === "INTERESTED"
                                          ? "#dcfce7"
                                          : fb === "VIEW"
                                          ? "#e0f2fe"
                                          : "#fee2e2",
                                      color:
                                        fb === "APPLY" || fb === "SAVE" || fb === "INTERESTED"
                                          ? "#15803d"
                                          : fb === "VIEW"
                                          ? "#0369a1"
                                          : "#b91c1c",
                                    }}
                                  >
                                    {fb}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>No interaction</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </div>

            {/* Modal Footer */}
            <div
              style={{
                padding: "12px 20px",
                borderTop: "1px solid var(--border-color)",
                display: "flex",
                justifyContent: "flex-end",
              }}
            >
              <button
                onClick={closeSnapshotModal}
                style={{
                  padding: "6px 14px",
                  fontSize: "12px",
                  fontWeight: 600,
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--border-color)",
                  background: "var(--bg-main)",
                  cursor: "pointer",
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
