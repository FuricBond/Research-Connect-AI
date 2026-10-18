"use client";

import { useEffect, useId, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import {
  applyThemePreference,
  readThemePreference,
  watchSystemTheme,
  watchThemePreference,
  type ThemePreference,
} from "../../../utils/theme";
import styles from "./ThemeSwitcher.module.css";

const OPTIONS: { value: ThemePreference; label: string; Icon: typeof Sun }[] = [
  { value: "system", label: "Match system theme", Icon: Monitor },
  { value: "light", label: "Light theme", Icon: Sun },
  { value: "dark", label: "Dark theme", Icon: Moon },
];

/**
 * Light, dark or system. Native radios (arrow keys move between them); the choice is stored
 * and applied at once. While "system" is chosen, an OS change is followed live.
 */
export function ThemeSwitcher({ className }: { className?: string }) {
  const name = `theme-${useId()}`;
  // The inline script in <head> already applied the stored choice; read it after mount.
  const [preference, setPreference] = useState<ThemePreference>("system");
  useEffect(() => setPreference(readThemePreference()), []);
  // Another theme control (Settings → Appearance) may change it while this one is mounted.
  useEffect(() => watchThemePreference(setPreference), []);

  useEffect(() => {
    if (preference !== "system") return;
    return watchSystemTheme(() => applyThemePreference("system"));
  }, [preference]);

  return (
    <fieldset className={`${styles.group} ${className ?? ""}`}>
      <legend className="rc-visually-hidden">Colour theme</legend>
      {OPTIONS.map(({ value, label, Icon }) => (
        <label key={value} className={styles.option} title={label}>
          <input
            type="radio"
            name={name}
            value={value}
            checked={preference === value}
            aria-label={label}
            onChange={() => {
              setPreference(value);
              applyThemePreference(value);
            }}
          />
          <span className={styles.face} aria-hidden="true">
            <Icon size={15} />
          </span>
        </label>
      ))}
    </fieldset>
  );
}
