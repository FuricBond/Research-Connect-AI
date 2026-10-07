/**
 * Colour theme (DESIGN_SYSTEM.md §3.1).
 *
 * The person chooses light, dark or system; "system" follows the operating system. The choice
 * is kept in localStorage and resolved to data-theme="light" | "dark" on the root element —
 * before first paint by THEME_INIT_SCRIPT, and afterwards by applyThemePreference. Styles key
 * only off data-theme, so what a page looks like never depends on the OS by accident.
 */

export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "rc-theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

export function isThemePreference(value: unknown): value is ThemePreference {
  return value === "system" || value === "light" || value === "dark";
}

export function resolveTheme(preference: ThemePreference, systemPrefersDark: boolean): ResolvedTheme {
  if (preference === "system") return systemPrefersDark ? "dark" : "light";
  return preference;
}

export function readThemePreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(stored) ? stored : "system";
  } catch {
    return "system";
  }
}

export function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(DARK_QUERY).matches;
}

/** Applies a preference to the document and remembers it. */
export function applyThemePreference(preference: ThemePreference): ResolvedTheme {
  const resolved = resolveTheme(preference, systemPrefersDark());
  const root = document.documentElement;
  root.dataset.theme = resolved;
  root.dataset.themePreference = preference;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Storage can be blocked; the choice still applies for this page view.
  }
  return resolved;
}

/** Calls `onChange` when the OS switches between light and dark. Returns an unsubscribe. */
export function watchSystemTheme(onChange: () => void): () => void {
  if (typeof window.matchMedia !== "function") return () => undefined;
  const query = window.matchMedia(DARK_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/**
 * Runs in <head> before the body is painted, so the first frame already has the right theme.
 * Kept dependency-free and tolerant of blocked storage.
 */
export const THEME_INIT_SCRIPT = `(function(){var r=document.documentElement,p="system";try{var s=localStorage.getItem("${THEME_STORAGE_KEY}");if(s==="light"||s==="dark"||s==="system")p=s}catch(e){}var d=p==="dark"||(p==="system"&&window.matchMedia&&window.matchMedia("${DARK_QUERY}").matches);r.setAttribute("data-theme",d?"dark":"light");r.setAttribute("data-theme-preference",p)})();`;
