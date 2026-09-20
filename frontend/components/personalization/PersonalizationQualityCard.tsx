"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Activity,
  AlertCircle,
  ArrowDownRight,
  ArrowUpRight,
  Award,
  BarChart3,
  CheckCircle2,
  Clock,
  Compass,
  HelpCircle,
  Info,
  Layers,
  RefreshCw,
  Scale,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  TrendingUp,
  XCircle,
} from "lucide-react";
import {
  fetchPersonalizationQuality,
  recomputePersonalizationQuality,
} from "../../services/api";
import type {
  ContextualSummaryItem,
  PersonalizationQualityResponse,
  QualityEvaluationState,
} from "../../types/personalization";

interface PersonalizationQualityCardProps {
  profileId: string;
  userId?: string;
  className?: string;
}

export const PersonalizationQualityCard: React.FC<PersonalizationQualityCardProps> = ({
  profileId,
  userId,
  className = "",
}) => {
  const [data, setData] = useState<PersonalizationQualityResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRecomputing, setIsRecomputing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [activeContextFilter, setActiveContextFilter] = useState<string>("ALL");

  const loadQualityData = useCallback(async () => {
    if (!profileId) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetchPersonalizationQuality(profileId, userId);
      setData(res);
    } catch (err: unknown) {
      console.error("Failed to load personalization quality:", err);
      setError(err instanceof Error ? err.message : "Failed to load quality data");
    } finally {
      setIsLoading(false);
    }
  }, [profileId, userId]);

  useEffect(() => {
    loadQualityData();
  }, [loadQualityData]);

  const handleRecompute = async () => {
    if (!profileId || isRecomputing) return;
    setIsRecomputing(true);
    setError(null);
    try {
      const res = await recomputePersonalizationQuality(profileId, undefined, userId);
      setData(res);
    } catch (err: unknown) {
      console.error("Failed to recompute quality evaluation:", err);
      setError(err instanceof Error ? err.message : "Failed to recompute quality");
    } finally {
      setIsRecomputing(false);
    }
  };

  const getStateBadge = (state: QualityEvaluationState) => {
    switch (state) {
      case "POSITIVE":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
            <TrendingUp className="w-3 h-3" />
            Positive Lift
          </span>
        );
      case "NEGATIVE":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20">
            <TrendingDown className="w-3 h-3" />
            Negative Change
          </span>
        );
      case "MIXED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
            <Scale className="w-3 h-3" />
            Mixed Outcomes
          </span>
        );
      case "STABLE":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
            <CheckCircle2 className="w-3 h-3" />
            Stable
          </span>
        );
      case "EARLY_SIGNAL":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            <Clock className="w-3 h-3" />
            Early Signal
          </span>
        );
      case "EVALUATING":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20">
            <Activity className="w-3 h-3" />
            Evaluating
          </span>
        );
      case "INSUFFICIENT_DATA":
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-500/10 text-slate-600 dark:text-slate-400 border border-slate-500/20">
            <HelpCircle className="w-3 h-3" />
            Insufficient Evidence
          </span>
        );
    }
  };

  const evaluation = data?.evaluation;
  const contextSummaries = data?.context_summaries || [];

  // Group context summaries by dimension
  const contextDimensions = Array.from(new Set(contextSummaries.map((c) => c.context_dimension)));

  const filteredContexts = activeContextFilter === "ALL"
    ? contextSummaries
    : contextSummaries.filter((c) => c.context_dimension === activeContextFilter);

  return (
    <div
      className={`bg-card/90 backdrop-blur-md rounded-2xl border border-border/60 shadow-lg p-6 transition-all duration-300 ${className}`}
      id="personalization-quality-card"
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-border/50">
        <div className="flex items-start gap-3">
          <div className="p-2.5 rounded-xl bg-primary/10 text-primary border border-primary/20">
            <BarChart3 className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold text-foreground tracking-tight">
                Personalization Quality & Contextual Adaptation
              </h3>
              <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-primary/15 text-primary">
                Phase 5.7
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Deterministic evaluation of personalization usefulness, observed lift, and bounded contextual adaptation.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleRecompute}
            disabled={isRecomputing || isLoading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-secondary hover:bg-secondary/80 text-secondary-foreground border border-border/60 transition-colors disabled:opacity-50"
            title="Recompute quality evaluation from latest interaction history"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRecomputing ? "animate-spin" : ""}`} />
            {isRecomputing ? "Evaluating..." : "Re-evaluate"}
          </button>
        </div>
      </div>

      {/* Loading & Error States */}
      {isLoading ? (
        <div className="py-12 flex flex-col items-center justify-center gap-3 text-muted-foreground">
          <RefreshCw className="w-6 h-6 animate-spin text-primary" />
          <span className="text-sm">Evaluating personalization quality metrics...</span>
        </div>
      ) : error ? (
        <div className="py-8 px-4 my-4 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive flex items-center gap-3">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <span className="text-sm font-medium">{error}</span>
        </div>
      ) : !evaluation ? (
        <div className="py-8 text-center text-muted-foreground text-sm">
          No quality evaluation data available for this researcher.
        </div>
      ) : (
        <div className="space-y-6 pt-6">
          {/* Summary Stat Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {/* Observed Personalization Lift */}
            <div className="p-3.5 rounded-xl bg-secondary/30 border border-border/50 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Observed Lift</span>
                <Sparkles className="w-3.5 h-3.5 text-primary" />
              </div>
              <div className="mt-2 flex items-baseline gap-1.5">
                <span className={`text-xl font-extrabold ${evaluation.observed_personalization_lift > 0 ? "text-emerald-600 dark:text-emerald-400" : evaluation.observed_personalization_lift < 0 ? "text-rose-600 dark:text-rose-400" : "text-foreground"}`}>
                  {evaluation.observed_personalization_lift > 0 ? "+" : ""}
                  {(evaluation.observed_personalization_lift * 100).toFixed(1)}%
                </span>
                <span className="text-xs text-muted-foreground">vs baseline</span>
              </div>
              <span className="text-[10px] text-muted-foreground mt-1">Empirical observation</span>
            </div>

            {/* Engagement Rate */}
            <div className="p-3.5 rounded-xl bg-secondary/30 border border-border/50 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Engagement Rate</span>
                <Activity className="w-3.5 h-3.5 text-blue-500" />
              </div>
              <div className="mt-2 flex items-baseline gap-1.5">
                <span className="text-xl font-extrabold text-foreground">
                  {(evaluation.observed_engagement_rate * 100).toFixed(1)}%
                </span>
                <span className="text-xs text-muted-foreground">
                  ({evaluation.attributed_interactions_count}/{evaluation.recommendations_evaluated_count})
                </span>
              </div>
              <span className="text-[10px] text-muted-foreground mt-1">Interacted / Exposed</span>
            </div>

            {/* Positive vs Negative Feedback */}
            <div className="p-3.5 rounded-xl bg-secondary/30 border border-border/50 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Positive / Negative</span>
                <Scale className="w-3.5 h-3.5 text-amber-500" />
              </div>
              <div className="mt-2 flex items-baseline gap-1.5">
                <span className="text-xl font-extrabold text-emerald-600 dark:text-emerald-400">
                  {evaluation.positive_outcomes_count}
                </span>
                <span className="text-muted-foreground text-xs">/</span>
                <span className="text-xl font-extrabold text-rose-600 dark:text-rose-400">
                  {evaluation.negative_outcomes_count}
                </span>
              </div>
              <span className="text-[10px] text-muted-foreground mt-1">
                {(evaluation.observed_positive_rate * 100).toFixed(0)}% pos rate
              </span>
            </div>

            {/* Diversity & Novelty */}
            <div className="p-3.5 rounded-xl bg-secondary/30 border border-border/50 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Diversity / Novelty</span>
                <Compass className="w-3.5 h-3.5 text-indigo-500" />
              </div>
              <div className="mt-2 flex items-baseline gap-1.5">
                <span className="text-xl font-extrabold text-foreground">
                  {(evaluation.diversity_score * 100).toFixed(0)}%
                </span>
                <span className="text-muted-foreground text-xs">/</span>
                <span className="text-base font-semibold text-muted-foreground">
                  {(evaluation.novelty_rate * 100).toFixed(0)}%
                </span>
              </div>
              <span className="text-[10px] text-muted-foreground mt-1">Diversity / Novelty</span>
            </div>
          </div>

          {/* Explanation Banner */}
          <div className="p-4 rounded-xl bg-primary/5 border border-primary/15 flex items-start gap-3">
            <Info className="w-5 h-5 text-primary shrink-0 mt-0.5" />
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-primary">
                  Evaluation Summary
                </span>
                {getStateBadge(evaluation.evaluation_state)}
              </div>
              <p className="text-xs text-foreground/90 leading-relaxed">
                {evaluation.deterministic_explanation}
              </p>
            </div>
          </div>

          {/* Precedence Hierarchy Indicator */}
          <div className="p-3 rounded-xl bg-muted/40 border border-border/40 text-[11px] text-muted-foreground flex flex-wrap items-center gap-2">
            <span className="font-semibold text-foreground">Architecture Pipeline:</span>
            <span className="px-1.5 py-0.5 rounded bg-background border border-border/60">Explicit Preferences</span>
            <span>→</span>
            <span className="px-1.5 py-0.5 rounded bg-background border border-border/60">Adaptive Signals</span>
            <span>→</span>
            <span className="px-1.5 py-0.5 rounded bg-background border border-border/60">Calibration</span>
            <span>→</span>
            <span className="px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 font-medium">Quality Evaluation</span>
            <span>→</span>
            <span className="px-1.5 py-0.5 rounded bg-background border border-border/60">Contextual Adaptation (±0.03)</span>
          </div>

          {/* Contextual Breakdown Section */}
          <div className="space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-primary" />
                <h4 className="text-sm font-semibold text-foreground">
                  Contextual Performance Breakdown
                </h4>
              </div>

              {/* Dimension Filter Tabs */}
              {contextDimensions.length > 0 && (
                <div className="flex items-center gap-1 overflow-x-auto pb-1 sm:pb-0">
                  <button
                    onClick={() => setActiveContextFilter("ALL")}
                    className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${activeContextFilter === "ALL" ? "bg-primary text-primary-foreground" : "bg-muted hover:bg-muted/80 text-muted-foreground"}`}
                  >
                    All Contexts
                  </button>
                  {contextDimensions.map((dim) => (
                    <button
                      key={dim}
                      onClick={() => setActiveContextFilter(dim)}
                      className={`px-2.5 py-1 text-xs rounded-md font-medium whitespace-nowrap transition-colors ${activeContextFilter === dim ? "bg-primary text-primary-foreground" : "bg-muted hover:bg-muted/80 text-muted-foreground"}`}
                    >
                      {dim.replace("_", " ")}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Context Cards Grid */}
            {filteredContexts.length === 0 ? (
              <div className="py-6 text-center text-xs text-muted-foreground border border-dashed border-border/60 rounded-xl">
                No context breakdown data available for this dimension.
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {filteredContexts.map((ctx, idx) => (
                  <div
                    key={`${ctx.context_dimension}-${ctx.context_value}-${idx}`}
                    className="p-3.5 rounded-xl bg-card border border-border/60 hover:border-primary/30 transition-all flex flex-col justify-between gap-2"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-1 mb-1">
                        <span className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">
                          {ctx.context_dimension.replace("_", " ")}
                        </span>
                        {getStateBadge(ctx.evaluation_state)}
                      </div>
                      <h5 className="text-sm font-bold text-foreground">
                        {ctx.context_value}
                      </h5>
                    </div>

                    <div className="pt-2 border-t border-border/40 flex items-center justify-between text-xs">
                      <div>
                        <span className="text-muted-foreground">Lift: </span>
                        <span className={`font-bold ${ctx.observed_lift > 0 ? "text-emerald-600 dark:text-emerald-400" : ctx.observed_lift < 0 ? "text-rose-600 dark:text-rose-400" : "text-foreground"}`}>
                          {ctx.observed_lift > 0 ? "+" : ""}
                          {(ctx.observed_lift * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Sample: </span>
                        <span className="font-semibold text-foreground">{ctx.sample_size}</span>
                      </div>
                    </div>

                    <p className="text-[11px] text-muted-foreground line-clamp-2 leading-normal">
                      {ctx.explanation}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
