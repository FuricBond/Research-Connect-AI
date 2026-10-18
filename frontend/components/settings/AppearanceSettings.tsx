"use client";

import { useEffect, useState } from "react";
import {
  applyThemePreference,
  readThemePreference,
  resolveTheme,
  systemPrefersDark,
  watchSystemTheme,
  watchThemePreference,
  type ThemePreference,
} from "../../utils/theme";
import { RadioGroup } from "../ui/Field/Field";
import styles from "./SettingsPage.module.css";

const WORDS = { light: "light", dark: "dark" } as const;

/**
 * P8 — Settings → Appearance (plan P11's control, here): match the system, light or dark. The
 * choice applies at once and is kept in this browser (`rc-theme`, applied before first paint on
 * every page, DESIGN_SYSTEM.md §3.1); the account menu's switch shows the same choice.
 */
export function AppearanceSettings() {
  const [preference, setPreference] = useState<ThemePreference>("system");
  const [systemDark, setSystemDark] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    setPreference(readThemePreference());
    setSystemDark(systemPrefersDark());
    return watchThemePreference(setPreference);
  }, []);

  useEffect(
    () =>
      watchSystemTheme(() => {
        setSystemDark(systemPrefersDark());
        if (readThemePreference() === "system") applyThemePreference("system");
      }),
    []
  );

  const choose = (value: string) => {
    const next = value as ThemePreference;
    const resolved = applyThemePreference(next);
    setPreference(next);
    setMessage(next === "system" ? `Matching the system: ${WORDS[resolved]} theme.` : `${resolved === "dark" ? "Dark" : "Light"} theme.`);
  };

  return (
    <div className={styles.stack}>
      <RadioGroup
        legend="Colour theme"
        name="settings-theme"
        value={preference}
        onChange={choose}
        options={[
          { value: "system", label: "Match the system", hint: `Follows this device's setting (now ${WORDS[resolveTheme("system", systemDark)]}).` },
          { value: "light", label: "Light" },
          { value: "dark", label: "Dark" },
        ]}
      />
      <p className={styles.note}>Kept in this browser; other devices keep their own choice.</p>
      <p role="status" className="rc-visually-hidden">
        {message}
      </p>
    </div>
  );
}
