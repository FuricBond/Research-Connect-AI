"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useId } from "react";
import { useSession } from "../auth/SessionProvider";
import { currentHref, navigationFor } from "../../utils/navigation";
import styles from "./PrimaryNav.module.css";

/**
 * The primary navigation: the destinations this account may see, grouped by task, with the
 * current page marked by aria-current="page" (and visibly, by more than colour). Rendered in
 * the sidebar from 1024px and in the navigation drawer below.
 *
 * While the stored session is still being checked it shows placeholders, never the visitor's
 * navigation: a signed-in person would otherwise see their destinations appear late and the
 * visitor's list vanish.
 */
export function PrimaryNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname() ?? "/";
  const { status, role } = useSession();
  const baseId = useId();

  if (status === "loading") {
    return (
      <nav aria-label="Primary" aria-busy="true" className={styles.nav}>
        <div className={styles.placeholder} aria-hidden="true">
          {Array.from({ length: 7 }, (_, i) => (
            <span key={i} className={styles.placeholderRow} />
          ))}
        </div>
      </nav>
    );
  }

  const sections = navigationFor(status === "authenticated" ? role : null);
  const current = currentHref(pathname);

  return (
    <nav aria-label="Primary" className={styles.nav}>
      {sections.map((section) => {
        const labelId = `${baseId}-${section.group}`;
        return (
          <div key={section.group} className={styles.section}>
            {section.label && (
              <p id={labelId} className={styles.sectionLabel}>
                {section.label}
              </p>
            )}
            <ul className={styles.list} aria-labelledby={section.label ? labelId : undefined}>
              {section.items.map((item) => {
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={styles.link}
                      aria-current={item.href === current ? "page" : undefined}
                      onClick={onNavigate}
                    >
                      <Icon size={18} aria-hidden="true" className={styles.icon} />
                      <span className={styles.label}>{item.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}
