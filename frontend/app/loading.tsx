import { Loader2 } from "lucide-react";
import styles from "./loading.module.css";

/**
 * Next.js loading.tsx — shown automatically while a page loads. Server Component.
 *
 * P3: the design system's "structure unknown" state (DESIGN_SYSTEM.md §10): a small spinner and
 * one line of text, appearing only after 300ms so a quick page change does not flash it.
 */
export default function Loading() {
  return (
    <div className={styles.loading} role="status">
      <Loader2 size={16} className={styles.spinner} aria-hidden="true" />
      <span>Loading…</span>
    </div>
  );
}
