"use client";

import React, { useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  BookOpen,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Cpu,
  Eye,
  Filter,
  Globe,
  Info,
  Layers,
  MapPin,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Tag,
} from "lucide-react";
import type {
  CandidateSourceType,
  PersonalizedCandidateItem,
  PersonalizedCandidateSetResponse,
} from "../../types/researcher";

interface PersonalizedCandidatePreviewProps {
  candidatesResponse: PersonalizedCandidateSetResponse | null;
  loading: boolean;
  error: string | null;
  onRefresh: (options?: {
    limit?: number;
    includeInferred?: boolean;
    includeExpertise?: boolean;
    includeFallback?: boolean;
  }) => void;
  isRefreshing: boolean;
}

export function PersonalizedCandidatePreview({
  candidatesResponse,
  loading,
  error,
  onRefresh,
  isRefreshing,
}: PersonalizedCandidatePreviewProps) {
  const [expandedCandidates, setExpandedCandidates] = useState<Record<string, boolean>>({});
  const [selectedLimit, setSelectedLimit] = useState<number>(50);
  const [includeInferred, setIncludeInferred] = useState<boolean>(true);
  const [includeExpertise, setIncludeExpertise] = useState<boolean>(true);
  const [includeFallback, setIncludeFallback] = useState<boolean>(true);

  const toggleExpand = (candidateId: string) => {
    setExpandedCandidates((prev) => ({
      ...prev,
      [candidateId]: !prev[candidateId],
    }));
  };

  const handleApplyFilters = () => {
    onRefresh({
      limit: selectedLimit,
      includeInferred,
      includeExpertise,
      includeFallback,
    });
  };

  const getSourceBadge = (source: CandidateSourceType) => {
    switch (source) {
      case "EXPLICIT_PREFERENCE":
        return {
          label: "Explicit Preference",
          bg: "bg-blue-900/40 text-blue-300 border-blue-700/50",
          icon: <Sparkles className="w-3 h-3" />,
        };
      case "INFERRED_PREFERENCE":
        return {
          label: "Inferred Preference",
          bg: "bg-indigo-900/40 text-indigo-300 border-indigo-700/50",
          icon: <Eye className="w-3 h-3" />,
        };
      case "RESEARCH_EXPERTISE":
        return {
          label: "Scholarly Expertise",
          bg: "bg-purple-900/40 text-purple-300 border-purple-700/50",
          icon: <BookOpen className="w-3 h-3" />,
        };
      case "RESEARCH_INTEREST":
        return {
          label: "Emerging Interest",
          bg: "bg-teal-900/40 text-teal-300 border-teal-700/50",
          icon: <Cpu className="w-3 h-3" />,
        };
      case "PROFILE_KEYWORD":
        return {
          label: "Profile Keyword",
          bg: "bg-amber-900/40 text-amber-300 border-amber-700/50",
          icon: <Tag className="w-3 h-3" />,
        };
      case "COLD_START_FALLBACK":
        return {
          label: "Discovery Fallback",
          bg: "bg-slate-800 text-slate-300 border-slate-700",
          icon: <Globe className="w-3 h-3" />,
        };
      default:
        return {
          label: source,
          bg: "bg-slate-800 text-slate-300 border-slate-700",
          icon: <Layers className="w-3 h-3" />,
        };
    }
  };

  const getUrgencyBadge = (urgencyTier?: string | null, daysRemaining?: number | null) => {
    if (!urgencyTier || urgencyTier === "UNKNOWN" || urgencyTier === "NONE") {
      return null;
    }
    const daysStr =
      daysRemaining !== null && daysRemaining !== undefined
        ? ` (${daysRemaining > 0 ? Math.round(daysRemaining) : 0}d left)`
        : "";

    switch (urgencyTier) {
      case "CRITICAL":
      case "DUE_TODAY":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-950/80 text-red-300 border border-red-800">
            <AlertTriangle className="w-3 h-3" />
            {urgencyTier}
            {daysStr}
          </span>
        );
      case "URGENT":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-950/80 text-amber-300 border border-amber-800">
            <AlertCircle className="w-3 h-3" />
            {urgencyTier}
            {daysStr}
          </span>
        );
      case "APPROACHING":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-yellow-950/80 text-yellow-300 border border-yellow-800">
            <Calendar className="w-3 h-3" />
            {urgencyTier}
            {daysStr}
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-slate-800 text-slate-300 border border-slate-700">
            <Calendar className="w-3 h-3" />
            {urgencyTier}
            {daysStr}
          </span>
        );
    }
  };

  const getRiskBadge = (
    riskLevel?: string | null,
    isPredatory?: boolean,
    riskScore?: number | null
  ) => {
    if (isPredatory || riskLevel === "HIGH_RISK") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-950/80 text-red-300 border border-red-800">
          <ShieldAlert className="w-3 h-3 text-red-400" />
          High Risk {riskScore !== null && riskScore !== undefined ? `(${riskScore.toFixed(2)})` : ""}
        </span>
      );
    }
    if (riskLevel === "MODERATE_RISK") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-950/80 text-amber-300 border border-amber-800">
          <AlertCircle className="w-3 h-3 text-amber-400" />
          Moderate Risk
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-emerald-950/80 text-emerald-300 border border-emerald-800">
        <ShieldCheck className="w-3 h-3 text-emerald-400" />
        Low Risk
      </span>
    );
  };

  return (
    <div className="space-y-6">
      {/* ── Strict Phase Boundary Banner ─────────────────────────────────── */}
      <div className="bg-slate-900 border border-indigo-500/30 rounded-xl p-5 shadow-lg relative overflow-hidden">
        <div className="absolute top-0 right-0 w-72 h-72 bg-indigo-600/10 rounded-full blur-3xl pointer-events-none" />
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-bold tracking-wide uppercase bg-indigo-500/20 text-indigo-300 border border-indigo-500/40">
                Phase 3.4
              </span>
              <h2 className="text-xl font-bold text-white tracking-tight">
                Personalized Candidate Preview
              </h2>
            </div>
            <p className="text-sm text-slate-300 max-w-2xl">
              Generates the initial candidate pool matching canonical profiles, Phase 3.2 scholarly expertise,
              and Phase 3.3 personal preferences.{" "}
              <strong className="text-indigo-300">
                Strict boundary: Unranked candidate set. Personalized ranking will be introduced in Phase 3.5.
              </strong>
            </p>
          </div>

          <button
            onClick={() => handleApplyFilters()}
            disabled={loading || isRefreshing}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800/50 text-white rounded-lg font-medium text-sm transition shadow-sm self-start md:self-auto"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? "animate-spin" : ""}`} />
            Refresh Candidate Set
          </button>
        </div>
      </div>

      {/* ── Controls & Filter Bar ────────────────────────────────────────── */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <span className="text-slate-400 font-medium">Source Channels:</span>
          </div>

          <label className="flex items-center gap-1.5 cursor-pointer text-slate-300">
            <input
              type="checkbox"
              checked={includeInferred}
              onChange={(e) => setIncludeInferred(e.target.checked)}
              className="rounded bg-slate-800 border-slate-700 text-indigo-600 focus:ring-indigo-500"
            />
            <span>Inferred Preferences</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer text-slate-300">
            <input
              type="checkbox"
              checked={includeExpertise}
              onChange={(e) => setIncludeExpertise(e.target.checked)}
              className="rounded bg-slate-800 border-slate-700 text-indigo-600 focus:ring-indigo-500"
            />
            <span>Scholarly Expertise</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer text-slate-300">
            <input
              type="checkbox"
              checked={includeFallback}
              onChange={(e) => setIncludeFallback(e.target.checked)}
              className="rounded bg-slate-800 border-slate-700 text-indigo-600 focus:ring-indigo-500"
            />
            <span>Discovery Fallback</span>
          </label>

          <div className="flex items-center gap-2 ml-2">
            <span className="text-slate-400 font-medium">Limit:</span>
            <select
              value={selectedLimit}
              onChange={(e) => setSelectedLimit(Number(e.target.value))}
              className="bg-slate-800 border border-slate-700 text-slate-200 rounded px-2.5 py-1 text-xs focus:ring-indigo-500"
            >
              <option value={10}>10 candidates</option>
              <option value={25}>25 candidates</option>
              <option value={50}>50 candidates</option>
              <option value={100}>100 candidates</option>
            </select>
          </div>
        </div>

        <button
          onClick={handleApplyFilters}
          disabled={loading || isRefreshing}
          className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 rounded-lg text-xs font-medium transition"
        >
          Apply Filters
        </button>
      </div>

      {/* ── Diagnostic Coverage Summary ──────────────────────────────────── */}
      {candidatesResponse && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
          <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-3 text-center">
            <div className="text-xl font-bold text-white">
              {candidatesResponse.candidate_count}
            </div>
            <div className="text-xs text-slate-400 mt-0.5">Total Candidates</div>
          </div>
          <div className="bg-slate-900/90 border border-blue-900/40 rounded-xl p-3 text-center">
            <div className="text-xl font-bold text-blue-400">
              {candidatesResponse.coverage.explicit_preference_count}
            </div>
            <div className="text-xs text-slate-400 mt-0.5">Explicit Match</div>
          </div>
          <div className="bg-slate-900/90 border border-indigo-900/40 rounded-xl p-3 text-center">
            <div className="text-xl font-bold text-indigo-400">
              {candidatesResponse.coverage.inferred_preference_count}
            </div>
            <div className="text-xs text-slate-400 mt-0.5">Inferred Match</div>
          </div>
          <div className="bg-slate-900/90 border border-purple-900/40 rounded-xl p-3 text-center">
            <div className="text-xl font-bold text-purple-400">
              {candidatesResponse.coverage.expertise_count}
            </div>
            <div className="text-xs text-slate-400 mt-0.5">Expertise Match</div>
          </div>
          <div className="bg-slate-900/90 border border-amber-900/40 rounded-xl p-3 text-center">
            <div className="text-xl font-bold text-amber-400">
              {candidatesResponse.coverage.profile_count}
            </div>
            <div className="text-xs text-slate-400 mt-0.5">Profile Match</div>
          </div>
          <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-3 text-center">
            <div className="text-xl font-bold text-slate-400">
              {candidatesResponse.coverage.fallback_count}
            </div>
            <div className="text-xs text-slate-400 mt-0.5">Fallback Match</div>
          </div>
        </div>
      )}

      {/* ── Cold Start Indicator ─────────────────────────────────────────── */}
      {candidatesResponse?.is_cold_start && (
        <div className="bg-amber-950/40 border border-amber-800/60 rounded-xl p-4 text-amber-200 text-sm flex items-start gap-3">
          <Info className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          <div>
            <strong className="font-semibold text-amber-300">Cold Start Active:</strong> This
            researcher has sparse preferences and publications. Candidates have been safely generated
            using discovery fallbacks and platform defaults without empty-state failure.
          </div>
        </div>
      )}

      {/* ── Error State ──────────────────────────────────────────────────── */}
      {error && (
        <div className="bg-red-950/40 border border-red-800/60 rounded-xl p-4 text-red-200 text-sm flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* ── Candidate List ───────────────────────────────────────────────── */}
      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-32 bg-slate-900/60 border border-slate-800 rounded-xl animate-pulse"
            />
          ))}
        </div>
      ) : candidatesResponse?.candidates.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center">
          <Layers className="w-10 h-10 text-slate-500 mx-auto mb-3" />
          <h3 className="text-lg font-medium text-slate-300">No Candidates Found</h3>
          <p className="text-sm text-slate-500 mt-1 max-w-md mx-auto">
            Try enabling Discovery Fallback or declaring additional topics/preferences to expand the
            candidate pool.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {candidatesResponse?.candidates.map((item: PersonalizedCandidateItem) => {
            const opp = item.opportunity;
            const prov = item.provenance;
            const isExpanded = expandedCandidates[item.candidate_id] ?? false;

            return (
              <div
                key={item.candidate_id}
                className="bg-slate-900/90 border border-slate-800 hover:border-slate-700 rounded-xl p-5 transition shadow-sm space-y-3"
              >
                {/* Header row */}
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="px-2 py-0.5 text-xs font-semibold rounded bg-slate-800 text-slate-300 border border-slate-700">
                        {opp.opportunity_type}
                      </span>
                      <span className="px-2 py-0.5 text-xs rounded bg-slate-800/80 text-slate-400">
                        {opp.delivery_mode}
                      </span>
                      {getUrgencyBadge(opp.urgency_tier, opp.days_remaining)}
                      {getRiskBadge(opp.risk_level, opp.is_predatory_flag, opp.risk_score)}
                    </div>
                    <h3 className="text-base font-semibold text-white group-hover:text-indigo-300">
                      {opp.title}
                    </h3>
                  </div>

                  <div className="flex items-center gap-2 self-start">
                    <button
                      onClick={() => toggleExpand(item.candidate_id)}
                      className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-300 transition"
                    >
                      {isExpanded ? (
                        <>
                          <ChevronUp className="w-3.5 h-3.5" />
                          Hide Provenance
                        </>
                      ) : (
                        <>
                          <ChevronDown className="w-3.5 h-3.5" />
                          Why Included? ({prov.sources.length})
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {/* Metadata tags */}
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-400 pt-1">
                  {opp.location && (
                    <div className="flex items-center gap-1">
                      <MapPin className="w-3.5 h-3.5 text-slate-500" />
                      <span>{opp.location}</span>
                    </div>
                  )}
                  {opp.organizer && (
                    <div className="flex items-center gap-1">
                      <BookOpen className="w-3.5 h-3.5 text-slate-500" />
                      <span>{opp.organizer}</span>
                    </div>
                  )}
                  {opp.submission_deadline && (
                    <div className="flex items-center gap-1">
                      <Calendar className="w-3.5 h-3.5 text-slate-500" />
                      <span>
                        Deadline:{" "}
                        {new Date(opp.submission_deadline).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                        })}
                      </span>
                    </div>
                  )}
                  <div className="flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                    <span>Eligibility: {opp.status}</span>
                  </div>
                </div>

                {/* Candidate Source Badges */}
                <div className="flex flex-wrap items-center gap-1.5 pt-1">
                  <span className="text-xs text-slate-500 mr-1">Sources:</span>
                  {prov.sources.map((src) => {
                    const badge = getSourceBadge(src);
                    return (
                      <span
                        key={src}
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border ${badge.bg}`}
                      >
                        {badge.icon}
                        {badge.label}
                      </span>
                    );
                  })}
                </div>

                {/* Collapsible Provenance Details */}
                {isExpanded && (
                  <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-4 mt-3 space-y-3 text-xs">
                    <div>
                      <h4 className="font-semibold text-slate-300 mb-1 flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                        Provenance Rationale:
                      </h4>
                      <ul className="list-disc list-inside space-y-1 text-slate-400 pl-1">
                        {prov.reasons.map((reason, idx) => (
                          <li key={idx}>{reason}</li>
                        ))}
                      </ul>
                    </div>

                    {prov.matched_topics.length > 0 && (
                      <div>
                        <span className="font-semibold text-slate-300">Matched Topics: </span>
                        <span className="text-indigo-300">
                          {prov.matched_topics.join(", ")}
                        </span>
                      </div>
                    )}

                    {prov.matched_preferences.length > 0 && (
                      <div>
                        <span className="font-semibold text-slate-300">Matched Preferences: </span>
                        <span className="text-blue-300">
                          {prov.matched_preferences.join(", ")}
                        </span>
                      </div>
                    )}

                    {prov.matched_expertise.length > 0 && (
                      <div>
                        <span className="font-semibold text-slate-300">Matched Expertise: </span>
                        <span className="text-purple-300">
                          {prov.matched_expertise.join(", ")}
                        </span>
                      </div>
                    )}

                    {opp.risk_reasons && opp.risk_reasons.length > 0 && (
                      <div className="pt-1 border-t border-slate-800">
                        <span className="font-semibold text-slate-300">Phase 2.6 Risk Assessment: </span>
                        <span className="text-slate-400">
                          {opp.risk_reasons.join("; ")}
                        </span>
                      </div>
                    )}

                    {opp.deadline_explanation && (
                      <div className="pt-1 border-t border-slate-800">
                        <span className="font-semibold text-slate-300">Phase 2.7 Deadline Timing: </span>
                        <span className="text-slate-400">{opp.deadline_explanation}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
