"use client";

import React, { useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Info,
  Loader2,
  MinusCircle,
  Shield,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { Button } from "../ui/Button/Button";
import { Dialog } from "../ui/Dialog/Dialog";
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

  const getImpactBadge = (impact: PersonalizationImpact) => {
    switch (impact) {
      case "STRONG_PERSONALIZATION":
        return {
          label: "Strong Personalization",
          badgeClass: "bg-purple-100 text-purple-800 border-purple-300",
          icon: <Sparkles className="w-4 h-4 mr-1 text-purple-600" />,
        };
      case "MODERATE_PERSONALIZATION":
        return {
          label: "Moderate Personalization",
          badgeClass: "bg-indigo-100 text-indigo-800 border-indigo-300",
          icon: <Sparkles className="w-4 h-4 mr-1 text-indigo-600" />,
        };
      case "LOW_PERSONALIZATION":
        return {
          label: "Low Personalization",
          badgeClass: "bg-blue-100 text-blue-800 border-blue-300",
          icon: <Info className="w-4 h-4 mr-1 text-blue-600" />,
        };
      case "PERSONALIZATION_SUPPRESSED":
        return {
          label: "Personalization Suppressed",
          badgeClass: "bg-amber-100 text-amber-800 border-amber-300",
          icon: <ShieldAlert className="w-4 h-4 mr-1 text-amber-600" />,
        };
      case "NO_PERSONALIZATION":
      default:
        return {
          label: "No Personalization Influence",
          badgeClass: "bg-gray-100 text-gray-700 border-gray-300",
          icon: <MinusCircle className="w-4 h-4 mr-1 text-gray-500" />,
        };
    }
  };

  // P6: the API sends the factors in four lists, each with a summary (no polarity), and a summary checklist.
  const getFactorIcon = (_factor: PersonalizationFactor) => <MinusCircle className="w-4 h-4 text-gray-400 shrink-0 mt-0.5" />;
  const factors: PersonalizationFactor[] = data
    ? [...(data.explicit_preference_factors ?? []), ...(data.adaptive_signal_factors ?? []), ...(data.calibration_factors ?? []), ...(data.contextual_factors ?? [])]
    : [];

  return (
    <Dialog
      open={isOpen}
      onClose={onClose}
      title="Why this recommendation?"
      description="How your preferences and activity shaped this result."
      size="lg"
      footer={
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
      }
    >
        <div className="space-y-5">
          {isLoading && (
            <div className="flex flex-col items-center justify-center py-12 text-gray-500">
              <Loader2 className="w-8 h-8 animate-spin text-indigo-600 mb-2" />
              <p className="text-sm font-medium">Loading personalization explanation...</p>
            </div>
          )}

          {error && (
            <div className="p-4 bg-rose-50 border border-rose-200 rounded-lg text-rose-800 text-sm">
              <p className="font-semibold flex items-center gap-1.5">
                <AlertCircle className="w-4 h-4" /> Error loading explanation
              </p>
              <p className="mt-1">The explanation is not available right now. Try again in a moment.</p>
            </div>
          )}

          {!isLoading && !error && data && (
            <>
              {/* Opportunity Title & Impact Badge */}
              <div className="bg-gray-50 p-4 rounded-lg border border-gray-200 space-y-2">
                <div className="text-xs tracking-wider font-semibold text-gray-500">
                  Opportunity
                </div>
                <h3 className="text-base font-semibold text-gray-900">
                  {data.opportunity_title}
                </h3>
                <div className="pt-2 flex items-center gap-2">
                  <span className="text-xs text-gray-500">Personalization Impact:</span>
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
                <div className="p-3 bg-blue-50/60 border border-blue-200 rounded-lg">
                  <div className="text-xs font-medium text-blue-700">
                    Core Base Relevance
                  </div>
                  <div className="text-2xl font-bold text-blue-900 mt-1">
                    {(data.base_relevance_score * 100).toFixed(0)}%
                  </div>
                  <p className="text-xs text-blue-600 mt-0.5">
                    85% baseline weight
                  </p>
                </div>

                <div className="p-3 bg-purple-50/60 border border-purple-200 rounded-lg">
                  <div className="text-xs font-medium text-purple-700">
                    Personalization Fit
                  </div>
                  <div className="text-2xl font-bold text-purple-900 mt-1">
                    {(data.personalization_score * 100).toFixed(0)}%
                  </div>
                  <p className="text-xs text-purple-600 mt-0.5">
                    15% bounded weight
                  </p>
                </div>

                <div className="p-3 bg-emerald-50/60 border border-emerald-200 rounded-lg">
                  <div className="text-xs font-medium text-emerald-700">
                    Final Ranking Score
                  </div>
                  <div className="text-2xl font-bold text-emerald-900 mt-1">
                    {(data.final_score * 100).toFixed(0)}%
                  </div>
                  <p className="text-xs text-emerald-600 mt-0.5">
                    Deterministic blend
                  </p>
                </div>
              </div>

              {/* Contributing Factors */}
              <div className="space-y-2">
                <h4 className="text-sm font-semibold text-gray-800 flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4 text-indigo-500" />
                  Contributing Personalization Factors
                </h4>
                {factors.length > 0 ? (
                  <div className="space-y-2">
                    {factors.map((f, idx) => (
                      <div
                        key={idx}
                        className="flex items-start gap-2.5 p-3 rounded-lg border border-gray-200 bg-white"
                      >
                        {getFactorIcon(f)}
                        <div className="text-xs space-y-0.5">
                          <p className="font-medium text-gray-900">{f.summary}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-500 italic">
                    No active personalization factors contributed to this recommendation.
                  </p>
                )}
              </div>

              {/* Summary Points */}
              {data.contributing_factors_summary && data.contributing_factors_summary.length > 0 && (
                <div className="p-3.5 bg-gray-50 rounded-lg border border-gray-200 space-y-1.5">
                  <div className="text-xs font-semibold text-gray-700 tracking-wide">
                    Summary Notes
                  </div>
                  <ul className="text-xs text-gray-600 space-y-1 list-disc list-inside">
                    {data.contributing_factors_summary.map((pt, idx) => (
                      <li key={idx}>{pt}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Safety & Academic Guarantee Banner */}
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg flex items-start gap-2.5">
                <Shield className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
                <div className="text-xs text-slate-600 space-y-0.5">
                  <span className="font-semibold text-slate-900">
                    Academic Safety Guarantee:
                  </span>{" "}
                  Personalization influence is strictly bounded to ±15%. It can never override academic
                  eligibility, hard submission deadlines, or institutional risk constraints.
                </div>
              </div>

              {/* Footer Metadata */}
              <details className="pt-2 border-t border-gray-200 text-xs text-gray-500">
                <summary className="cursor-pointer">Technical details</summary>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                  <span>Governance state: <strong>{data.governance_state}</strong></span>
                  <span>Personalization version: <strong>v{data.personalization_state_version}</strong></span>
                  <span>Algorithm: <strong>v{data.algorithm_version}</strong></span>
                </div>
              </details>
            </>
          )}
        </div>

    </Dialog>
  );
};
