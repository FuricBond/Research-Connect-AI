"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clock,
  HelpCircle,
  Info,
  RefreshCw,
  Sparkles,
  TrendingUp,
  XCircle,
} from "lucide-react";
import {
  fetchResearcherAdaptiveSignals,
  fetchAdaptiveSignalsExplanation,
  recomputeAdaptiveSignals,
} from "../../services/api";
import type {
  AdaptiveEvidenceState,
  AdaptivePreferenceSignal,
  AdaptiveSignalExplanationResponse,
} from "../../types/personalization";

interface AdaptiveSignalsCardProps {
  profileId: string;
  userId?: string;
  className?: string;
}

export const AdaptiveSignalsCard: React.FC<AdaptiveSignalsCardProps> = ({
  profileId,
  userId,
  className = "",
}) => {
  const [signals, setSignals] = useState<AdaptivePreferenceSignal[]>([]);
  const [explanation, setExplanation] = useState<AdaptiveSignalExplanationResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRecomputing, setIsRecomputing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [filterState, setFilterState] = useState<AdaptiveEvidenceState | "ALL">("ALL");

  const loadSignalsData = useCallback(async () => {
    if (!profileId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [signalsRes, explanationRes] = await Promise.all([
        fetchResearcherAdaptiveSignals(profileId, undefined, userId),
        fetchAdaptiveSignalsExplanation(profileId, userId),
      ]);
      setSignals(signalsRes.items || []);
      setExplanation(explanationRes);
    } catch (err: unknown) {
      console.error("Failed to load adaptive signals:", err);
      setError(err instanceof Error ? err.message : "Failed to load adaptive signals");
    } finally {
      setIsLoading(false);
    }
  }, [profileId, userId]);

  useEffect(() => {
    loadSignalsData();
  }, [loadSignalsData]);

  const handleRecompute = async () => {
    if (isRecomputing || !profileId) return;
    setIsRecomputing(true);
    setError(null);
    try {
      await recomputeAdaptiveSignals(profileId, undefined, userId);
      await loadSignalsData();
    } catch (err: unknown) {
      console.error("Failed to recompute adaptive signals:", err);
      setError(err instanceof Error ? err.message : "Failed to recompute signals");
    } finally {
      setIsRecomputing(false);
    }
  };

  const getStateBadge = (state: AdaptiveEvidenceState) => {
    switch (state) {
      case "STRONG":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300">
            <CheckCircle2 className="w-3 h-3" /> Strong Affinity
          </span>
        );
      case "ESTABLISHED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300">
            <TrendingUp className="w-3 h-3" /> Established
          </span>
        );
      case "EMERGING":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300">
            <Sparkles className="w-3 h-3" /> Emerging Pattern
          </span>
        );
      case "CONFLICT":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-950/60 dark:text-purple-300">
            <AlertCircle className="w-3 h-3" /> Mixed Feedback
          </span>
        );
      case "INSUFFICIENT_EVIDENCE":
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-normal bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
            <HelpCircle className="w-3 h-3" /> Insufficient Evidence
          </span>
        );
    }
  };

  const filteredSignals = signals.filter((s) => {
    if (filterState === "ALL") return true;
    return s.evidence_state === filterState;
  });

  return (
    <div
      className={`bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-sm ${className}`}
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              Adaptive Behavioral Signals
            </h3>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Bounded behavioral signals derived deterministically from your opportunity activity.
          </p>
        </div>

        <button
          onClick={handleRecompute}
          disabled={isRecomputing || isLoading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition-colors disabled:opacity-50 self-start sm:self-auto"
          title="Recalculate adaptive signals from interaction history"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRecomputing ? "animate-spin" : ""}`} />
          {isRecomputing ? "Recomputing..." : "Recompute Signals"}
        </button>
      </div>

      {/* Info Notice: Explicit vs Adaptive */}
      <div className="mt-4 p-3 rounded-lg bg-indigo-50/70 dark:bg-indigo-950/30 border border-indigo-100 dark:border-indigo-900/50 flex items-start gap-2.5 text-xs text-indigo-900 dark:text-indigo-200">
        <Info className="w-4 h-4 text-indigo-600 dark:text-indigo-400 mt-0.5 flex-shrink-0" />
        <div className="space-y-1">
          <p className="font-medium">
            Explicit preferences remain authoritative.
          </p>
          <p className="text-indigo-700 dark:text-indigo-300">
            These signals reflect repeated saves, dismissals, and expressed interests. They provide secondary, bounded personalization (up to ±10%) and never overwrite your configured preferences.
          </p>
        </div>
      </div>

      {/* Summary Explanation */}
      {explanation && (
        <div className="mt-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-800">
          <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
            {explanation.summary_explanation}
          </p>
          <div className="flex flex-wrap items-center gap-4 mt-2 pt-2 border-t border-slate-200/60 dark:border-slate-700/60 text-[11px] text-slate-500 dark:text-slate-400">
            <span>Established: <strong className="text-slate-800 dark:text-slate-200">{explanation.established_signals_count}</strong></span>
            <span>Emerging: <strong className="text-slate-800 dark:text-slate-200">{explanation.emerging_signals_count}</strong></span>
            <span>Mixed: <strong className="text-slate-800 dark:text-slate-200">{explanation.conflict_signals_count}</strong></span>
            <span>Sparse: <strong className="text-slate-800 dark:text-slate-200">{explanation.insufficient_signals_count}</strong></span>
          </div>
        </div>
      )}

      {/* State Filters */}
      <div className="flex items-center gap-1.5 mt-4 overflow-x-auto pb-1 text-xs">
        {(["ALL", "STRONG", "ESTABLISHED", "EMERGING", "CONFLICT", "INSUFFICIENT_EVIDENCE"] as const).map((st) => (
          <button
            key={st}
            onClick={() => setFilterState(st)}
            className={`px-2.5 py-1 rounded-md transition-colors whitespace-nowrap ${
              filterState === st
                ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 font-medium"
                : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
            }`}
          >
            {st === "ALL" ? "All Signals" : st.replace("_", " ")}
          </button>
        ))}
      </div>

      {/* Error display */}
      {error && (
        <div className="mt-3 p-3 rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-xs text-red-700 dark:text-red-300 flex items-center gap-2">
          <XCircle className="w-4 h-4 text-red-500" />
          <span>{error}</span>
        </div>
      )}

      {/* Signals List */}
      <div className="mt-3 space-y-2.5">
        {isLoading ? (
          <div className="py-8 text-center text-xs text-slate-400 dark:text-slate-500">
            <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-slate-400" />
            Loading adaptive signals...
          </div>
        ) : filteredSignals.length === 0 ? (
          <div className="py-6 text-center text-xs text-slate-400 dark:text-slate-500 border border-dashed border-slate-200 dark:border-slate-800 rounded-lg">
            No adaptive signals match this filter. As you interact with opportunities, behavioral patterns will appear here.
          </div>
        ) : (
          filteredSignals.map((sig) => (
            <div
              key={sig.id}
              className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/40 hover:border-slate-300 dark:hover:border-slate-700 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[11px] font-mono uppercase tracking-wider text-slate-500 dark:text-slate-400 bg-slate-200/70 dark:bg-slate-700/60 px-1.5 py-0.5 rounded">
                      {sig.dimension.replace("_", " ")}
                    </span>
                    <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {sig.signal_value}
                    </span>
                    {getStateBadge(sig.evidence_state)}
                  </div>

                  <p className="text-xs text-slate-600 dark:text-slate-300 mt-1.5 leading-relaxed">
                    {sig.deterministic_explanation}
                  </p>
                </div>

                <div className="text-right flex-shrink-0">
                  <div className="text-xs font-semibold text-slate-900 dark:text-slate-100">
                    {sig.weighted_signal_strength > 0 ? "+" : ""}
                    {(sig.weighted_signal_strength * 100).toFixed(0)}%
                  </div>
                  <div className="text-[10px] text-slate-400 dark:text-slate-500">
                    Strength
                  </div>
                  <div className="text-[10px] text-slate-500 dark:text-slate-400 mt-1">
                    Conf: {(sig.confidence * 100).toFixed(0)}%
                  </div>
                </div>
              </div>

              {/* Evidence Metrics Footer */}
              <div className="mt-2.5 pt-2 border-t border-slate-200/60 dark:border-slate-700/60 flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
                <div className="flex items-center gap-3">
                  <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                    +{sig.positive_evidence_count} positive
                  </span>
                  <span className="text-rose-600 dark:text-rose-400 font-medium">
                    -{sig.negative_evidence_count} negative
                  </span>
                  <span>
                    Total: {sig.total_evidence_count}
                  </span>
                </div>

                {sig.latest_evidence_timestamp && (
                  <div className="flex items-center gap-1 text-slate-400 dark:text-slate-500">
                    <Clock className="w-3 h-3" />
                    <span>
                      {new Date(sig.latest_evidence_timestamp).toLocaleDateString()}
                    </span>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
