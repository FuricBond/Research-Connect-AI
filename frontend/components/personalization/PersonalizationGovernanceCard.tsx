"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Compass,
  FileText,
  HelpCircle,
  History,
  Info,
  Lock,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  Scale,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  Zap,
} from "lucide-react";
import {
  fetchPersonalizationHealth,
  fetchPersonalizationDrift,
  fetchGovernanceEvents,
  recomputePersonalizationHealth,
} from "../../services/api";
import type {
  AdaptationState,
  DriftType,
  EvidenceStrength,
  GovernanceEventType,
  GovernanceGateState,
  PersonalizationDriftEvaluation,
  PersonalizationGovernanceEvent,
  PersonalizationHealthResponse,
  PersonalizationHealthState,
  PreferenceAlignmentState,
  SignalDriftItem,
  SignalFreshnessState,
} from "../../types/personalization";

interface PersonalizationGovernanceCardProps {
  profileId: string;
  userId?: string;
  className?: string;
}

export const PersonalizationGovernanceCard: React.FC<PersonalizationGovernanceCardProps> = ({
  profileId,
  userId,
  className = "",
}) => {
  const [healthData, setHealthData] = useState<PersonalizationHealthResponse | null>(null);
  const [driftSignals, setDriftSignals] = useState<{
    drifting: SignalDriftItem[];
    stale: SignalDriftItem[];
    stable: SignalDriftItem[];
  }>({ drifting: [], stale: [], stable: [] });
  const [governanceEvents, setGovernanceEvents] = useState<PersonalizationGovernanceEvent[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRecomputing, setIsRecomputing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"SIGNALS" | "AUDIT">("SIGNALS");
  const [signalFilter, setSignalFilter] = useState<"ALL" | "DRIFTING" | "STALE" | "STABLE">("ALL");

  const loadAllGovernanceData = useCallback(async () => {
    if (!profileId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [healthRes, driftRes, eventsRes] = await Promise.all([
        fetchPersonalizationHealth(profileId, userId),
        fetchPersonalizationDrift(profileId, userId).catch(() => null),
        fetchGovernanceEvents(profileId, 10, 0, userId).catch(() => null),
      ]);
      setHealthData(healthRes);
      if (driftRes) {
        setDriftSignals({
          drifting: driftRes.drifting_signals,
          stale: driftRes.stale_signals,
          stable: driftRes.stable_signals,
        });
      }
      if (eventsRes) {
        setGovernanceEvents(eventsRes.items);
      }
    } catch (err: unknown) {
      console.error("Failed to load personalization governance data:", err);
      setError(err instanceof Error ? err.message : "Failed to load governance data");
    } finally {
      setIsLoading(false);
    }
  }, [profileId, userId]);

  useEffect(() => {
    loadAllGovernanceData();
  }, [loadAllGovernanceData]);

  const handleRecompute = async () => {
    if (!profileId || isRecomputing) return;
    setIsRecomputing(true);
    setError(null);
    try {
      const res = await recomputePersonalizationHealth(profileId, undefined, userId);
      setHealthData(res);
      // Refresh drift and events as well
      const [driftRes, eventsRes] = await Promise.all([
        fetchPersonalizationDrift(profileId, userId).catch(() => null),
        fetchGovernanceEvents(profileId, 10, 0, userId).catch(() => null),
      ]);
      if (driftRes) {
        setDriftSignals({
          drifting: driftRes.drifting_signals,
          stale: driftRes.stale_signals,
          stable: driftRes.stable_signals,
        });
      }
      if (eventsRes) {
        setGovernanceEvents(eventsRes.items);
      }
    } catch (err: unknown) {
      console.error("Failed to recompute governance evaluation:", err);
      setError(err instanceof Error ? err.message : "Failed to recompute governance");
    } finally {
      setIsRecomputing(false);
    }
  };

  const getHealthBadge = (state: PersonalizationHealthState) => {
    switch (state) {
      case "HEALTHY":
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 shadow-sm">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            Healthy
          </span>
        );
      case "STABLE":
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 shadow-sm">
            <span className="w-2 h-2 rounded-full bg-blue-500" />
            Stable
          </span>
        );
      case "DRIFTING":
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 shadow-sm">
            <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
            Behavioral Drift
          </span>
        );
      case "DEGRADED":
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20 shadow-sm">
            <span className="w-2 h-2 rounded-full bg-orange-500" />
            Degraded
          </span>
        );
      case "SUSPENDED":
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20 shadow-sm">
            <span className="w-2 h-2 rounded-full bg-rose-500" />
            Suspended
          </span>
        );
      case "INSUFFICIENT_DATA":
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-slate-500/10 text-slate-600 dark:text-slate-400 border border-slate-500/20 shadow-sm">
            <span className="w-2 h-2 rounded-full bg-slate-400" />
            Insufficient Data
          </span>
        );
    }
  };

  const getGateBadge = (gate: GovernanceGateState) => {
    switch (gate) {
      case "ALLOW":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
            <PlayCircle className="w-3.5 h-3.5" />
            ALLOW
          </span>
        );
      case "ALLOW_BOUNDED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-semibold bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-500/20">
            <ShieldCheck className="w-3.5 h-3.5" />
            ALLOW_BOUNDED
          </span>
        );
      case "HOLD":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            <PauseCircle className="w-3.5 h-3.5" />
            HOLD
          </span>
        );
      case "REDUCE":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-semibold bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
            <TrendingDown className="w-3.5 h-3.5" />
            REDUCE
          </span>
        );
      case "SUSPEND":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-semibold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20">
            <ShieldAlert className="w-3.5 h-3.5" />
            SUSPEND
          </span>
        );
    }
  };

  const getDriftTypeBadge = (type: DriftType) => {
    switch (type) {
      case "STABLE":
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
            Stable
          </span>
        );
      case "EMERGING":
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
            Emerging Drift
          </span>
        );
      case "PERSISTENT":
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300">
            Persistent Drift
          </span>
        );
      case "REVERSING":
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
            Reversing Drift
          </span>
        );
      case "UNKNOWN":
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400">
            Unknown
          </span>
        );
    }
  };

  const getEvidenceStrengthBadge = (strength: EvidenceStrength) => {
    switch (strength) {
      case "HIGH":
        return <span className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">High Evidence</span>;
      case "MEDIUM":
        return <span className="text-[11px] font-semibold text-blue-600 dark:text-blue-400">Medium Evidence</span>;
      case "LOW":
        return <span className="text-[11px] font-semibold text-amber-600 dark:text-amber-400">Low Evidence</span>;
      case "INSUFFICIENT":
      default:
        return <span className="text-[11px] font-semibold text-slate-500">Insufficient</span>;
    }
  };

  const evaluation = healthData?.evaluation;

  // Combine and filter drift items
  const allDriftItems: SignalDriftItem[] = [
    ...(driftSignals.drifting || []),
    ...(driftSignals.stale || []),
    ...(driftSignals.stable || []),
  ];

  const filteredSignals = allDriftItems.filter((item) => {
    if (signalFilter === "DRIFTING") return item.drift_type !== "STABLE" && item.drift_type !== "UNKNOWN";
    if (signalFilter === "STALE") return item.is_stale;
    if (signalFilter === "STABLE") return item.drift_type === "STABLE" && !item.is_stale;
    return true;
  });

  return (
    <div
      id="personalization-governance-card"
      className={`rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white/70 dark:bg-slate-900/70 backdrop-blur-md shadow-sm transition-all overflow-hidden ${className}`}
    >
      {/* Header Banner */}
      <div className="p-5 border-b border-slate-100 dark:border-slate-800/80 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 border border-indigo-200/60 dark:border-indigo-800/60">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                Personalization Governance & Drift Safety
              </h3>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
                Phase 5.8
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Deterministic behavioral drift monitoring, hysteresis protection & adaptation gating
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {healthData && getHealthBadge(healthData.overall_health_state)}
          <button
            id="recompute-governance-btn"
            onClick={handleRecompute}
            disabled={isRecomputing || isLoading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-700 transition-colors disabled:opacity-50"
            title="Recompute personalization governance & drift status"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRecomputing ? "animate-spin text-indigo-600" : ""}`} />
            <span>{isRecomputing ? "Evaluating..." : "Re-evaluate"}</span>
          </button>
        </div>
      </div>

      {/* Content Area */}
      <div className="p-5 space-y-6">
        {error && (
          <div className="p-3.5 rounded-lg bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/50 flex items-start gap-2.5 text-xs text-rose-700 dark:text-rose-400">
            <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <div>
              <p className="font-medium">Governance Evaluation Error</p>
              <p className="mt-0.5 opacity-90">{error}</p>
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="py-12 flex flex-col items-center justify-center gap-3 text-slate-400">
            <RefreshCw className="w-6 h-6 animate-spin text-indigo-500" />
            <p className="text-xs">Evaluating personalization health and behavioral drift...</p>
          </div>
        ) : !healthData ? (
          <div className="py-8 text-center text-xs text-slate-500 dark:text-slate-400">
            No governance records found. Personalization operates under standard baseline constraints.
          </div>
        ) : (
          <>
            {/* Top Stat Cards: Health, Gate, Adaptation */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
              {/* Overall Health State */}
              <div className="p-3.5 rounded-lg bg-slate-50/70 dark:bg-slate-800/40 border border-slate-200/60 dark:border-slate-800">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Personalization Health</span>
                  <Activity className="w-4 h-4 text-indigo-500" />
                </div>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-lg font-bold text-slate-900 dark:text-slate-100">
                    {healthData.overall_health_state}
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400 line-clamp-2">
                  {healthData.health_summary}
                </p>
              </div>

              {/* Governance Gate State */}
              <div className="p-3.5 rounded-lg bg-slate-50/70 dark:bg-slate-800/40 border border-slate-200/60 dark:border-slate-800">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Governance Gate</span>
                  <ShieldCheck className="w-4 h-4 text-sky-500" />
                </div>
                <div className="mt-2 flex items-baseline gap-2">
                  {getGateBadge(healthData.governance_state)}
                </div>
                <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400 line-clamp-2">
                  {healthData.governance_explanation}
                </p>
              </div>

              {/* Adaptation State */}
              <div className="p-3.5 rounded-lg bg-slate-50/70 dark:bg-slate-800/40 border border-slate-200/60 dark:border-slate-800">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Adaptation Mode</span>
                  <Zap className="w-4 h-4 text-amber-500" />
                </div>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-lg font-bold text-slate-900 dark:text-slate-100">
                    {healthData.adaptation_state}
                  </span>
                  <span className="text-xs text-slate-400">
                    ({healthData.drifting_signals_count} drifting, {healthData.stale_signals_count} stale)
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                  {healthData.adaptation_state === "SUSPENDED"
                    ? "Modifiers neutral (0.0). Core ranking remains authoritative."
                    : healthData.adaptation_state === "BOUNDED"
                    ? "Dampened 50% to prevent over-fitting to recent noise."
                    : "Active bounded contextual adaptation."}
                </p>
              </div>
            </div>

            {/* 8 Health Dimensions Matrix */}
            {evaluation && (
              <div className="p-4 rounded-lg bg-slate-50/50 dark:bg-slate-800/30 border border-slate-200/50 dark:border-slate-800/70">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-3 flex items-center gap-1.5">
                  <Scale className="w-3.5 h-3.5 text-indigo-500" />
                  Deterministic Health Dimensions
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div>
                    <span className="text-slate-400 text-[11px] block">Signal Freshness</span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200">
                      {evaluation.signal_freshness}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-[11px] block">Evidence Sufficiency</span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200">
                      {evaluation.evidence_sufficiency}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-[11px] block">Quality Stability</span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200">
                      {evaluation.quality_stability}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-[11px] block">Context Stability</span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200">
                      {evaluation.context_stability}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-[11px] block">Preference Alignment</span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200">
                      {evaluation.preference_alignment}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-[11px] block">Recommendation Diversity</span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200">
                      {evaluation.recommendation_diversity}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-[11px] block">Drift Status</span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200">
                      {evaluation.drifting_signals_count > 0 ? "DRIFT_DETECTED" : "STABLE"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-[11px] block">Windows (Hist / Recent)</span>
                    <span className="font-mono text-slate-800 dark:text-slate-200">
                      {evaluation.historical_window_days}d / {evaluation.recent_window_days}d
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Navigation Tabs: Behavioral Signals vs Audit Trail */}
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-2">
              <div className="flex items-center gap-2">
                <button
                  id="tab-signals"
                  onClick={() => setActiveTab("SIGNALS")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 ${
                    activeTab === "SIGNALS"
                      ? "bg-indigo-50 dark:bg-indigo-950/50 text-indigo-600 dark:text-indigo-400 border border-indigo-200/60 dark:border-indigo-800/60"
                      : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                  }`}
                >
                  <Activity className="w-3.5 h-3.5" />
                  Behavioral Signal Drift ({allDriftItems.length})
                </button>
                <button
                  id="tab-audit"
                  onClick={() => setActiveTab("AUDIT")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 ${
                    activeTab === "AUDIT"
                      ? "bg-indigo-50 dark:bg-indigo-950/50 text-indigo-600 dark:text-indigo-400 border border-indigo-200/60 dark:border-indigo-800/60"
                      : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                  }`}
                >
                  <History className="w-3.5 h-3.5" />
                  Governance Audit Trail ({governanceEvents.length})
                </button>
              </div>

              {activeTab === "SIGNALS" && (
                <div className="flex items-center gap-1 text-xs">
                  <span className="text-slate-400 text-[11px] mr-1">Filter:</span>
                  {(["ALL", "DRIFTING", "STALE", "STABLE"] as const).map((filter) => (
                    <button
                      key={filter}
                      onClick={() => setSignalFilter(filter)}
                      className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                        signalFilter === filter
                          ? "bg-slate-200 dark:bg-slate-700 text-slate-900 dark:text-slate-100"
                          : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                      }`}
                    >
                      {filter}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* TAB 1: Behavioral Signal Drift Breakdown */}
            {activeTab === "SIGNALS" && (
              <div className="space-y-3">
                {filteredSignals.length === 0 ? (
                  <div className="py-8 text-center text-xs text-slate-500 dark:text-slate-400">
                    No signals found matching filter &ldquo;{signalFilter}&rdquo;.
                  </div>
                ) : (
                  filteredSignals.map((item, idx) => (
                    <div
                      key={`${item.dimension}-${item.signal_value}-${idx}`}
                      className="p-3.5 rounded-lg border border-slate-200/70 dark:border-slate-800 bg-white/50 dark:bg-slate-800/20 space-y-2 text-xs"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-900 dark:text-slate-100">
                            {item.signal_value}
                          </span>
                          <span className="text-[11px] px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400">
                            {item.dimension}
                          </span>
                          {item.is_stale && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                              STALE
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-2">
                          {getDriftTypeBadge(item.drift_type)}
                          {getEvidenceStrengthBadge(item.evidence_strength)}
                        </div>
                      </div>

                      {/* Numerical Comparison */}
                      <div className="grid grid-cols-3 gap-2 py-1.5 px-2.5 rounded bg-slate-50 dark:bg-slate-800/40 text-[11px]">
                        <div>
                          <span className="text-slate-400 block">Historical Strength</span>
                          <span className="font-mono font-medium text-slate-700 dark:text-slate-300">
                            {item.historical_strength.toFixed(2)}
                          </span>
                        </div>
                        <div>
                          <span className="text-slate-400 block">Recent Strength</span>
                          <span className="font-mono font-medium text-slate-700 dark:text-slate-300">
                            {item.recent_strength.toFixed(2)}
                          </span>
                        </div>
                        <div>
                          <span className="text-slate-400 block">Difference</span>
                          <span
                            className={`font-mono font-semibold flex items-center gap-0.5 ${
                              item.difference > 0
                                ? "text-emerald-600 dark:text-emerald-400"
                                : item.difference < 0
                                ? "text-rose-600 dark:text-rose-400"
                                : "text-slate-500"
                            }`}
                          >
                            {item.difference > 0 ? (
                              <ArrowUpRight className="w-3 h-3" />
                            ) : item.difference < 0 ? (
                              <ArrowDownRight className="w-3 h-3" />
                            ) : null}
                            {item.difference >= 0 ? `+${item.difference.toFixed(2)}` : item.difference.toFixed(2)}
                          </span>
                        </div>
                      </div>

                      {/* Explanation */}
                      <p className="text-[11px] text-slate-500 dark:text-slate-400 italic">
                        &ldquo;{item.explanation}&rdquo;
                      </p>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* TAB 2: Governance Audit Trail */}
            {activeTab === "AUDIT" && (
              <div className="space-y-2.5">
                {governanceEvents.length === 0 ? (
                  <div className="py-8 text-center text-xs text-slate-500 dark:text-slate-400">
                    No governance audit events recorded yet.
                  </div>
                ) : (
                  governanceEvents.map((event) => (
                    <div
                      key={event.id}
                      className="p-3 rounded-lg border border-slate-200/60 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/20 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-800 dark:text-slate-200">
                            {event.event_type}
                          </span>
                          {event.previous_state && (
                            <span className="text-slate-400 font-mono text-[11px]">
                              {event.previous_state} &rarr; {event.new_state}
                            </span>
                          )}
                          {!event.previous_state && (
                            <span className="text-slate-400 font-mono text-[11px]">
                              &rarr; {event.new_state}
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-slate-500 dark:text-slate-400">
                          {event.reason}
                        </p>
                      </div>

                      <div className="text-right flex-shrink-0 text-[10px] text-slate-400 font-mono">
                        {new Date(event.reference_time || event.created_at).toLocaleString()}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Invariant & Governance Notice */}
            <div className="p-3.5 rounded-lg bg-indigo-50/60 dark:bg-indigo-950/20 border border-indigo-100 dark:border-indigo-900/40 flex items-start gap-2.5 text-xs text-indigo-800 dark:text-indigo-300">
              <Lock className="w-4 h-4 mt-0.5 flex-shrink-0 text-indigo-600 dark:text-indigo-400" />
              <div className="space-y-0.5">
                <p className="font-semibold">Explicit Preference & Relevance Dominance Guaranteed</p>
                <p className="text-[11px] leading-relaxed opacity-90">
                  Behavioral drift detection operates under strict hierarchy: explicit exclusions and preferences are never overridden by behavioral changes. Suspended personalization reverts modifiers to neutral (0.0) without disrupting core ranking guarantees.
                </p>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
