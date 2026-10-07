"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Activity,
  AlertCircle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  HelpCircle,
  Info,
  RefreshCw,
  Scale,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  TrendingUp,
  XCircle,
} from "lucide-react";
import {
  fetchResearcherCalibrations,
  recomputeCalibrations,
} from "../../services/api";
import type {
  CalibrationState,
  PersonalizationCalibration,
  PersonalizationCalibrationResponse,
} from "../../types/personalization";

interface PersonalizationCalibrationCardProps {
  profileId: string;
  userId?: string;
  className?: string;
}

export const PersonalizationCalibrationCard: React.FC<PersonalizationCalibrationCardProps> = ({
  profileId,
  userId,
  className = "",
}) => {
  const [data, setData] = useState<PersonalizationCalibrationResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRecomputing, setIsRecomputing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [filterState, setFilterState] = useState<CalibrationState | "ALL">("ALL");

  const loadCalibrationData = useCallback(async () => {
    if (!profileId) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetchResearcherCalibrations(profileId, undefined, userId);
      setData(res);
    } catch (err: unknown) {
      console.error("Failed to load personalization calibration:", err);
      setError(err instanceof Error ? err.message : "Failed to load calibration data");
    } finally {
      setIsLoading(false);
    }
  }, [profileId, userId]);

  useEffect(() => {
    loadCalibrationData();
  }, [loadCalibrationData]);

  const handleRecompute = async () => {
    if (!profileId || isRecomputing) return;
    setIsRecomputing(true);
    setError(null);
    try {
      const res = await recomputeCalibrations(profileId, undefined, userId);
      setData(res);
    } catch (err: unknown) {
      console.error("Failed to recompute calibration:", err);
      setError(err instanceof Error ? err.message : "Failed to recompute calibration");
    } finally {
      setIsRecomputing(false);
    }
  };

  const filteredItems = (data?.items || []).filter((item) => {
    if (filterState === "ALL") return true;
    return item.calibration_state === filterState;
  });

  const getStateBadge = (state: CalibrationState) => {
    switch (state) {
      case "STABLE":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
            <CheckCircle2 className="w-3 h-3" />
            Stable
          </span>
        );
      case "CALIBRATING":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-600 border border-blue-500/20">
            <Activity className="w-3 h-3" />
            Calibrating
          </span>
        );
      case "EARLY_SIGNAL":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-600 border border-amber-500/20">
            <Clock className="w-3 h-3" />
            Early Signal
          </span>
        );
      case "CONFLICTED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-600 border border-purple-500/20">
            <Scale className="w-3 h-3" />
            Conflicted Feedback
          </span>
        );
      case "INSUFFICIENT_DATA":
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-500/10 text-slate-600 border border-slate-500/20">
            <HelpCircle className="w-3 h-3" />
            Insufficient Evidence
          </span>
        );
    }
  };

  const getModifierDisplay = (modifier: number) => {
    if (modifier > 0) {
      return (
        <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-600 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
          <ArrowUpRight className="w-3.5 h-3.5" />
          +{modifier.toFixed(3)}
        </span>
      );
    }
    if (modifier < 0) {
      return (
        <span className="inline-flex items-center gap-1 text-xs font-bold text-rose-600 bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20">
          <ArrowDownRight className="w-3.5 h-3.5" />
          {modifier.toFixed(3)}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
        0.000 (Neutral)
      </span>
    );
  };

  return (
    <div
      className={`bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden transition-all ${className}`}
    >
      {/* Header */}
      <div className="p-6 border-b border-slate-100">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="p-1.5 rounded-lg bg-indigo-50 text-indigo-600">
                <Scale className="w-5 h-5" />
              </span>
              <h3 className="text-lg font-bold text-slate-900">
                Personalization Calibration & Feedback Loop
              </h3>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              Measures recommendation performance against your subsequent feedback and applies bounded, explainable calibration modifiers.
            </p>
          </div>

          <button
            onClick={handleRecompute}
            disabled={isRecomputing || isLoading}
            className="inline-flex items-center justify-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRecomputing ? "animate-spin" : ""}`} />
            {isRecomputing ? "Recomputing..." : "Recompute Calibration"}
          </button>
        </div>

        {/* Architectural Hierarchy Banner */}
        <div className="mt-4 p-3 rounded-lg bg-slate-50 border border-slate-200/80 flex flex-wrap items-center gap-2 text-xs text-slate-600">
          <ShieldCheck className="w-4 h-4 text-emerald-500 flex-shrink-0" />
          <span className="font-semibold text-slate-800">Precedence Guarantee:</span>
          <span>Explicit Preferences (Authoritative)</span>
          <span className="text-slate-400">→</span>
          <span>Adaptive Signals (Bounded ±0.10)</span>
          <span className="text-slate-400">→</span>
          <span className="font-medium text-indigo-600">Calibration Modifier (Bounded ±0.05)</span>
        </div>

        {/* Stats Summary Bar */}
        {data && (
          <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
              <span className="text-xs text-slate-500">Total Tracked Signals</span>
              <p className="text-lg font-bold text-slate-900 mt-0.5">{data.total_count}</p>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
              <span className="text-xs text-slate-500">Actively Calibrated</span>
              <p className="text-lg font-bold text-indigo-600 mt-0.5">{data.calibrated_signals_count}</p>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
              <span className="text-xs text-slate-500">Average Confidence</span>
              <p className="text-lg font-bold text-slate-900 mt-0.5">
                {Math.round(data.average_confidence * 100)}%
              </p>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
              <span className="text-xs text-slate-500">Stable / Calibrating</span>
              <p className="text-lg font-bold text-emerald-600 mt-0.5">
                {(data.state_counts?.STABLE || 0) + (data.state_counts?.CALIBRATING || 0)}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Filter Tabs */}
      <div className="px-6 pt-4 pb-2 flex items-center gap-1.5 overflow-x-auto border-b border-slate-100 text-xs">
        {(["ALL", "STABLE", "CALIBRATING", "EARLY_SIGNAL", "CONFLICTED", "INSUFFICIENT_DATA"] as const).map(
          (st) => (
            <button
              key={st}
              onClick={() => setFilterState(st)}
              className={`px-3 py-1.5 rounded-lg font-medium whitespace-nowrap transition-colors ${
                filterState === st
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {st === "ALL" ? "All Records" : st.replace("_", " ")}
            </button>
          )
        )}
      </div>

      {/* Content */}
      <div className="p-6">
        {isLoading ? (
          <div className="py-12 flex flex-col items-center justify-center text-center">
            <RefreshCw className="w-8 h-8 text-indigo-500 animate-spin mb-3" />
            <p className="text-sm font-medium text-slate-600">Loading personalization calibrations...</p>
          </div>
        ) : error ? (
          <div className="p-4 rounded-lg bg-rose-50 border border-rose-200 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-rose-800">Error loading calibration</p>
              <p className="text-xs text-rose-600 mt-0.5">{error}</p>
            </div>
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="py-12 flex flex-col items-center justify-center text-center">
            <div className="p-3 rounded-full bg-slate-100 text-slate-400 mb-3">
              <Info className="w-6 h-6" />
            </div>
            <p className="text-sm font-medium text-slate-700">
              No calibration records match the selected filter.
            </p>
            <p className="text-xs text-slate-500 mt-1 max-w-sm">
              As you interact with recommendations (save, apply, or dismiss), the feedback loop attributes outcomes and calibrates personalization.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredItems.map((item) => (
              <div
                key={item.id}
                className="p-4 rounded-lg border border-slate-200 hover:border-slate-300 bg-white transition-all shadow-xs"
              >
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-2 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-600 tracking-wider">
                      {item.dimension.replace("_", " ")}
                    </span>
                    <span className="text-sm font-bold text-slate-900">
                      {item.signal_value}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {getStateBadge(item.calibration_state)}
                    {getModifierDisplay(item.net_calibration_modifier)}
                  </div>
                </div>

                <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                  <div>
                    <span className="text-slate-500">Recs Influenced:</span>
                    <span className="ml-1.5 font-semibold text-slate-800">
                      {item.recommendations_influenced_count}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500">Positive Feedback:</span>
                    <span className="ml-1.5 font-semibold text-emerald-600">
                      {item.positive_outcome_count}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500">Negative Feedback:</span>
                    <span className="ml-1.5 font-semibold text-rose-600">
                      {item.negative_outcome_count}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500">Confidence:</span>
                    <span className="ml-1.5 font-semibold text-slate-800">
                      {Math.round(item.calibration_confidence * 100)}%
                    </span>
                  </div>
                </div>

                {/* Explanation text */}
                <p className="mt-2.5 text-xs text-slate-600 leading-relaxed bg-slate-50 p-2 rounded">
                  {item.deterministic_explanation}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
