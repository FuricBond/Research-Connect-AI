import Link from "next/link";
import styles from "./VisitorIntro.module.css";

/**
 * P3 — the signed-out landing's one line: what a visitor can do here, and what an account adds.
 * Shown under the search before a first search, so it never moves the search box.
 */
export function VisitorIntro() {
  return (
    <p className={styles.intro}>
      Searching is open to everyone. <Link href="/login">Sign in</Link> or <Link href="/register">create an account</Link> to save
      papers, track calls for papers and get recommendations.
    </p>
  );
}
