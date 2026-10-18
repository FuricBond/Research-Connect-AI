import { Check } from "lucide-react";
import { cx } from "../../utils/cx";
import styles from "./Research.module.css";

/**
 * Research topics as quiet, non-interactive tags (DESIGN_SYSTEM.md §9 ResearchTopicTag). `shared`
 * topics — also in the query or the chosen paper — carry a check and the brand tint, and say so.
 */
export function TopicTags({ topics, shared = false, label }: { topics: string[]; shared?: boolean; label: string }) {
  if (topics.length === 0) return null;
  return (
    <ul className={styles.tags} aria-label={label}>
      {topics.map((topic) => (
        <li key={topic} className={cx(styles.tag, shared && styles.tagShared)}>
          {shared && <Check size={12} aria-hidden="true" />}
          {topic}
        </li>
      ))}
    </ul>
  );
}
