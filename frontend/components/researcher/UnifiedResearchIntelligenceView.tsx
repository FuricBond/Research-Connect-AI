"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Award,
  Bookmark,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Compass,
  ExternalLink,
  Eye,
  FileCheck,
  Filter,
  Info,
  Layers,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Tag,
  UserCheck,
  Users,
  Zap,
} from "lucide-react";
import {
  fetchBatchOpportunityPersonalization,
  fetchBatchOpportunityPreferenceMatches,
  getOpportunityIntelligence,
  getUnifiedRecommendations,
  getUnifiedResearchIntelligence,
} from "../../services/api";
import { PreferenceMatchBadge } from "../personalization/PreferenceMatchBadge";
import { PersonalizationScoreBadge } from "../personalization/PersonalizationScoreBadge";
import type {
  EvidenceTierBreakdown,
  ResearchIntelligenceSignal,
  UnifiedOpportunityIntelligence,
  UnifiedRecommendationItem,
  UnifiedRecommendationResponse,
  UnifiedResearcherContext,
} from "../../types/research_intelligence";
import type {
  PersonalizationAssessment,
  PreferencePersonalizationAssessment,
} from "../../types/personalization";

interface UnifiedResearchIntelligenceViewProps {
  profileId: string;
  userId?: string;
  onSelectOpportunity?: (opportunityId: string) => void;
  onNavigateToWorkspace?: (savedId?: string) => void;
}

