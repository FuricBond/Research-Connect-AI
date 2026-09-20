"use client";

import React, { useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  HelpCircle,
  Info,
  Loader2,
  MinusCircle,
  Shield,
  ShieldAlert,
  Sparkles,
  X,
} from "lucide-react";
import { fetchRecommendationPersonalizationExplanation } from "../../services/api";
import type {
  PersonalizationFactor,
  PersonalizationImpact,
  RecommendationPersonalizationExplanation,
} from "../../types/personalization";

interface WhyThisRecommendationModalProps {
  isOpen: boolean;
  onClose: () => void;
  researcherId: string;
  recommendationId: string;
  userId?: string;
}

export const WhyThisRecommendationModal: React.FC<WhyThisRecommendationModalProps> = ({
  isOpen,
  onClose,
  researcherId,
  recommendationId,
  userId,
}) => {
  const [data, setData] = useState<RecommendationPersonalizationExplanation | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !recommendationId || !researcherId) return;

    let isMounted = true;
    setIsLoading(true);
    setError(null);

    fetchRecommendationPersonalizationExplanation(researcherId, recommendationId, userId)
      .then((res) => {
        if (isMounted) {
          setData(res);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err?.detail || err?.message || "Failed to load personalization explanation.");
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, recommendationId, researcherId, userId]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const getImpactBadge = (impact: PersonalizationImpact) => {
    switch (impact) {
      case "STRONG_PERSONALIZATION":
        return {
          label: "Strong Personalization",
          badgeClass: "bg-purple-100 text-purple-800 border-purple-300 dark:bg-purple-950/50 dark:text-purple-300 dark:border-purple-800",
          icon: <Sparkles className="w-4 h-4 mr-1 text-purple-600 dark:text-purple-400" />,
        };
      case "MODERATE_PERSONALIZATION":
        return {
          label: "Moderate Personalization",
          badgeClass: "bg-indigo-100 text-indigo-800 border-indigo-300 dark:bg-indigo-950/50 dark:text-indigo-300 dark:border-indigo-800",
          icon: <Sparkles className="w-4 h-4 mr-1 text-indigo-600 dark:text-indigo-400" />,
        };
      case "LOW_PERSONALIZATION":
        return {
          label: "Low Personalization",
          badgeClass: "bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-800",
          icon: <Info className="w-4 h-4 mr-1 text-blue-600 dark:text-blue-400" />,
        };
      case "PERSONALIZATION_SUPPRESSED":
        return {
          label: "Personalization Suppressed",
          badgeClass: "bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800",
          icon: <ShieldAlert className="w-4 h-4 mr-1 text-amber-600 dark:text-amber-400" />,
        };
      case "NO_PERSONALIZATION":
      default:
        return {
          label: "No Personalization Influence",
          badgeClass: "bg-gray-100 text-gray-700 border-gray-300 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700",
          icon: <MinusCircle className="w-4 h-4 mr-1 text-gray-500" />,
        };
    }
  };

  const getFactorIcon = (factor: PersonalizationFactor) => {
    if (factor.polarity === "POSITIVE") {
      return <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />;
    }
    if (factor.polarity === "NEGATIVE") {
      return <AlertCircle className="w-4 h-4 text-rose-600 dark:text-rose-400 shrink-0 mt-0.5" />;
    }
    return <MinusCircle className="w-4 h-4 text-gray-400 shrink-0 mt-0.5" />;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-white dark:bg-gray-900 rounded-xl shadow-2xl border border-gray-200 dark:border-gray-800 p-6 text-gray-900 dark:text-gray-100"
        role="dialog"
        aria-modal="true"
        aria-labelledby="why-modal-title"
      >
        {/* Header */}
        <div className="flex items-start justify-between pb-4 border-b border-gray-200 dark:border-gray-800">
          <div>
            <div className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
              <h2 id="why-modal-title" className="text-xl font-bold tracking-tight">
                Why This Recommendation?
              </h2>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Transparent, deterministic explanation of how your preferences and signals shaped this result.
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="mt-4 space-y-5">
          {isLoading && (
            <div className="flex flex-col items-center justify-center py-12 text-gray-500">
              <Loader2 className="w-8 h-8 animate-spin text-indigo-600 dark:text-indigo-400 mb-2" />
              <p className="text-sm font-medium">Loading personalization explanation...</p>
            </div>
          )}

          {error && (
            <div className="p-4 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-lg text-rose-800 dark:text-rose-200 text-sm">
              <p className="font-semibold flex items-center gap-1.5">
                <AlertCircle className="w-4 h-4" /> Error loading explanation
              </p>
              <p className="mt-1">{error}</p>
            </div>
          )}

          {!isLoading && !error && data && (
            <>
              {/* Opportunity Title & Impact Badge */}
              <div className="bg-gray-50 dark:bg-gray-800/60 p-4 rounded-lg border border-gray-200 dark:border-gray-700/60 space-y-2">
                <div className="text-xs uppercase tracking-wider font-semibold text-gray-500 dark:text-gray-400">
                  Opportunity
                </div>
                <h3 className="text-base font-semibold text-gray-900 dark:text-white">
                  {data.opportunity_title}
                </h3>
                <div className="pt-2 flex items-center gap-2">
                  <span className="text-xs text-gray-500 dark:text-gray-400">Personalization Impact:</span>
                  {(() => {
                    const badge = getImpactBadge(data.personalization_impact);
                    return (
                      <span
                        className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold border ${badge.badgeClass}`}
                      >
                        {badge.icon}
                        {badge.label}
                      </span>
                    );
                  })()}
                </div>
              </div>

              {/* Score Breakdown (Base Relevance vs Personalization) */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="p-3 bg-blue-50/60 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-900/40 rounded-lg">
                  <div className="text-xs font-medium text-blue-700 dark:text-blue-300">
                    Core Base Relevance
                  </div>
                  <div className="text-2xl font-bold text-blue-900 dark:text-blue-100 mt-1">
                    {(data.base_relevance_score * 100).toFixed(0)}%
                  </div>
                  <p className="text-[11px] text-blue-600/80 dark:text-blue-400 mt-0.5">
                    85% baseline weight
                  </p>
                </div>

                <div className="p-3 bg-purple-50/60 dark:bg-purple-950/20 border border-purple-200 dark:border-purple-900/40 rounded-lg">
                  <div className="text-xs font-medium text-purple-700 dark:text-purple-300">
                    Personalization Fit
                  </div>
                  <div className="text-2xl font-bold text-purple-900 dark:text-purple-100 mt-1">
                    {(data.personalization_score * 100).toFixed(0)}%
                  </div>
                  <p className="text-[11px] text-purple-600/80 dark:text-purple-400 mt-0.5">
                    15% bounded weight
                  </p>
                </div>

                <div className="p-3 bg-emerald-50/60 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-900/40 rounded-lg">
                  <div className="text-xs font-medium text-emerald-700 dark:text-emerald-300">
                    Final Ranking Score
                  </div>
                  <div className="text-2xl font-bold text-emerald-900 dark:text-emerald-100 mt-1">
                    {(data.final_score * 100).toFixed(0)}%
                  </div>
                  <p className="text-[11px] text-emerald-600/80 dark:text-emerald-400 mt-0.5">
                    Deterministic blend
                  </p>
                </div>
              </div>

              {/* Contributing Factors */}
              <div className="space-y-2">
                <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-200 flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4 text-indigo-500" />
                  Contributing Personalization Factors
                </h4>
                {data.factors && data.factors.length > 0 ? (
                  <div className="space-y-2">
                    {data.factors.map((f, idx) => (
                      <div
                        key={idx}
                        className="flex items-start gap-2.5 p-3 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/50"
                      >
                        {getFactorIcon(f)}
                        <div className="text-xs space-y-0.5">
                          <p className="font-medium text-gray-900 dark:text-gray-100">{f.summary}</p>
                          <p className="text-gray-500 dark:text-gray-400">{f.evidence_basis}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-500 dark:text-gray-400 italic">
                    No active personalization factors contributed to this recommendation.
                  </p>
                )}
              </div>

              {/* Summary Points */}
              {data.summary_points && data.summary_points.length > 0 && (
                <div className="p-3.5 bg-gray-50 dark:bg-gray-800/40 rounded-lg border border-gray-200 dark:border-gray-700/60 space-y-1.5">
                  <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                    Summary Notes
                  </div>
                  <ul className="text-xs text-gray-600 dark:text-gray-300 space-y-1 list-disc list-inside">
                    {data.summary_points.map((pt, idx) => (
                      <li key={idx}>{pt}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Safety & Academic Guarantee Banner */}
              <div className="p-3 bg-slate-50 dark:bg-slate-900/70 border border-slate-200 dark:border-slate-800 rounded-lg flex items-start gap-2.5">
                <Shield className="w-4 h-4 text-indigo-600 dark:text-indigo-400 shrink-0 mt-0.5" />
                <div className="text-xs text-slate-600 dark:text-slate-400 space-y-0.5">
                  <span className="font-semibold text-slate-900 dark:text-slate-200">
                    Academic Safety Guarantee:
                  </span>{" "}
                  Personalization influence is strictly bounded to ±15%. It can never override academic
                  eligibility, hard submission deadlines, or institutional risk constraints.
                </div>
              </div>

              {/* Footer Metadata */}
              <div className="pt-2 border-t border-gray-200 dark:border-gray-800 flex flex-wrap items-center justify-between text-[11px] text-gray-400">
                <span>Governance State: <strong>{data.governance_state}</strong></span>
                <span>Personalization Version: <strong>v{data.personalization_state_version}</strong></span>
                <span>Algorithm: <strong>v{data.algorithm_version}</strong></span>
              </div>
            </>
          )}
        </div>

        {/* Action Button */}
        <div className="mt-6 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
