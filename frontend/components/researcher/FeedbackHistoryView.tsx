"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  fetchFeedbackSummary,
  fetchRecommendationFeedbackHistory,
  deleteRecommendationFeedback,
} from "../../services/api";
import type {
  FeedbackItem,
  FeedbackSummaryResponse,
  FeedbackType,
} from "../../types/researcher";
import {
  Activity,
  Bookmark,
  CheckCircle2,
  Clock,
  Eye,
  Flame,
  Layers,
  RefreshCw,
  Shield,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  XCircle,
} from "lucide-react";

interface FeedbackHistoryViewProps {
  profileId: string;
  userId?: string;
  onFeedbackChanged?: () => void;
}

export function FeedbackHistoryView({
  profileId,
  userId,
  onFeedbackChanged,
}: FeedbackHistoryViewProps) {
  const [loading, setLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [summary, setSummary] = useState<FeedbackSummaryResponse | null>(null);
  const [history, setHistory] = useState<FeedbackItem[]>([]);
  const [filterType, setFilterType] = useState<string>("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadFeedbackData = useCallback(async (refresh = false) => {
    if (!profileId) return;
    if (refresh) setIsRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const [sumData, histData] = await Promise.all([
        fetchFeedbackSummary(profileId, userId),
        fetchRecommendationFeedbackHistory(
          profileId,
          { limit: 30, feedbackType: filterType || undefined },
          userId
        ),
      ]);
      setSummary(sumData);
      setHistory(histData.items);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Failed to load feedback learning data.";
      setError(msg);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, [profileId, userId, filterType]);

  useEffect(() => {
    loadFeedbackData();
  }, [loadFeedbackData]);

  const handleDelete = async (feedbackId: string) => {
    if (!profileId || deletingId) return;
    setDeletingId(feedbackId);
    try {
      await deleteRecommendationFeedback(profileId, feedbackId, userId);
      setHistory((prev) => prev.filter((item) => item.id !== feedbackId));
      if (summary) {
        setSummary({
          ...summary,
          total_feedback_count: Math.max(0, summary.total_feedback_count - 1),
        });
      }
      onFeedbackChanged?.();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to delete feedback record.";
      setError(msg);
    } finally {
      setDeletingId(null);
    }
  };

  const getFeedbackIcon = (type: FeedbackType) => {
    switch (type) {
      case "SAVE":
        return <Bookmark size={14} className="text-amber-400" />;
      case "INTERESTED":
        return <ThumbsUp size={14} className="text-emerald-400" />;
      case "NOT_INTERESTED":
        return <ThumbsDown size={14} className="text-rose-400" />;
      case "DISMISS":
        return <XCircle size={14} className="text-slate-400" />;
      case "APPLY":
        return <Flame size={14} className="text-purple-400" />;
      case "VIEW":
      default:
        return <Eye size={14} className="text-blue-400" />;
    }
  };

  const getFeedbackBadgeClass = (type: FeedbackType) => {
    switch (type) {
      case "SAVE":
        return "bg-amber-950/60 text-amber-300 border-amber-800/50";
      case "INTERESTED":
        return "bg-emerald-950/60 text-emerald-300 border-emerald-800/50";
      case "NOT_INTERESTED":
        return "bg-rose-950/60 text-rose-300 border-rose-800/50";
      case "DISMISS":
        return "bg-slate-800 text-slate-300 border-slate-700";
      case "APPLY":
        return "bg-purple-950/60 text-purple-300 border-purple-800/50";
      case "VIEW":
      default:
        return "bg-blue-950/60 text-blue-300 border-blue-800/50";
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-white tracking-tight">
              Recommendation Feedback & Behavioral Learning
            </h2>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-900/60 text-emerald-300 border border-emerald-700/50">
              Phase 3.6 Loop
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Deterministic feedback aggregation with exponential decay (T₁/₂ = 30d), confidence scaling, and explicit preference dominance.
          </p>
        </div>

        <button
          onClick={() => loadFeedbackData(true)}
          disabled={loading || isRefreshing}
          className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-slate-200 border border-slate-700 hover:bg-slate-700 hover:text-white transition-colors disabled:opacity-50"
        >
          <RefreshCw size={13} className={isRefreshing ? "animate-spin" : ""} />
          <span>Refresh Signals</span>
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div className="p-3 bg-red-950/50 border border-red-800 rounded text-red-300 text-xs">
          {error}
        </div>
      )}

      {/* Summary KPI Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>Total Feedback</span>
              <Activity size={14} className="text-indigo-400" />
            </div>
            <div className="text-2xl font-bold text-white font-mono mt-1">
              {summary.total_feedback_count}
            </div>
            <span className="text-[10px] text-slate-500">
              {summary.is_cold_start ? "Cold Start Fallback" : "Active Behavioral Model"}
            </span>
          </div>

          <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>Behavioral Confidence</span>
              <Shield size={14} className="text-emerald-400" />
            </div>
            <div className="text-2xl font-bold text-white font-mono mt-1">
              {(summary.overall_confidence * 100).toFixed(1)}%
            </div>
            <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
              <div
                className="bg-emerald-500 h-full rounded-full transition-all duration-300"
                style={{ width: `${Math.min(100, summary.overall_confidence * 100)}%` }}
              />
            </div>
          </div>

          <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>Suppressed Items</span>
              <XCircle size={14} className="text-rose-400" />
            </div>
            <div className="text-2xl font-bold text-rose-300 font-mono mt-1">
              {summary.suppressed_count}
            </div>
            <span className="text-[10px] text-slate-500">
              Omitted from candidate retrieval
            </span>
          </div>

          <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>Feedback Distribution</span>
              <Layers size={14} className="text-blue-400" />
            </div>
            <div className="flex items-center gap-1.5 mt-2 flex-wrap text-[11px]">
              <span className="text-emerald-400 font-semibold" title="Interested / Save">
                +{(summary.counts_by_type["SAVE"] || 0) + (summary.counts_by_type["INTERESTED"] || 0)}
              </span>
              <span className="text-slate-600">/</span>
              <span className="text-rose-400 font-semibold" title="Dismiss / Not Interested">
                -{(summary.counts_by_type["DISMISS"] || 0) + (summary.counts_by_type["NOT_INTERESTED"] || 0)}
              </span>
              <span className="text-slate-600">/</span>
              <span className="text-blue-400" title="Views">
                {summary.counts_by_type["VIEW"] || 0} views
              </span>
            </div>
            <span className="text-[10px] text-slate-500 mt-1 block">
              30-day temporal window
            </span>
          </div>
        </div>
      )}

      {/* Top Learned Preferences / Signals Preview */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-2">
            <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
              <CheckCircle2 size={13} className="text-emerald-400" />
              Learned Positive Topics (+Signal)
            </span>
            {summary.top_positive_topics.length > 0 ? (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {summary.top_positive_topics.map((t, idx) => (
                  <span
                    key={idx}
                    className="px-2.5 py-1 rounded bg-emerald-950/70 text-emerald-300 border border-emerald-800/40 text-xs font-medium"
                  >
                    {t}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500 italic">
                No positive topic preferences learned yet. Save or mark opportunities as Interested to train.
              </p>
            )}
          </div>

          <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-2">
            <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
              <XCircle size={13} className="text-rose-400" />
              Learned Negative Topics (-Signal)
            </span>
            {summary.top_negative_topics.length > 0 ? (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {summary.top_negative_topics.map((t, idx) => (
                  <span
                    key={idx}
                    className="px-2.5 py-1 rounded bg-rose-950/70 text-rose-300 border border-rose-800/40 text-xs font-medium"
                  >
                    {t}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500 italic">
                No negative topic preferences learned yet. Dismissing opportunities will register negative signals.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Feedback History Log Table */}
      <div className="space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h3 className="text-sm font-semibold text-white">Recent Interaction History</h3>
          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-400">Filter:</label>
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="bg-slate-950 text-slate-300 border border-slate-800 rounded px-2 py-1 text-xs focus:outline-none focus:border-indigo-500"
            >
              <option value="">All Events</option>
              <option value="SAVE">SAVE</option>
              <option value="INTERESTED">INTERESTED</option>
              <option value="NOT_INTERESTED">NOT_INTERESTED</option>
              <option value="DISMISS">DISMISS</option>
              <option value="APPLY">APPLY</option>
              <option value="VIEW">VIEW</option>
            </select>
          </div>
        </div>

        {history.length > 0 ? (
          <div className="overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-950/80 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="py-2.5 px-3">Type</th>
                  <th className="py-2.5 px-3">Opportunity</th>
                  <th className="py-2.5 px-3">Type / Mode</th>
                  <th className="py-2.5 px-3">Source</th>
                  <th className="py-2.5 px-3">Recorded At</th>
                  <th className="py-2.5 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 bg-slate-900/40">
                {history.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-2 px-3 whitespace-nowrap">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold border ${getFeedbackBadgeClass(
                          item.feedback_type
                        )}`}
                      >
                        {getFeedbackIcon(item.feedback_type)}
                        {item.feedback_type}
                      </span>
                    </td>
                    <td className="py-2 px-3 font-medium text-white max-w-[240px] truncate">
                      {item.opportunity_title || item.opportunity_id}
                    </td>
                    <td className="py-2 px-3 text-slate-400 whitespace-nowrap">
                      {item.opportunity_type || "—"} / {item.delivery_mode || "—"}
                    </td>
                    <td className="py-2 px-3 text-slate-400 text-[11px] whitespace-nowrap font-mono">
                      {item.source}
                    </td>
                    <td className="py-2 px-3 text-slate-400 whitespace-nowrap flex items-center gap-1">
                      <Clock size={11} />
                      {new Date(item.created_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="py-2 px-3 text-right whitespace-nowrap">
                      <button
                        onClick={() => handleDelete(item.id)}
                        disabled={deletingId === item.id}
                        className="text-slate-500 hover:text-rose-400 transition-colors disabled:opacity-50 p-1"
                        title="Delete feedback entry (undoes behavioral training)"
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-8 text-center text-slate-500 text-xs bg-slate-950/40 rounded-lg border border-dashed border-slate-800">
            No feedback history found. Interact with recommendations to train the system.
          </div>
        )}
      </div>
    </div>
  );
}
