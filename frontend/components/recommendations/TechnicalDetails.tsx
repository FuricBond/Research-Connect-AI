"use client";

import dynamic from "next/dynamic";
import { Component, useState, type ReactNode } from "react";
import type { PersonalizedRankingResponse, ResearcherPreferenceIntelligenceResponse } from "../../types/researcher";
import { SkeletonList } from "../ui/State/State";
import styles from "./Recommendations.module.css";

const loading = () => <SkeletonList rows={2} label="Loading" announce={false} />;
const RankingPart = dynamic(() => import("./technical/RankingPart"), { ssr: false, loading });
const ContextPart = dynamic(() => import("./technical/ContextPart"), { ssr: false, loading });
const SummaryPart = dynamic(() => import("./technical/SummaryPart"), { ssr: false, loading });
const CandidatesPart = dynamic(() => import("./technical/CandidatesPart"), { ssr: false, loading });
const SignalsPart = dynamic(() => import("./technical/SignalsPart"), { ssr: false, loading });
const CalibrationPart = dynamic(() => import("./technical/CalibrationPart"), { ssr: false, loading });
const QualityPart = dynamic(() => import("./technical/QualityPart"), { ssr: false, loading });
const HealthPart = dynamic(() => import("./technical/HealthPart"), { ssr: false, loading });
const FeedbackPart = dynamic(() => import("./technical/FeedbackPart"), { ssr: false, loading });
const HistoryPart = dynamic(() => import("./technical/HistoryPart"), { ssr: false, loading });
const ControlsPart = dynamic(() => import("./technical/ControlsPart"), { ssr: false, loading });
const PreferencesPart = dynamic(() => import("./technical/PreferencesPart"), { ssr: false, loading });

/** A part that cannot be shown says so, and the rest of the page carries on. */
class PartBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) return <p className={styles.muted}>This part could not be shown. Close it and open it again, or reload the page.</p>;
    return this.props.children;
  }
}

/** One part: closed until opened, and its code and data asked for only then. */
function Part({ title, children }: { title: string; children: () => ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <details className={styles.part} onToggle={(event) => setOpen((event.currentTarget as HTMLDetailsElement).open)}>
      <summary>
        <h3 className={styles.partTitle}>{title}</h3>
      </summary>
      {open && (
        <div className={styles.partBody}>
          <PartBoundary>{children()}</PartBoundary>
        </div>
      )}
    </details>
  );
}

interface TechnicalDetailsProps {
  profileId: string;
  /** The page's ranking, whose comparison with relevance alone needs no request of its own. */
  ranking: PersonalizedRankingResponse | null;
  /** The page's preference record, shown in full without a request of its own. */
  preferences: ResearcherPreferenceIntelligenceResponse | null;
  onRankingChanged: () => void;
}

/**
 * "Technical details" (plan §12, P0-4: nothing removed): every diagnostic the profile's
 * Recommendations, Personalization and History sections had — the ranking comparison, the
 * research context and its signals, the summary, the calls considered, learned signals,
 * calibration, quality, health and drift, the feedback log, the recommendation history and the
 * settings' audit log — restyled, each in a part of its own that loads when opened.
 */
export function TechnicalDetails({ profileId, ranking, preferences, onRankingChanged }: TechnicalDetailsProps) {
  return (
    <section className={styles.technical} aria-labelledby="technical-heading">
      <h2 id="technical-heading" className={styles.sectionTitle}>
        Technical details
      </h2>
      <p className={styles.technicalIntro}>
        The records behind the ranking, for anyone who wants to check it. Each part loads when you open it.
      </p>
      <div className={styles.parts}>
        <Part title="Ranking with and without personalization">{() => <RankingPart profileId={profileId} ranking={ranking} />}</Part>
        <Part title="Your research context">{() => <ContextPart profileId={profileId} />}</Part>
        <Part title="Personalization summary">{() => <SummaryPart profileId={profileId} />}</Part>
        <Part title="Your preferences in detail">{() => <PreferencesPart preferences={preferences} />}</Part>
        <Part title="Calls considered before ranking">{() => <CandidatesPart profileId={profileId} />}</Part>
        <Part title="Signals learned from your activity">{() => <SignalsPart profileId={profileId} />}</Part>
        <Part title="Calibration from your feedback">{() => <CalibrationPart profileId={profileId} />}</Part>
        <Part title="Quality of personalization">{() => <QualityPart profileId={profileId} />}</Part>
        <Part title="Health and drift">{() => <HealthPart profileId={profileId} />}</Part>
        <Part title="Your feedback">{() => <FeedbackPart profileId={profileId} onChanged={onRankingChanged} />}</Part>
        <Part title="Recommendation history">{() => <HistoryPart profileId={profileId} />}</Part>
        <Part title="Changes to your settings">{() => <ControlsPart profileId={profileId} />}</Part>
        <Part title="How the order is protected">
          {() => (
            <>
              <p className={styles.muted}>Each layer can only adjust what the one before it decided, and by a bounded amount:</p>
              <ol className={styles.plainList}>
                <li>The platform&apos;s safety rules.</li>
                <li>Eligibility.</li>
                <li>Relevance to your research: at least 85% of every score.</li>
                <li>Your stated preferences.</li>
                <li>Your controls on this page.</li>
                <li>Signals learned from your activity: at most ±10%.</li>
                <li>Calibration from your feedback: at most ±5%.</li>
                <li>Context: at most ±3%.</li>
              </ol>
            </>
          )}
        </Part>
      </div>
    </section>
  );
}
