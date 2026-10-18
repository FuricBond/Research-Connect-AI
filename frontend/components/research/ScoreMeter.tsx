import styles from "./Research.module.css";

interface ScoreMeterProps {
  /** The signal's name in words ("Meaning"). */
  name: string;
  /** 0–1, as the API returns it. */
  score: number;
  /** The backend's own word for the score ("Very strong"), when it gives one. */
  assessment?: string | null;
  /** One sentence on what the signal measures. */
  description?: string | null;
  /** False when the backend had no data for this signal: said in words, never drawn as a zero. */
  available?: boolean;
}

/**
 * One ranking signal as a bar from 0 to 100 (DESIGN_SYSTEM.md §8.5). The text carries the
 * meaning — "Meaning: 76 out of 100, very strong" — so the bar is decoration for sighted readers
 * and hidden from assistive technology. Drawn in SVG so the width is not an inline style.
 */
export function ScoreMeter({ name, score, assessment, description, available = true }: ScoreMeterProps) {
  const value = available ? Math.round(Math.min(1, Math.max(0, score)) * 100) : 0;
  return (
    <div className={styles.meter}>
      <div className={styles.meterText}>
        <span className={styles.meterName}>{name}</span>
        <span className={styles.meterValue}>
          {available ? `${value} out of 100${assessment ? `, ${assessment.toLowerCase()}` : ""}` : "Not available for this item"}
        </span>
      </div>
      <svg className={styles.meterBar} viewBox="0 0 100 6" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <rect className={styles.meterTrack} x="0" y="0" width="100" height="6" rx="3" />
        {value > 0 && <rect className={styles.meterFill} x="0" y="0" width={value} height="6" rx="3" />}
      </svg>
      {description && <p className={styles.meterAbout}>{description}</p>}
    </div>
  );
}
