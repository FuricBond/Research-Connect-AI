"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  fetchPersonalizedRecommendations,
  fetchRecommendationExplanation,
  recordRecommendationFeedback,
} from "../../services/api";
import type {
  FeedbackType,
  PersonalizedRankedCandidate,
  PersonalizedRankingResponse,
  RecommendationExplanation,
} from "../../types/researcher";
import { RecommendationExplanationModal } from "./RecommendationExplanationModal";
import { AlertTriangle, HelpCircle, Sparkles } from "lucide-react";

interface PersonalizedRankingPreviewProps {
  profileId: string;
  userId?: string;
  onFeedbackRecorded?: () => void;
}

export function PersonalizedRankingPreview({
  profileId,
  userId,
  onFeedbackRecorded,
}: PersonalizedRankingPreviewProps) {
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<PersonalizedRankingResponse | null>(null);

  // Filters and Ablation Controls
  const [enablePersonalization, setEnablePersonalization] = useState<boolean>(true);
  const [includeInferred, setIncludeInferred] = useState<boolean>(true);
  const [includeExpertise, setIncludeExpertise] = useState<boolean>(true);
  const [limit, setLimit] = useState<number>(20);
  const [selectedCandidate, setSelectedCandidate] = useState<PersonalizedRankedCandidate | null>(null);
  const [feedbackStatus, setFeedbackStatus] = useState<Record<string, string>>({});
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState<boolean>(false);

  // Phase 3.8 Explanation Modal State
  const [explainingCandidate, setExplainingCandidate] = useState<PersonalizedRankedCandidate | null>(null);
  const [explanationData, setExplanationData] = useState<RecommendationExplanation | null>(null);
  const [isExplanationLoading, setIsExplanationLoading] = useState<boolean>(false);
  const [showExplanationModal, setShowExplanationModal] = useState<boolean>(false);

  const handleOpenExplanation = async (cand: PersonalizedRankedCandidate, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setExplainingCandidate(cand);
    setShowExplanationModal(true);

    if (cand.explanation) {
      setExplanationData(cand.explanation);
      setIsExplanationLoading(false);
    } else {
      setIsExplanationLoading(true);
      try {
        const exp = await fetchRecommendationExplanation(profileId, cand.opportunity_id, userId);
        setExplanationData(exp);
      } catch (err) {
        console.error("Failed to fetch explanation:", err);
      } finally {
        setIsExplanationLoading(false);
      }
    }
  };

  const handleRecordFeedback = async (
    opportunityId: string,
    type: FeedbackType,
    rankPosition?: number
  ) => {
    if (!profileId || isSubmittingFeedback) return;
    setIsSubmittingFeedback(true);
    try {
      await recordRecommendationFeedback(
        profileId,
        {
          opportunity_id: opportunityId,
          feedback_type: type,
          source: "RECOMMENDATION_FEED",
          rank_position: rankPosition,
        },
        userId
      );
      setFeedbackStatus((prev) => ({ ...prev, [opportunityId]: type }));
      onFeedbackRecorded?.();
    } catch (err: unknown) {
      console.error("Failed to record feedback:", err);
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  const loadRecommendations = useCallback(async () => {
    if (!profileId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPersonalizedRecommendations(
        profileId,
        {
          limit,
          includeInferred,
          includeExpertise,
          enablePersonalization,
          includeAblation: true,
        },
        userId
      );
      setResponse(data);
      if (data.recommendations.length > 0) {
        setSelectedCandidate(data.recommendations[0]);
      } else {
        setSelectedCandidate(null);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load personalized recommendations.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [profileId, userId, limit, includeInferred, includeExpertise, enablePersonalization]);

  useEffect(() => {
    loadRecommendations();
  }, [loadRecommendations]);

  const ablation = response?.ablation_summary;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-6">
      {/* Header & Architectural Scope Note */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-white tracking-tight">
              Personalized Recommendation Ranking
            </h2>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-900/60 text-indigo-300 border border-indigo-700/50">
              Phase 3.5 Diagnostic
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Deterministic ranking layer: Base Relevance (Phase 2) + Bounded Personalization (Max &le; 0.15).
          </p>
        </div>

        {/* Action Button & Toggle */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setEnablePersonalization(!enablePersonalization)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              enablePersonalization
                ? "bg-indigo-600/30 text-indigo-300 border-indigo-500/50 hover:bg-indigo-600/40"
                : "bg-slate-800 text-slate-400 border-slate-700 hover:bg-slate-700"
            }`}
            title="Toggle between Phase 3.5 Personalization (R1) and Phase 2 Base Ranking (R0)"
          >
            {enablePersonalization ? "✓ Personalization ON (R1)" : "✕ Personalization OFF (R0 Baseline)"}
          </button>
          <button
            onClick={loadRecommendations}
            disabled={loading}
            className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors"
          >
            {loading ? "Re-ranking..." : "Refresh"}
          </button>
        </div>
      </div>

      {/* Control Panel */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 bg-slate-950/60 p-3 rounded-lg border border-slate-800/80 text-xs">
        <label className="flex items-center gap-2 text-slate-300 cursor-pointer">
          <input
            type="checkbox"
            checked={includeInferred}
            onChange={(e) => setIncludeInferred(e.target.checked)}
            className="rounded border-slate-700 text-indigo-600 focus:ring-indigo-500 bg-slate-800"
          />
          Include Inferred Preferences
        </label>
        <label className="flex items-center gap-2 text-slate-300 cursor-pointer">
          <input
            type="checkbox"
            checked={includeExpertise}
            onChange={(e) => setIncludeExpertise(e.target.checked)}
            className="rounded border-slate-700 text-indigo-600 focus:ring-indigo-500 bg-slate-800"
          />
          Include Scholarly Expertise
        </label>
        <div className="flex items-center gap-2 text-slate-300">
          <span>Max Results:</span>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="bg-slate-800 border border-slate-700 text-white rounded px-2 py-0.5 text-xs focus:ring-1 focus:ring-indigo-500"
          >
            <option value={10}>10</option>
            <option value={20}>20</option>
            <option value={50}>50</option>
          </select>
        </div>
      </div>

      {/* Ablation Summary Banner */}
      {ablation && (
        <div className="bg-gradient-to-r from-slate-950 via-slate-900 to-indigo-950/40 p-4 rounded-lg border border-indigo-900/30 grid grid-cols-2 md:grid-cols-5 gap-3 text-center">
          <div>
            <div className="text-xs text-slate-400">Total Evaluated</div>
            <div className="text-lg font-bold text-white">{ablation.total_candidates}</div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Reordered (R0 &rarr; R1)</div>
            <div className="text-lg font-bold text-indigo-300">
              {ablation.reordered_candidates_count}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Max Promotion / Demotion</div>
            <div className="text-sm font-semibold text-slate-200 mt-1">
              <span className="text-emerald-400">+{ablation.max_rank_promotion}</span> /{" "}
              <span className="text-amber-400">{ablation.max_rank_demotion}</span>
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Avg Personalization Adj</div>
            <div className="text-lg font-bold text-cyan-300">
              +{ablation.average_personalization_adjustment.toFixed(4)}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Safety & Invariants</div>
            <div className="text-sm font-semibold mt-1">
              {ablation.invariants_verified ? (
                <span className="text-emerald-400 flex items-center justify-center gap-1">
                  ✓ Monotonic
                </span>
              ) : (
                <span className="text-red-400">Invariant Violation</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="p-3 bg-red-950/50 border border-red-800 rounded text-red-300 text-xs">
          {error}
        </div>
      )}

      {/* Results Content */}
      {loading ? (
        <div className="py-12 text-center text-slate-400 text-sm">
          Evaluating Phase 2 base relevance and bounded personalization adjustments...
        </div>
      ) : response && response.recommendations.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Candidates List Table */}
          <div className="lg:col-span-2 space-y-2 overflow-y-auto max-h-[560px] pr-1">
            {response.recommendations.map((cand) => {
              const isSelected = selectedCandidate?.opportunity_id === cand.opportunity_id;
              const delta = cand.rank_delta;

              return (
                <div
                  key={cand.opportunity_id}
                  onClick={() => setSelectedCandidate(cand)}
                  className={`p-3.5 rounded-lg border cursor-pointer transition-all ${
                    isSelected
                      ? "bg-slate-800/90 border-indigo-500 shadow-md ring-1 ring-indigo-500/50"
                      : "bg-slate-950/60 border-slate-800 hover:border-slate-700 hover:bg-slate-900/60"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    {/* Rank & Delta Indicator */}
                    <div className="flex items-center gap-2 min-w-[58px]">
                      <span className="text-base font-bold text-white">#{cand.rank}</span>
                      {delta > 0 ? (
                        <span className="text-[10px] font-bold text-emerald-400 bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800/50">
                          +{delta}
                        </span>
                      ) : delta < 0 ? (
                        <span className="text-[10px] font-bold text-amber-400 bg-amber-950/60 px-1.5 py-0.5 rounded border border-amber-800/50">
                          {delta}
                        </span>
                      ) : (
                        <span className="text-[10px] text-slate-500 font-mono">=</span>
                      )}
                    </div>

                    {/* Title & Metadata */}
                    <div className="flex-1 min-w-0">
                      <h4 className="text-xs font-semibold text-white truncate">
                        {cand.opportunity.title}
                      </h4>
                      <div className="flex flex-wrap items-center gap-2 mt-1 text-[11px] text-slate-400">
                        <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                          {cand.opportunity.opportunity_type}
                        </span>
                        <span>{cand.opportunity.delivery_mode}</span>
                        {cand.opportunity.location && (
                          <span className="truncate">&bull; {cand.opportunity.location}</span>
                        )}
                        {cand.opportunity.days_remaining != null && (
                          <span className="text-amber-400">
                            &bull; {Math.max(0, Math.round(cand.opportunity.days_remaining))}d left
                          </span>
                        )}

                      </div>
                    </div>

                    {/* Score Badges & Why This Button */}
                    <div className="text-right flex flex-col items-end min-w-[90px] gap-1.5">
                      <div>
                        <div className="text-sm font-bold text-indigo-300 font-mono">
                          {cand.final_score.toFixed(4)}
                        </div>
                        <div className="text-[10px] text-slate-400 font-mono">
                          Base: {cand.base_relevance_score.toFixed(3)}
                        </div>
                        {cand.personalization_adjustment > 0 && (
                          <div className="text-[10px] text-emerald-400 font-mono">
                            +{cand.personalization_adjustment.toFixed(3)}
                          </div>
                        )}
                      </div>

                      {/* Why this? Button */}
                      <button
                        type="button"
                        onClick={(e) => handleOpenExplanation(cand, e)}
                        className="px-2 py-1 rounded bg-indigo-950/80 hover:bg-indigo-900 text-indigo-300 border border-indigo-800/60 text-[10px] font-semibold flex items-center gap-1 transition-colors"
                        title="Why this recommendation?"
                      >
                        <HelpCircle size={11} />
                        <span>Why this?</span>
                      </button>
                    </div>
                  </div>

                  {/* Badges footer: Personalization strength + Risk warning */}
                  <div className="mt-2 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[10px]">
                    <span className="text-slate-400 flex items-center gap-1">
                      <Sparkles size={11} className="text-indigo-400" />
                      {cand.explanation?.personalization_strength ||
                        (cand.personalization_adjustment >= 0.08
                          ? "Highly personalized"
                          : cand.personalization_adjustment >= 0.04
                          ? "Personalized"
                          : cand.personalization_adjustment > 0
                          ? "Some personalization"
                          : "General recommendation")}
                    </span>

                    {(cand.opportunity.risk_level === "HIGH_RISK" || cand.opportunity.is_predatory_flag) && (
                      <span className="text-rose-400 font-semibold flex items-center gap-1">
                        <AlertTriangle size={11} /> High Risk Warning
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Detailed Candidate Diagnostic Inspection Pane */}
          {selectedCandidate && (
            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-4 text-xs">
              <div>
                <span className="text-[10px] uppercase font-bold tracking-wider text-indigo-400">
                  Candidate Diagnostic Inspection
                </span>
                <h3 className="text-sm font-bold text-white mt-1">
                  {selectedCandidate.opportunity.title}
                </h3>
                <div className="text-slate-400 mt-0.5">
                  Opportunity ID:{" "}
                  <span className="font-mono text-[10px] text-slate-300">
                    {selectedCandidate.opportunity_id}
                  </span>
                </div>
              </div>

              {/* Ranks & Score Decomposition */}
              <div className="grid grid-cols-3 gap-2 bg-slate-900/80 p-2.5 rounded border border-slate-800 font-mono text-center">
                <div>
                  <div className="text-[10px] text-slate-400">Final Rank (R1)</div>
                  <div className="text-base font-bold text-indigo-300">
                    #{selectedCandidate.rank}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] text-slate-400">Base Rank (R0)</div>
                  <div className="text-base font-bold text-slate-400">
                    #{selectedCandidate.base_rank}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] text-slate-400">Movement</div>
                  <div
                    className={`text-base font-bold ${
                      selectedCandidate.rank_delta > 0
                        ? "text-emerald-400"
                        : selectedCandidate.rank_delta < 0
                        ? "text-amber-400"
                        : "text-slate-400"
                    }`}
                  >
                    {selectedCandidate.rank_delta > 0
                      ? `+${selectedCandidate.rank_delta}`
                      : selectedCandidate.rank_delta}
                  </div>
                </div>
              </div>

              {/* Score Component Breakdown */}
              <div className="space-y-2">
                <span className="text-[11px] font-semibold text-slate-300">
                  Personalization Adjustment Attribution
                </span>
                <div className="space-y-1.5 text-[11px]">
                  <div className="flex justify-between text-slate-300">
                    <span>Base Relevance (Phase 2):</span>
                    <span className="font-mono font-bold">
                      {selectedCandidate.base_relevance_score.toFixed(4)}
                    </span>
                  </div>
                  <div className="flex justify-between text-slate-300">
                    <span>Explicit Preferences (40%):</span>
                    <span className="font-mono">
                      {selectedCandidate.score_breakdown.explicit_preference_score.toFixed(4)}
                    </span>
                  </div>
                  <div className="flex justify-between text-slate-300">
                    <span>Inferred Preferences (15%):</span>
                    <span className="font-mono">
                      {selectedCandidate.score_breakdown.inferred_preference_score.toFixed(4)}
                    </span>
                  </div>
                  <div className="flex justify-between text-slate-300">
                    <span>Scholarly Expertise (25%):</span>
                    <span className="font-mono">
                      {selectedCandidate.score_breakdown.expertise_match_score.toFixed(4)}
                    </span>
                  </div>
                  <div className="flex justify-between text-slate-300">
                    <span>Profile Signals (10%):</span>
                    <span className="font-mono">
                      {selectedCandidate.score_breakdown.profile_match_score.toFixed(4)}
                    </span>
                  </div>
                  {selectedCandidate.score_breakdown.behavioral_score != null && (
                    <div className="flex justify-between text-slate-300">
                      <span>Learned Behavioral (Phase 3.6):</span>
                      <span
                        className={`font-mono ${
                          (selectedCandidate.score_breakdown.behavioral_adjustment ?? 0) >= 0
                            ? "text-emerald-400"
                            : "text-rose-400"
                        }`}
                      >
                        {(selectedCandidate.score_breakdown.behavioral_adjustment ?? 0) >= 0 ? "+" : ""}
                        {(selectedCandidate.score_breakdown.behavioral_adjustment ?? 0).toFixed(4)}
                      </span>
                    </div>
                  )}
                  <div className="flex justify-between text-slate-300">
                    <span>Relevance Damping Factor:</span>
                    <span className="font-mono">
                      {selectedCandidate.score_breakdown.relevance_damping.toFixed(4)}
                    </span>
                  </div>
                  <div className="border-t border-slate-800 pt-1 flex justify-between font-semibold text-emerald-400">
                    <span>Total Bounded Adjustment (&le;0.15):</span>
                    <span className="font-mono">
                      +{selectedCandidate.personalization_adjustment.toFixed(4)}
                    </span>
                  </div>
                  <div className="flex justify-between font-bold text-white text-xs border-t border-slate-800 pt-1">
                    <span>Final Composite Score:</span>
                    <span className="font-mono text-indigo-300">
                      {selectedCandidate.final_score.toFixed(4)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Matched Personalization Signals */}
              <div className="space-y-1.5">
                <span className="text-[11px] font-semibold text-slate-300">
                  Matched Researcher Signals
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {selectedCandidate.matched_signals.matched_preferences.map((p, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 rounded bg-indigo-950/80 text-indigo-300 border border-indigo-800/40 text-[10px]"
                    >
                      {p}
                    </span>
                  ))}
                  {selectedCandidate.matched_signals.matched_expertise.map((e, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 rounded bg-purple-950/80 text-purple-300 border border-purple-800/40 text-[10px]"
                    >
                      {e}
                    </span>
                  ))}
                  {selectedCandidate.matched_signals.matched_topics.map((t, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px]"
                    >
                      {t}
                    </span>
                  ))}
                  {selectedCandidate.matched_signals.matched_preferences.length === 0 &&
                    selectedCandidate.matched_signals.matched_expertise.length === 0 &&
                    selectedCandidate.matched_signals.matched_topics.length === 0 && (
                      <span className="text-slate-500 italic text-[10px]">
                        No specific preference/expertise match (fallback discovery)
                      </span>
                    )}
                </div>
              </div>

              {/* Phase 2.6 Risk & Phase 2.7 Deadline Badges */}
              <div className="border-t border-slate-800 pt-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400 text-[11px]">Phase 2.6 Trust/Risk:</span>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                      selectedCandidate.opportunity.risk_level === "HIGH_RISK" ||
                      selectedCandidate.opportunity.is_predatory_flag
                        ? "bg-red-950 text-red-300 border border-red-800"
                        : "bg-emerald-950 text-emerald-300 border border-emerald-800"
                    }`}
                  >
                    {selectedCandidate.opportunity.risk_level || "LOW_RISK"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400 text-[11px]">Phase 2.7 Deadline:</span>
                  <span className="text-[10px] font-mono text-amber-300">
                    {selectedCandidate.opportunity.deadline_status || "UNKNOWN"} (
                    {selectedCandidate.opportunity.urgency_tier || "APPROACHING"})
                  </span>
                </div>

                {/* Phase 3.6 Interactive Recommendation Feedback Loop */}
                <div className="border-t border-slate-800/80 pt-2.5 mt-2 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-slate-300">
                      Recommendation Feedback:
                    </span>
                    {feedbackStatus[selectedCandidate.opportunity_id] && (
                      <span className="text-[10px] text-emerald-400 font-medium font-mono">
                        ✓ Recorded: {feedbackStatus[selectedCandidate.opportunity_id]}
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-4 gap-1.5 pt-0.5">
                    <button
                      type="button"
                      onClick={() =>
                        handleRecordFeedback(
                          selectedCandidate.opportunity_id,
                          "SAVE",
                          selectedCandidate.rank
                        )
                      }
                      disabled={isSubmittingFeedback}
                      className="px-2 py-1.5 rounded bg-amber-950/60 hover:bg-amber-900/60 text-amber-300 border border-amber-800/50 text-[11px] font-medium flex items-center justify-center gap-1 transition-colors disabled:opacity-50"
                      title="Save bookmark (+0.25 weight)"
                    >
                      <span>★</span> Save
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        handleRecordFeedback(
                          selectedCandidate.opportunity_id,
                          "INTERESTED",
                          selectedCandidate.rank
                        )
                      }
                      disabled={isSubmittingFeedback}
                      className="px-2 py-1.5 rounded bg-emerald-950/60 hover:bg-emerald-900/60 text-emerald-300 border border-emerald-800/50 text-[11px] font-medium flex items-center justify-center gap-1 transition-colors disabled:opacity-50"
                      title="Interested (+0.30 weight)"
                    >
                      <span>👍</span> Like
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        handleRecordFeedback(
                          selectedCandidate.opportunity_id,
                          "NOT_INTERESTED",
                          selectedCandidate.rank
                        )
                      }
                      disabled={isSubmittingFeedback}
                      className="px-2 py-1.5 rounded bg-rose-950/60 hover:bg-rose-900/60 text-rose-300 border border-rose-800/50 text-[11px] font-medium flex items-center justify-center gap-1 transition-colors disabled:opacity-50"
                      title="Not Interested (-0.30 weight)"
                    >
                      <span>👎</span> Dislike
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        handleRecordFeedback(
                          selectedCandidate.opportunity_id,
                          "DISMISS",
                          selectedCandidate.rank
                        )
                      }
                      disabled={isSubmittingFeedback}
                      className="px-2 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-[11px] font-medium flex items-center justify-center gap-1 transition-colors disabled:opacity-50"
                      title="Dismiss & Suppress (-0.20 weight)"
                    >
                      <span>✕</span> Dismiss
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="py-10 text-center text-slate-400 text-sm">
          No candidates available for personalized ranking.
        </div>
      )}

      {/* Phase 3.8 Recommendation Explanation Modal */}
      <RecommendationExplanationModal
        isOpen={showExplanationModal}
        onClose={() => setShowExplanationModal(false)}
        explanation={explanationData}
        loading={isExplanationLoading}
        opportunityTitle={explainingCandidate?.opportunity.title}
        organization={explainingCandidate?.opportunity.location || explainingCandidate?.opportunity.delivery_mode}
      />
    </div>
  );
}
