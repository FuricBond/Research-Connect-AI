"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  History,
  Info,
  Loader2,
  Lock,
  RefreshCw,
  RotateCcw,
  Settings,
  Shield,
  ShieldCheck,
  Sliders,
  Sparkles,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";
import {
  fetchPersonalizationSettings,
  updatePersonalizationSettings,
  resetPersonalization,
  fetchPersonalizationControlHistory,
} from "../../services/api";
import type {
  PersonalizationControlEvent,
  PersonalizationResetResponse,
  ResearcherPersonalizationSettings,
} from "../../types/personalization";

interface PersonalizationSettingsCardProps {
  profileId: string;
  userId?: string;
  className?: string;
}

export const PersonalizationSettingsCard: React.FC<PersonalizationSettingsCardProps> = ({
  profileId,
  userId,
  className = "",
}) => {
  const [settings, setSettings] = useState<ResearcherPersonalizationSettings | null>(null);
  const [controlEvents, setControlEvents] = useState<PersonalizationControlEvent[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isUpdating, setIsUpdating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Reset modal state
  const [isResetModalOpen, setIsResetModalOpen] = useState<boolean>(false);
  const [resetReason, setResetReason] = useState<string>("");
  const [isResetting, setIsResetting] = useState<boolean>(false);
  const [resetResult, setResetResult] = useState<PersonalizationResetResponse | null>(null);

  // Audit history expansion
  const [isHistoryExpanded, setIsHistoryExpanded] = useState<boolean>(false);

  const loadData = useCallback(async () => {
    if (!profileId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [settingsRes, historyRes] = await Promise.all([
        fetchPersonalizationSettings(profileId, userId),
        fetchPersonalizationControlHistory(profileId, 10, 0, userId),
      ]);
      setSettings(settingsRes);
      setControlEvents(historyRes.events || []);
    } catch (err: any) {
      setError(err?.detail || err?.message || "Failed to load personalization settings.");
    } finally {
      setIsLoading(false);
    }
  }, [profileId, userId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleToggle = async (key: "personalization_enabled" | "adaptive_signals_enabled" | "feedback_learning_enabled") => {
    if (!settings || isUpdating) return;
    setIsUpdating(true);
    setError(null);
    setSuccessMessage(null);

    const newValue = !settings[key];
    const payload = { [key]: newValue };

    try {
      const updated = await updatePersonalizationSettings(profileId, payload, userId);
      setSettings(updated);
      setSuccessMessage(
        key === "personalization_enabled"
          ? `Personalization ${newValue ? "enabled" : "disabled"}.`
          : key === "adaptive_signals_enabled"
          ? `Adaptive signals ${newValue ? "enabled" : "disabled"}.`
          : `Feedback learning ${newValue ? "enabled" : "disabled"}.`
      );
      // Reload control history
      const historyRes = await fetchPersonalizationControlHistory(profileId, 10, 0, userId);
      setControlEvents(historyRes.events || []);
    } catch (err: any) {
      setError(err?.detail || err?.message || "Failed to update personalization setting.");
    } finally {
      setIsUpdating(false);
    }
  };

  const handleReset = async () => {
    if (isResetting) return;
    setIsResetting(true);
    setError(null);
    try {
      const res = await resetPersonalization(profileId, resetReason || "User reset request", userId);
      setResetResult(res);
      setIsResetModalOpen(false);
      setResetReason("");
      setSuccessMessage(res.message);
      await loadData();
    } catch (err: any) {
      setError(err?.detail || err?.message || "Failed to reset personalization.");
    } finally {
      setIsResetting(false);
    }
  };

  const formatEventType = (type: string) => {
    switch (type) {
      case "PERSONALIZATION_ENABLED":
        return { label: "Personalization Enabled", color: "text-emerald-600 dark:text-emerald-400" };
      case "PERSONALIZATION_DISABLED":
        return { label: "Personalization Disabled", color: "text-amber-600 dark:text-amber-400" };
      case "ADAPTIVE_SIGNALS_ENABLED":
        return { label: "Adaptive Signals Enabled", color: "text-blue-600 dark:text-blue-400" };
      case "ADAPTIVE_SIGNALS_DISABLED":
        return { label: "Adaptive Signals Disabled", color: "text-gray-600 dark:text-gray-400" };
      case "FEEDBACK_LEARNING_ENABLED":
        return { label: "Feedback Learning Enabled", color: "text-indigo-600 dark:text-indigo-400" };
      case "FEEDBACK_LEARNING_DISABLED":
        return { label: "Feedback Learning Disabled", color: "text-gray-600 dark:text-gray-400" };
      case "PERSONALIZATION_RESET":
        return { label: "Personalization Reset", color: "text-purple-600 dark:text-purple-400" };
      default:
        return { label: type, color: "text-gray-600 dark:text-gray-400" };
    }
  };

  return (
    <div
      className={`bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 space-y-6 ${className}`}
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-gray-200 dark:border-gray-800">
        <div>
          <div className="flex items-center gap-2.5">
            <Sliders className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            <h2 className="text-lg font-bold text-gray-900 dark:text-white">
              Personalization Controls & Transparency
            </h2>
            {settings && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800">
                State v{settings.personalization_state_version}
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Safely control how your preferences and behavioral signals influence opportunity ranking.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            disabled={isLoading}
            className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            title="Refresh settings"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <div className="p-3 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-lg text-rose-800 dark:text-rose-200 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {successMessage && (
        <div className="p-3 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-lg text-emerald-800 dark:text-emerald-200 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}

      {isLoading && !settings ? (
        <div className="py-12 flex flex-col items-center justify-center text-gray-400 text-xs gap-2">
          <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
          <span>Loading personalization controls...</span>
        </div>
      ) : settings ? (
        <>
          {/* Controls Toggles */}
          <div className="space-y-4">
            {/* 1. Master Personalization Toggle */}
            <div className="flex items-center justify-between p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/30">
              <div className="space-y-0.5 max-w-md">
                <div className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                  <span>Personalization</span>
                  {settings.personalization_enabled ? (
                    <span className="text-[10px] uppercase font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/50 px-1.5 py-0.5 rounded border border-emerald-200 dark:border-emerald-800">
                      Active
                    </span>
                  ) : (
                    <span className="text-[10px] uppercase font-bold text-gray-500 bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded border border-gray-200 dark:border-gray-700">
                      Disabled
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  When enabled, recommendations are personalized using explicit preferences and bounded behavioral signals.
                  When disabled, only core relevance is used (explicit exclusions still apply).
                </p>
              </div>

              <button
                onClick={() => handleToggle("personalization_enabled")}
                disabled={isUpdating}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  settings.personalization_enabled
                    ? "bg-indigo-600"
                    : "bg-gray-200 dark:bg-gray-700"
                }`}
                role="switch"
                aria-checked={settings.personalization_enabled}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                    settings.personalization_enabled ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>

            {/* 2. Adaptive Signals Toggle */}
            <div className="flex items-center justify-between p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/30">
              <div className="space-y-0.5 max-w-md">
                <div className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                  <span>Adaptive Behavioral Learning</span>
                  {settings.adaptive_signals_enabled ? (
                    <span className="text-[10px] uppercase font-bold text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/50 px-1.5 py-0.5 rounded border border-blue-200 dark:border-blue-800">
                      Active
                    </span>
                  ) : (
                    <span className="text-[10px] uppercase font-bold text-gray-500 bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded border border-gray-200 dark:border-gray-700">
                      Disabled
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Allow aggregated, bounded behavioral signals (e.g. conference interest, grant affinity) to fine-tune rankings.
                  When disabled, only your explicit preferences are used.
                </p>
              </div>

              <button
                onClick={() => handleToggle("adaptive_signals_enabled")}
                disabled={isUpdating || !settings.personalization_enabled}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  settings.adaptive_signals_enabled && settings.personalization_enabled
                    ? "bg-indigo-600"
                    : "bg-gray-200 dark:bg-gray-700 opacity-60"
                }`}
                role="switch"
                aria-checked={settings.adaptive_signals_enabled}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                    settings.adaptive_signals_enabled && settings.personalization_enabled
                      ? "translate-x-5"
                      : "translate-x-0"
                  }`}
                />
              </button>
            </div>

            {/* 3. Feedback Learning Toggle */}
            <div className="flex items-center justify-between p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/30">
              <div className="space-y-0.5 max-w-md">
                <div className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                  <span>Feedback Learning from Future Interactions</span>
                  {settings.feedback_learning_enabled ? (
                    <span className="text-[10px] uppercase font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/50 px-1.5 py-0.5 rounded border border-emerald-200 dark:border-emerald-800">
                      Enabled
                    </span>
                  ) : (
                    <span className="text-[10px] uppercase font-bold text-gray-500 bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded border border-gray-200 dark:border-gray-700">
                      Paused
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Allow future saves, dismissals, and clicks to update your adaptive signals.
                  When paused, historical signals remain frozen and new interactions are not used for learning.
                </p>
              </div>

              <button
                onClick={() => handleToggle("feedback_learning_enabled")}
                disabled={isUpdating}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  settings.feedback_learning_enabled
                    ? "bg-indigo-600"
                    : "bg-gray-200 dark:bg-gray-700"
                }`}
                role="switch"
                aria-checked={settings.feedback_learning_enabled}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                    settings.feedback_learning_enabled ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Reset Action & Invariants Card */}
          <div className="p-4 rounded-lg border border-purple-200 dark:border-purple-900/50 bg-purple-50/40 dark:bg-purple-950/20 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1 max-w-lg">
              <div className="text-sm font-semibold text-purple-900 dark:text-purple-200 flex items-center gap-1.5">
                <RotateCcw className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                <span>Reset Personalization State</span>
              </div>
              <p className="text-xs text-purple-700/80 dark:text-purple-300">
                Safely clears derived behavioral signals, calibrations, and contextual modifiers.
                Your <strong>explicit preferences</strong>, <strong>profile</strong>, and <strong>account</strong> are
                strictly preserved.
              </p>
            </div>

            <button
              onClick={() => setIsResetModalOpen(true)}
              className="px-3.5 py-2 text-xs font-semibold text-purple-700 dark:text-purple-200 bg-white dark:bg-gray-800 border border-purple-300 dark:border-purple-700 hover:bg-purple-50 dark:hover:bg-purple-900/30 rounded-lg shadow-sm transition-colors whitespace-nowrap"
            >
              Reset Personalization
            </button>
          </div>

          {/* Academic Invariant Box */}
          <div className="p-3 bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-lg text-xs text-slate-600 dark:text-slate-400 flex items-start gap-2.5">
            <ShieldCheck className="w-4 h-4 text-indigo-600 dark:text-indigo-400 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold text-slate-800 dark:text-slate-200">
                Guaranteed Precedence Hierarchy:
              </span>{" "}
              System Safety Constraints &gt; Eligibility &gt; Core Relevance (&ge; 85%) &gt; Explicit Preferences &gt;
              Researcher Controls &gt; Adaptive Signals (&plusmn; 10%) &gt; Calibration (&plusmn; 5%) &gt; Contextual (&plusmn; 3%).
            </div>
          </div>

          {/* Audit / Control History Section */}
          <div className="pt-2 border-t border-gray-200 dark:border-gray-800">
            <button
              onClick={() => setIsHistoryExpanded(!isHistoryExpanded)}
              className="w-full flex items-center justify-between text-xs font-semibold text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white py-1"
            >
              <span className="flex items-center gap-1.5">
                <History className="w-4 h-4 text-indigo-500" />
                Personalization Control History &amp; Audit Log ({controlEvents.length})
              </span>
              {isHistoryExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {isHistoryExpanded && (
              <div className="mt-3 space-y-2">
                {controlEvents.length === 0 ? (
                  <p className="text-xs text-gray-400 italic py-2">No control events recorded yet.</p>
                ) : (
                  <div className="divide-y divide-gray-100 dark:divide-gray-800/60 max-h-60 overflow-y-auto">
                    {controlEvents.map((ev) => {
                      const badge = formatEventType(ev.event_type);
                      return (
                        <div key={ev.id} className="py-2.5 flex items-start justify-between text-xs">
                          <div className="space-y-0.5">
                            <span className={`font-semibold ${badge.color}`}>{badge.label}</span>
                            {ev.trigger_reason && (
                              <p className="text-gray-500 dark:text-gray-400">{ev.trigger_reason}</p>
                            )}
                          </div>
                          <div className="text-right text-[11px] text-gray-400 shrink-0">
                            <p>{new Date(ev.created_at).toLocaleDateString()}</p>
                            <p>{new Date(ev.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      ) : null}

      {/* Confirmation Modal for Reset */}
      {isResetModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative w-full max-w-md bg-white dark:bg-gray-900 rounded-xl shadow-2xl border border-gray-200 dark:border-gray-800 p-6 space-y-4 text-gray-900 dark:text-gray-100">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-purple-100 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400 rounded-lg">
                <RotateCcw className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-gray-900 dark:text-white">
                  Reset Derived Personalization?
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  This will neutralize learned adaptive signals, calibrations, and contextual modifiers.
                </p>
              </div>
            </div>

            <div className="p-3 bg-gray-50 dark:bg-gray-800/60 rounded-lg border border-gray-200 dark:border-gray-700/60 text-xs space-y-1.5">
              <div className="font-semibold text-gray-700 dark:text-gray-300">Strict Guarantees:</div>
              <ul className="text-gray-600 dark:text-gray-400 space-y-0.5 list-disc list-inside">
                <li>Your explicit preferences are <strong>NOT deleted</strong></li>
                <li>Your researcher profile is <strong>NOT changed</strong></li>
                <li>Your user account and history are <strong>preserved</strong></li>
                <li>State version will increment from v{settings?.personalization_state_version} to v{(settings?.personalization_state_version ?? 1) + 1}</li>
              </ul>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                Reason for Reset (Optional):
              </label>
              <input
                type="text"
                value={resetReason}
                onChange={(e) => setResetReason(e.target.value)}
                placeholder="e.g. Switched research focus, reset recommendations"
                className="w-full px-3 py-2 text-xs border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setIsResetModalOpen(false)}
                disabled={isResetting}
                className="px-3.5 py-2 text-xs font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleReset}
                disabled={isResetting}
                className="px-3.5 py-2 text-xs font-semibold text-white bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors flex items-center gap-1.5"
              >
                {isResetting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Confirm Reset
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
