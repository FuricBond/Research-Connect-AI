"use client";

import Link from "next/link";
import { useSession } from "../auth/SessionProvider";
import { APPLICANTS_HREF, MY_POSTINGS_HREF } from "../../utils/postings";
import styles from "./Faculty.module.css";

export type PostingsView = "discover" | "mine" | "applicants";

/**
 * The research postings' own pages, as links with `aria-current` (they are pages, not tabs):
 * Discover for everyone; My postings and Applicants for the accounts that may author postings
 * (FACULTY, ADMIN — the server's rule); My applications for every signed-in account, as before.
 * A visitor sees none (Discover is the only page open to them).
 */
export function PostingsNav({ current }: { current: PostingsView }) {
  const { status, hasRole } = useSession();
  if (status !== "authenticated") return null;
  const author = hasRole("FACULTY", "ADMIN");
  const links: { view: PostingsView | "applications"; href: string; label: string }[] = [
    { view: "discover", href: "/postings", label: "Discover" },
    ...(author
      ? [
          { view: "mine" as const, href: MY_POSTINGS_HREF, label: "My postings" },
          { view: "applicants" as const, href: APPLICANTS_HREF, label: "Applicants" },
        ]
      : []),
    { view: "applications", href: "/postings/applications", label: "My applications" },
  ];
  return (
    <nav aria-label="Research postings" className={styles.localNav}>
      <ul>
        {links.map((link) => (
          <li key={link.view}>
            <Link href={link.href} aria-current={link.view === current ? "page" : undefined} className={styles.localLink}>
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