export const UnifiedResearchIntelligenceView: React.FC<UnifiedResearchIntelligenceViewProps> = ({
  profileId,
  userId,
  onSelectOpportunity,
  onNavigateToWorkspace,
}) => {
  // Context State
  const [context, setContext] = useState<UnifiedResearcherContext | null>(null);
  const [contextLoading, setContextLoading] = useState<boolean>(true);
  const [contextError, setContextError] = useState<string | null>(null);

  // Recommendations State
  const [recsData, setRecsData] = useState<UnifiedRecommendationResponse | null>(null);
  const [recsLoading, setRecsLoading] = useState<boolean>(true);
  const [recsError, setRecsError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [preferenceMatches, setPreferenceMatches] = useState<Record<string, PreferencePersonalizationAssessment>>({});
  const [personalizationScores, setPersonalizationScores] = useState<Record<string, PersonalizationAssessment>>({});

  // Detailed Intelligence Modal/Drawer State
  const [selectedIntel, setSelectedIntel] = useState<UnifiedOpportunityIntelligence | null>(null);
  const [intelLoading, setIntelLoading] = useState<boolean>(false);
  const [expandedTiers, setExpandedTiers] = useState<Record<string, boolean>>({});
  const [activeSignalFilter, setActiveSignalFilter] = useState<string>("ALL");

  // Load Researcher Context
  const loadContext = useCallback(async () => {
    if (!profileId) return;
    setContextLoading(true);
    setContextError(null);
    try {
      const data = await getUnifiedResearchIntelligence(profileId, userId);
      setContext(data);
    } catch (err: unknown) {
      setContextError(err instanceof Error ? err.message : "Failed to load research intelligence context.");
    } finally {
      setContextLoading(false);
    }
  }, [profileId, userId]);

  // Load Unified Recommendations
  const loadRecommendations = useCallback(
    async (query?: string) => {
      if (!profileId) return;
      setRecsLoading(true);
      setRecsError(null);
      try {
        const data = await getUnifiedRecommendations(
          profileId,
          {
            query: query?.trim() ? query.trim() : undefined,
            limit: 25,
            include_evidence: true,
          },
          userId
        );
        setRecsData(data);
        if (data.recommendations.length > 0) {
          const oppIds = data.recommendations.map((r) => r.opportunity_id);

          fetchBatchOpportunityPreferenceMatches(profileId, oppIds, userId)
            .then((res) => {
              const map: Record<string, PreferencePersonalizationAssessment> = {};
              for (const a of res.assessments) {
                map[a.opportunity_id] = a;
              }
              setPreferenceMatches(map);
            })
            .catch((err) => {
              console.warn("Could not fetch preference matches:", err);
            });

          fetchBatchOpportunityPersonalization(profileId, oppIds, userId)
            .then((res) => {
              const map: Record<string, PersonalizationAssessment> = {};
              for (const a of res.assessments) {
                map[a.opportunity_id] = a;
              }
              setPersonalizationScores(map);
            })
            .catch((err) => {
              console.warn("Could not fetch personalization scores:", err);
            });
        }
      } catch (err: unknown) {
        setRecsError(err instanceof Error ? err.message : "Failed to load unified recommendations.");
      } finally {
        setRecsLoading(false);
      }
    },
    [profileId, userId]
  );

  useEffect(() => {
    loadContext();
    loadRecommendations();
  }, [loadContext, loadRecommendations]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    loadRecommendations(searchQuery);
  };

  const handleInspectIntelligence = async (opportunityId: string) => {
    setIntelLoading(true);
    try {
      const intel = await getOpportunityIntelligence(profileId, opportunityId, userId);
      setSelectedIntel(intel);
    } catch (err: unknown) {
      console.error("Failed to inspect opportunity intelligence:", err);
    } finally {
      setIntelLoading(false);
    }
  };

  const toggleTierExpanded = (key: string) => {
    setExpandedTiers((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const getIdentityBadge = (status: string, isAmbiguous: boolean) => {
    if (isAmbiguous) {
      return {
        bg: "#fef2f2",
        color: "#b91c1c",
        border: "#fecaca",
        label: "Ambiguous Identity",
        icon: AlertTriangle,
      };
    }
    switch (status) {
      case "CANONICAL_RESOLVED":
        return {
          bg: "#ecfdf5",
          color: "#047857",
          border: "#a7f3d0",
          label: "Canonical Resolved",
          icon: UserCheck,
        };
      case "SELF_DECLARED_ONLY":
        return {
          bg: "#eff6ff",
          color: "#1d4ed8",
          border: "#bfdbfe",
          label: "Self-Declared",
          icon: Info,
        };
      case "COLD_START":
      default:
        return {
          bg: "#f9fafb",
          color: "#4b5563",
          border: "#e5e7eb",
          label: "Cold Start",
          icon: Sparkles,
        };
    }
  };

  const filteredSignals = (signals: ResearchIntelligenceSignal[]) => {
    if (activeSignalFilter === "ALL") return signals;
    return signals.filter((s) => s.signal_type === activeSignalFilter);
  };

  return (
    <div className="space-y-6">
      {/* SECTION 1: HEADER & IDENTITY STATUS */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Sparkles className="w-5 h-5 text-indigo-600" />
              <span className="text-xs font-semibold uppercase tracking-wider text-indigo-700">
                Phase 4.7 Unified Intelligence
              </span>
            </div>
            <h1 className="text-2xl font-bold text-gray-900">
              {context?.full_name || "Research Intelligence & Recommendations"}
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              {context?.academic_status} {context?.institution_name ? `• ${context.institution_name}` : ""}
              {context?.department ? ` • Department: ${context.department}` : ""}
            </p>
          </div>

          <div className="flex items-center gap-3">
            {context && (
              <div
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border"
                style={{
                  backgroundColor: getIdentityBadge(context.identity_status, context.is_identity_ambiguous).bg,
                  color: getIdentityBadge(context.identity_status, context.is_identity_ambiguous).color,
                  borderColor: getIdentityBadge(context.identity_status, context.is_identity_ambiguous).border,
                }}
              >
                {React.createElement(getIdentityBadge(context.identity_status, context.is_identity_ambiguous).icon, {
                  size: 14,
                })}
                <span>{getIdentityBadge(context.identity_status, context.is_identity_ambiguous).label}</span>
              </div>
            )}
            <button
              onClick={() => {
                loadContext();
                loadRecommendations(searchQuery);
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-50 border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Refresh
            </button>
          </div>
        </div>

        {/* Identity Ambiguity or Cold Start Banner */}
        {context?.is_identity_ambiguous && (
          <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-2.5 text-amber-800 text-xs">
            <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
            <div>
              <span className="font-semibold">Identity Ambiguity Detected:</span> Multiple candidate academic profiles
              were detected for this name. Recommendations use only verified and explicit researcher signals to prevent
              fabrication.
            </div>
          </div>
        )}

        {context?.is_cold_start && (
          <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg flex items-start gap-2.5 text-blue-800 text-xs">
            <Info className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
            <div>
              <span className="font-semibold">Cold Start Researcher:</span> No explicit research topics or feedback
              records found yet. Relevance-dominant discovery ensures you receive high-quality opportunities without
              penalization.
            </div>
          </div>
        )}

        {/* Metrics Overview Cards */}
        {context && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-6 pt-6 border-t border-gray-100">
            <div className="bg-gray-50 p-3.5 rounded-lg border border-gray-100">
              <span className="text-xs text-gray-500 font-medium">Profile Completeness</span>
              <div className="text-lg font-bold text-gray-900 mt-0.5">{Math.round(context.completeness_score * 100)}%</div>
            </div>
            <div className="bg-gray-50 p-3.5 rounded-lg border border-gray-100">
              <span className="text-xs text-gray-500 font-medium">Research Topics</span>
              <div className="text-lg font-bold text-gray-900 mt-0.5">{context.active_interests_count}</div>
            </div>
            <div className="bg-gray-50 p-3.5 rounded-lg border border-gray-100">
              <span className="text-xs text-gray-500 font-medium">Preferences</span>
              <div className="text-lg font-bold text-gray-900 mt-0.5">
                {context.explicit_preferences_count} exp / {context.inferred_preferences_count} inf
              </div>
            </div>
            <div className="bg-gray-50 p-3.5 rounded-lg border border-gray-100">
              <span className="text-xs text-gray-500 font-medium">Intelligence Signals</span>
              <div className="text-lg font-bold text-gray-900 mt-0.5">{context.signals.length}</div>
            </div>
          </div>
        )}
      </div>

      {/* SECTION 2: SIGNAL PROVENANCE EXPLORER */}
      {context && context.signals.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
            <div>
              <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
                <Layers className="w-4 h-4 text-indigo-600" />
                Signal Provenance & Evidence Explorer
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Structured signals contributing to personalized recommendation and matching with complete provenance.
              </p>
            </div>

            {/* Filter buttons */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {["ALL", "PROFILE_ATTRIBUTE", "SCHOLARLY_EXPERTISE", "EXPLICIT_PREFERENCE", "INFERRED_PREFERENCE"].map(
                (filter) => (
                  <button
                    key={filter}
                    onClick={() => setActiveSignalFilter(filter)}
                    className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                      activeSignalFilter === filter
                        ? "bg-indigo-600 text-white font-medium"
                        : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                    }`}
                  >
                    {filter.replace("_", " ")}
                  </button>
                )
              )}
            </div>
          </div>

          <div className="divide-y divide-gray-100 max-h-64 overflow-y-auto pr-1">
            {filteredSignals(context.signals).map((signal, idx) => (
              <div key={idx} className="py-2.5 flex items-start justify-between gap-3 text-xs">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-gray-800">{signal.evidence || signal.signal_type}</span>
                    <span className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 text-[10px] font-mono">
                      {signal.signal_type}
                    </span>
                    <span className="px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 text-[10px] font-medium">
                      {signal.source}
                    </span>
                    {!signal.is_explicit && (
                      <span className="px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 text-[10px]">Inferred</span>
                    )}
                  </div>
                  <p className="text-gray-500 mt-1">{signal.evidence}</p>
                </div>
                <div className="text-right flex-shrink-0">
                  <div className="text-[11px] font-medium text-gray-700">
                    Strength: {(signal.strength * 100).toFixed(0)}%
                  </div>
                  <div className="text-[10px] text-gray-400">
                    Conf: {(signal.confidence * 100).toFixed(0)}%
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* SECTION 3: UNIFIED RECOMMENDATIONS WITH 6-TIER EXPLAINABILITY */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
          <div>
            <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
              <Award className="w-5 h-5 text-indigo-600" />
              Unified Evidence-Backed Recommendations
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Hybrid ranked opportunities bounded by Phase 2.5 relevance dominance guarantee (relevance ≥ 85%,
              personalization ≤ 15%).
            </p>
          </div>

          <form onSubmit={handleSearch} className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter by keyword..."
                className="pl-8 pr-3 py-1.5 text-xs border border-gray-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500 w-52"
              />
            </div>
            <button
              type="submit"
              className="px-3 py-1.5 text-xs font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors"
            >
              Search
            </button>
          </form>
        </div>

        {/* Relevance Dominance Guarantee Pill */}
        {recsData && (
          <div className="mb-4 px-3 py-2 bg-emerald-50 border border-emerald-200 rounded-lg flex items-center justify-between text-xs text-emerald-800">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-600 flex-shrink-0" />
              <span>{recsData.relevance_dominance_guarantee}</span>
            </div>
            <span className="font-semibold text-emerald-900">
              {recsData.returned_count} of {recsData.total_candidates} opportunities
            </span>
          </div>
        )}

        {/* Recommendations List */}
        {recsLoading ? (
          <div className="py-12 text-center text-gray-400 text-xs flex flex-col items-center gap-2">
            <RefreshCw className="w-5 h-5 animate-spin text-indigo-500" />
            Computing unified recommendations...
          </div>
        ) : recsError ? (
          <div className="p-4 bg-red-50 border border-red-200 text-red-700 text-xs rounded-lg">{recsError}</div>
        ) : !recsData?.recommendations.length ? (
          <div className="py-12 text-center text-gray-400 text-xs">No matching opportunities found.</div>
        ) : (
          <div className="space-y-4">
            {recsData.recommendations.map((item, idx) => {
              const tierKey = `item-${item.opportunity_id}`;
              const isExpanded = Boolean(expandedTiers[tierKey]);

              return (
                <div
                  key={item.opportunity_id}
                  className="p-4 rounded-xl border border-gray-200 hover:border-indigo-200 hover:shadow-sm transition-all"
                >
                  <div className="flex flex-col md:flex-row md:items-start justify-between gap-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="font-mono text-xs text-gray-400 font-semibold">#{idx + 1}</span>
                        {item.opportunity_type && (
                          <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 text-[10px] font-semibold">
                            {item.opportunity_type}
                          </span>
                        )}
                        {item.sponsor && (
                          <span className="text-xs text-gray-500 font-medium">{item.sponsor}</span>
                        )}
                        {item.workspace_context.is_saved && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-purple-50 text-purple-700 text-[10px] font-semibold">
                            <Bookmark className="w-3 h-3" />
                            Saved to Workspace
                          </span>
                        )}
                        {item.workspace_context.has_active_submission && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-green-50 text-green-700 text-[10px] font-semibold">
                            <FileCheck className="w-3 h-3" />
                            Submission: {item.workspace_context.submission_stage} (
                            {item.workspace_context.submission_readiness_score?.toFixed(0)}%)
                          </span>
                        )}
                        <PreferenceMatchBadge assessment={preferenceMatches[item.opportunity_id] || null} />
                        <PersonalizationScoreBadge assessment={personalizationScores[item.opportunity_id] || null} />
                      </div>

                      <h3
                        onClick={() => onSelectOpportunity?.(item.opportunity_id)}
                        className="text-base font-bold text-gray-900 hover:text-indigo-600 cursor-pointer transition-colors"
                      >
                        {item.title}
                      </h3>

                      <p className="text-xs text-gray-600 mt-1.5">{item.primary_match_reason}</p>

                      {/* Metadata row: Deadline, Risk, Amount */}
                      <div className="flex items-center gap-4 mt-2.5 text-xs text-gray-500 flex-wrap">
                        {item.deadline && (
                          <div className="flex items-center gap-1">
                            <Calendar className="w-3.5 h-3.5 text-gray-400" />
                            <span>
                              Deadline: {new Date(item.deadline).toLocaleDateString()}{" "}
                              {item.days_remaining !== null && item.days_remaining !== undefined && (
                                <span
                                  className={
                                    item.days_remaining < 14
                                      ? "text-red-600 font-semibold"
                                      : item.days_remaining < 30
                                      ? "text-amber-600"
                                      : "text-gray-500"
                                  }
                                >
                                  ({item.days_remaining}d left)
                                </span>
                              )}
                            </span>
                          </div>
                        )}

                        {item.risk_level && (
                          <div className="flex items-center gap-1">
                            {item.risk_level === "HIGH_RISK" ? (
                              <ShieldAlert className="w-3.5 h-3.5 text-red-500" />
                            ) : item.risk_level === "MODERATE_RISK" ? (
                              <AlertCircle className="w-3.5 h-3.5 text-amber-500" />
                            ) : (
                              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
                            )}
                            <span
                              className={
                                item.risk_level === "HIGH_RISK"
                                  ? "text-red-700 font-semibold"
                                  : item.risk_level === "MODERATE_RISK"
                                  ? "text-amber-700"
                                  : "text-emerald-700"
                              }
                            >
                              Risk: {item.risk_level.replace(/_/g, " ")}
                            </span>
                          </div>
                        )}

                        {item.amount_total && (
                          <div className="font-semibold text-gray-700">
                            {item.currency || "$"}
                            {item.amount_total.toLocaleString()}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Right side: Scores & Actions */}
                    <div className="flex md:flex-col items-end justify-between gap-2 flex-shrink-0">
                      <div className="text-right">
                        <div className="text-xs font-semibold text-gray-500">Composite Score</div>
                        <div className="text-xl font-black text-indigo-700">
                          {(item.composite_score * 100).toFixed(1)}%
                        </div>
                        <div className="text-[10px] text-gray-400 mt-0.5">
                          Rel: {(item.relevance_score * 100).toFixed(0)}% • Pers:{" "}
                          {(item.personalization_score * 100).toFixed(0)}%
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5 mt-2">
                        <button
                          onClick={() => handleInspectIntelligence(item.opportunity_id)}
                          className="p-1.5 text-gray-500 hover:text-indigo-600 rounded-md hover:bg-indigo-50 transition-colors"
                          title="View Full Multi-Tier Intelligence"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => toggleTierExpanded(tierKey)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
                        >
                          <span>Evidence ({item.evidence_tiers.length})</span>
                          {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Collapsible 6-Tier Evidence Breakdown */}
                  {isExpanded && (
                    <div className="mt-4 pt-4 border-t border-gray-100 space-y-2.5">
                      <div className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
                        Multi-Tier Evidence Breakdown
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                        {item.evidence_tiers.map((tier, tIdx) => (
                          <div
                            key={tIdx}
                            className={`p-3 rounded-lg border text-xs ${
                              tier.is_active
                                ? "bg-slate-50/80 border-slate-200"
                                : "bg-gray-50/40 border-gray-100 opacity-60"
                            }`}
                          >
                            <div className="flex items-center justify-between font-semibold text-gray-800">
                              <span>{tier.tier_title}</span>
                              <span className="text-[10px] text-indigo-600 font-mono">
                                +{(tier.score_contribution * 100).toFixed(1)}%
                              </span>
                            </div>
                            <p className="text-gray-600 mt-1 text-[11px] leading-relaxed">{tier.summary}</p>
                            {tier.signals.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-1">
                                {tier.signals.slice(0, 3).map((sig, sIdx) => (
                                  <span
                                    key={sIdx}
                                    className="px-1.5 py-0.5 rounded bg-white border border-gray-200 text-[10px] text-gray-600"
                                  >
                                    {sig.evidence || sig.signal_type}: {(sig.strength * 100).toFixed(0)}%
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* SECTION 4: DETAILED OPPORTUNITY INTELLIGENCE MODAL */}
      {selectedIntel && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4 z-50"
          onClick={() => setSelectedIntel(null)}
        >
          <div
            className="bg-white rounded-2xl max-w-2xl w-full max-h-[85vh] overflow-y-auto shadow-xl p-6 border border-gray-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 pb-4 border-b border-gray-100">
              <div>
                <span className="text-[10px] font-semibold uppercase tracking-wider text-indigo-600">
                  Opportunity Intelligence Dossier
                </span>
                <h3 className="text-lg font-bold text-gray-900 mt-0.5">{selectedIntel.opportunity_title}</h3>
              </div>
              <button
                onClick={() => setSelectedIntel(null)}
                className="text-gray-400 hover:text-gray-600 text-sm font-semibold p-1"
              >
                ✕
              </button>
            </div>

            {/* Score Decomposition Bar */}
            <div className="grid grid-cols-3 gap-3 my-4">
              <div className="bg-indigo-50 p-3 rounded-lg text-center">
                <span className="text-[10px] text-indigo-700 font-semibold">Composite Score</span>
                <div className="text-lg font-black text-indigo-900">
                  {(selectedIntel.composite_score * 100).toFixed(1)}%
                </div>
              </div>
              <div className="bg-emerald-50 p-3 rounded-lg text-center">
                <span className="text-[10px] text-emerald-700 font-semibold">Relevance (≥85%)</span>
                <div className="text-lg font-black text-emerald-900">
                  {(selectedIntel.relevance_score * 100).toFixed(1)}%
                </div>
              </div>
              <div className="bg-purple-50 p-3 rounded-lg text-center">
                <span className="text-[10px] text-purple-700 font-semibold">Personalization (≤15%)</span>
                <div className="text-lg font-black text-purple-900">
                  {(selectedIntel.personalization_score * 100).toFixed(1)}%
                </div>
              </div>
            </div>

            {/* Full Tiers List */}
            <div className="space-y-3">
              <span className="text-xs font-bold text-gray-800 uppercase tracking-wide">
                Structured Evidence Tiers
              </span>
              {selectedIntel.evidence_tiers.map((tier, idx) => (
                <div key={idx} className="p-3.5 rounded-lg border border-gray-200 bg-gray-50/60 text-xs">
                  <div className="flex items-center justify-between font-semibold text-gray-900">
                    <span>{tier.tier_title}</span>
                    <span className="text-indigo-600 font-mono">
                      Conf: {(tier.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="text-gray-700 mt-1 leading-relaxed">{tier.summary}</p>
                  {tier.signals.length > 0 && (
                    <div className="mt-2.5 pt-2 border-t border-gray-200/60 space-y-1">
                      {tier.signals.map((sig, sIdx) => (
                        <div key={sIdx} className="flex items-center justify-between text-[11px] text-gray-600">
                          <span>
                            • {sig.evidence || sig.signal_type} ({sig.source})
                          </span>
                          <span className="font-mono">{(sig.strength * 100).toFixed(0)}%</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="mt-6 pt-4 border-t border-gray-100 flex justify-end">
              <button
                onClick={() => setSelectedIntel(null)}
                className="px-4 py-2 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              >
                Close Dossier
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
