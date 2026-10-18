import Link from "next/link";
import styles from "./Workspace.module.css";

/**
 * Calls | Submissions (plan §13). They are two pages, so these are links with `aria-current`,
 * not tabs (DESIGN_SYSTEM.md §8.3: tabs are views of one object, never page navigation).
 */
export function WorkspaceNav({ current }: { current: "calls" | "submissions" }) {
  return (
    <nav aria-label="Workspace" className={styles.localNav}>
      <ul>
        <li>
          <Link href="/workspace" aria-current={current === "calls" ? "page" : undefined} className={styles.localLink}>
            Calls
          </Link>
        </li>
        <li>
          <Link href="/submissions" aria-current={current === "submissions" ? "page" : undefined} className={styles.localLink}>
            Submissions
          </Link>
        </li>
      </ul>
    </nav>
  );
}
