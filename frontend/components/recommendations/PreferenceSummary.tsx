"use client";

import Link from "next/link";
import { useState } from "react";
import { X } from "lucide-react";
import { deleteResearcherPreference } from "../../services/api";
import type { ResearcherPreferenceItem } from "../../types/researcher";
import { preferenceCategoryLabel, preferenceLabel, strengthWord } from "../../utils/personalization";
import { IconButton } from "../ui/Button/Button";
import styles from "./Recommendations.module.css";

interface PreferenceSummaryProps {
  profileId: string;
  stated: ResearcherPreferenceItem[];
  inferred: ResearcherPreferenceItem[];
  /** After a stated preference is removed: reload what depends on it. */
  onRemoved: (item: ResearcherPreferenceItem) => void;
  /** What to announce; the panel keeps it, so it outlives this list's reload. */
  onNotice: (text: string) => void;
}

/**
 * What the researcher told the platform, and what it inferred from the calls they saved (plan
 * §12: only what the person did here, stated plainly). Stated preferences can be removed here and
 * edited on the preferences page; inferred ones say how strong they are and why, in the API's words.
 */
export function PreferenceSummary({ profileId, stated, inferred, onRemoved, onNotice }: PreferenceSummaryProps) {
  const [removing, setRemoving] = useState<string | null>(null);

  async function remove(item: ResearcherPreferenceItem) {
    setRemoving(item.id);
    try {
      await deleteResearcherPreference(profileId, item.id);
      onNotice(`Removed ${preferenceLabel(item)}.`);
      onRemoved(item);
    } catch {
      onNotice("That preference could not be removed. Try again.");
    } finally {
      setRemoving(null);
    }
  }

  return (
    <>
      <div className={styles.group}>
        <h3 className={styles.groupTitle}>What you told us</h3>
        {stated.length === 0 ? (
          <p className={styles.muted}>
            You have not stated any preferences. <Link href="/researcher/preferences">Add research preferences</Link>.
          </p>
        ) : (
          <ul className={styles.preferences}>
            {stated.map((item) => (
              <li key={item.id} className={styles.preference}>
                <span className={styles.preferenceText}>
                  <span className={styles.preferenceCategory}>{preferenceCategoryLabel(item.category)}</span>{" "}
                  {item.preference_type === "EXCLUDED" ? `Not ${preferenceLabel(item)}` : preferenceLabel(item)}
                </span>
                <IconButton
                  size="sm"
                  label={`Remove ${preferenceLabel(item)}`}
                  icon={<X size={16} aria-hidden="true" />}
                  disabled={removing !== null}
                  onClick={() => remove(item)}
                />
              </li>
            ))}
          </ul>
        )}
        <Link href="/researcher/preferences" className={styles.inlineLink}>
          Edit your research preferences
        </Link>
      </div>

      <div className={styles.group}>
        <h3 className={styles.groupTitle}>From your saved calls</h3>
        {inferred.length === 0 ? (
          <p className={styles.muted}>Nothing has been inferred yet: preferences are inferred only from calls you save to your workspace.</p>
        ) : (
          <ul className={styles.preferences}>
            {inferred.map((item) => (
              <li key={item.id} className={styles.preference}>
                <span className={styles.preferenceText}>
                  <span className={styles.preferenceCategory}>{preferenceCategoryLabel(item.category)}</span> {preferenceLabel(item)}
                  <span className={styles.preferenceStrength}> · {strengthWord(item.strength)}</span>
                  {item.provenance_reasons[0] && <span className={styles.preferenceWhy}>{item.provenance_reasons[0]}</span>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

    </>
  );
}
