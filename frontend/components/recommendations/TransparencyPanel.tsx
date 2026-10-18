"use client";

import { useEffect, useState } from "react";
import type { ApiResource } from "../../hooks/useApiResource";
import type { ResearcherPersonalizationSettings } from "../../types/personalization";
import type { ResearcherPreferenceIntelligenceResponse } from "../../types/researcher";
import { ErrorState, SkeletonList } from "../ui/State/State";
import { PersonalizationSwitches } from "./PersonalizationSwitches";
import { PreferenceSummary } from "./PreferenceSummary";
import { ResetPersonalization } from "./ResetPersonalization";
import styles from "./Recommendations.module.css";

interface TransparencyPanelProps {
  profileId: string;
  preferences: ApiResource<ResearcherPreferenceIntelligenceResponse>;
  settings: ApiResource<ResearcherPersonalizationSettings>;
  /** After anything here changed the ranking: a removed preference, a setting, a reset. */
  onRankingChanged: () => void;
}

/**
 * "What shapes your recommendations" (plan §12, DESIGN_SYSTEM.md §18): the preferences the
 * researcher stated and the ones inferred from their saves, the switches that decide how much
 * either counts, and a reset. Its parts appear together once both requests have answered, so none
 * moves another (CLS); after that each fails on, and is retried from, only its own request.
 */
export function TransparencyPanel({ profileId, preferences, settings, onRankingChanged }: TransparencyPanelProps) {
  const [changedSettings, setChangedSettings] = useState<ResearcherPersonalizationSettings | null>(null);
  const shownSettings = changedSettings ?? settings.data;
  // While the preferences reload after a change, the last list stays (less what was removed), so
  // the panel does not jump and the confirmation is not lost with it.
  const [lastPreferences, setLastPreferences] = useState<ResearcherPreferenceIntelligenceResponse | null>(null);
  const [removed, setRemoved] = useState<Set<string>>(() => new Set());
  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (preferences.data) setLastPreferences(preferences.data);
  }, [preferences.data]);
  const shownPreferences = preferences.data ?? (preferences.status === "loading" ? lastPreferences : null);
  const active = (items: ResearcherPreferenceIntelligenceResponse["explicit_preferences"]) => items.filter((item) => item.is_active && !removed.has(item.id));
  const pending = (resource: ApiResource<unknown>) => resource.status === "loading" || resource.status === "idle";
  const settling = !lastPreferences && (pending(preferences) || pending(settings));

  return (
    <section className={styles.panel} aria-labelledby="shapes-heading">
      <h2 id="shapes-heading" className={styles.panelTitle}>
        What shapes your recommendations
      </h2>

      {settling ? (
        <SkeletonList rows={6} label="Loading what shapes your recommendations" />
      ) : (
        <>
          {shownPreferences ? (
            <PreferenceSummary
              profileId={profileId}
              stated={active(shownPreferences.explicit_preferences ?? [])}
              inferred={active(shownPreferences.inferred_preferences ?? [])}
              onNotice={setNotice}
              onRemoved={(item) => {
                setRemoved((current) => new Set(current).add(item.id));
                preferences.retry();
                onRankingChanged();
              }}
            />
          ) : pending(preferences) ? (
            <SkeletonList rows={3} label="Loading your preferences" />
          ) : (
            <ErrorState bare title="Your preferences could not be loaded" onRetry={preferences.retry} />
          )}
          <p role="status" className={styles.notice}>
            {notice}
          </p>

          {pending(settings) ? (
            <SkeletonList rows={3} label="Loading your personalization settings" />
          ) : !shownSettings ? (
            <ErrorState bare title="Your personalization settings could not be loaded" onRetry={settings.retry} />
          ) : (
            <PersonalizationSwitches
              profileId={profileId}
              settings={shownSettings}
              onSaved={(next) => {
                setChangedSettings(next);
                onRankingChanged();
              }}
            />
          )}

          <ResetPersonalization
            profileId={profileId}
            onReset={() => {
              preferences.retry();
              onRankingChanged();
            }}
          />
        </>
      )}
    </section>
  );
}
