import type { ReactNode } from "react";
import styles from "./Details.module.css";

/** One term and its value in a definition list (every pair in its own group, as HTML allows). */
export function Fact({ term, value }: { term: string; value: ReactNode }) {
  return (
    <div className={styles.factRow}>
      <dt>{term}</dt>
      <dd>{value}</dd>
    </div>
  );
}
