/** Where a tab remembers its chosen papers (hooks/useSelectedWork.ts). On its own for sign-out. */
export const SESSION_KEY = "rc_selected_work";
export const KNOWN_KEY = "rc_known_papers";
export const ORIGIN_KEY = "rc_paper_origin";

export function clearSelectedWork(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(SESSION_KEY);
    window.sessionStorage.removeItem(KNOWN_KEY);
    window.sessionStorage.removeItem(ORIGIN_KEY);
  } catch {
    // ignore
  }
}
