import styles from "./Workspace.module.css";

/**
 * A filter chip's count, after a space: "Saved (3)". While the count is unknown nothing is shown
 * or read (never a false zero), but a hidden placeholder of the same width keeps the chip's size,
 * so the chips do not rewrap and push the page down when the counts arrive.
 */
export function ChipCount({ count, className }: { count: number | null; className?: string }) {
  if (count === null) {
    return (
      <span className={`${styles.chipCount} ${styles.chipCountPending} ${className ?? ""}`} aria-hidden="true">
        {" (0)"}
      </span>
    );
  }
  return <span className={`${styles.chipCount} ${className ?? ""}`}> ({count})</span>;
}
