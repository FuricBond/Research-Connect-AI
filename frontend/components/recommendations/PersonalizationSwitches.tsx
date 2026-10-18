"use client";

import { useState } from "react";
import { updatePersonalizationSettings } from "../../services/api";
import type { ResearcherPersonalizationSettings, ResearcherPersonalizationSettingsUpdate } from "../../types/personalization";
import { Switch } from "../ui/Field/Field";
import styles from "./Recommendations.module.css";

type SettingKey = keyof ResearcherPersonalizationSettingsUpdate;

interface PersonalizationSwitchesProps {
  profileId: string;
  settings: ResearcherPersonalizationSettings;
  /** The saved settings, after a switch changed them. */
  onSaved: (settings: ResearcherPersonalizationSettings) => void;
}

/**
 * The three personalization settings (Phase 5.6), each applied at once. What each one does is
 * said in plain words, as the settings card said it before P6; using learned signals depends on
 * personalization being on, as the server applies it.
 */
export function PersonalizationSwitches({ profileId, settings, onSaved }: PersonalizationSwitchesProps) {
  const [saving, setSaving] = useState<SettingKey | null>(null);
  const [notice, setNotice] = useState("");

  async function change(key: SettingKey, value: boolean, done: string) {
    setSaving(key);
    try {
      onSaved(await updatePersonalizationSettings(profileId, { [key]: value }));
      setNotice(done);
    } catch {
      setNotice("The setting could not be changed. Try again.");
    } finally {
      setSaving(null);
    }
  }

  const on = settings.personalization_enabled;
  return (
    <div className={styles.group}>
      <h3 className={styles.groupTitle}>Your controls</h3>
      <Switch
        label="Personalize my recommendations"
        description="Off: calls are ranked by relevance to your research alone."
        checked={on}
        disabled={saving !== null}
        onChange={(value) => change("personalization_enabled", value, value ? "Personalization is on." : "Personalization is off.")}
      />
      <Switch
        label="Use what I have done here"
        description={
          on
            ? "Lets what was learned from your saves and feedback adjust the order. Off: only the preferences you stated are used."
            : "Applies only while personalization is on."
        }
        checked={settings.adaptive_signals_enabled}
        disabled={saving !== null || !on}
        onChange={(value) => change("adaptive_signals_enabled", value, value ? "Learned signals are used." : "Learned signals are not used.")}
      />
      <Switch
        label="Keep learning from new activity"
        description="New saves, feedback and dismissals update what was learned. Paused: it stays as it is."
        stateLabels={["On", "Paused"]}
        checked={settings.feedback_learning_enabled}
        disabled={saving !== null}
        onChange={(value) => change("feedback_learning_enabled", value, value ? "Learning from new activity." : "Learning is paused.")}
      />
      <p role="status" className={styles.notice}>
        {notice}
      </p>
    </div>
  );
}
