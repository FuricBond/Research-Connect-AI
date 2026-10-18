import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";
import styles from "./Breadcrumb.module.css";

export interface Crumb {
  label: string;
  /** Where the crumb leads; omitted for a crumb that only names the context (the paper). */
  href?: string;
}

/**
 * Where a detail page sits: "Search › Paper title › Similar papers". DESIGN_SYSTEM.md §8.3.
 * `nav aria-label="Breadcrumb"`, an ordered list, the last crumb is the current page. Below
 * 640px only the way back is shown ("‹ Search"), so a long title never crowds a phone.
 */
export function Breadcrumb({ items, current }: { items: Crumb[]; current: string }) {
  const parent = [...items].reverse().find((item) => item.href);
  return (
    <nav aria-label="Breadcrumb" className={styles.nav}>
      <ol className={styles.list}>
        {items.map((item, i) => (
          <li key={`${i}-${item.label}`} className={styles.item}>
            {item.href ? (
              <Link href={item.href} className={styles.link}>
                {item.label}
              </Link>
            ) : (
              <span className={styles.context}>{item.label}</span>
            )}
            <ChevronRight size={14} className={styles.separator} aria-hidden="true" />
          </li>
        ))}
        <li className={styles.item}>
          <span aria-current="page" className={styles.current}>
            {current}
          </span>
        </li>
      </ol>
      {parent?.href && (
        <Link href={parent.href} className={styles.back}>
          <ChevronLeft size={16} aria-hidden="true" />
          {parent.label}
        </Link>
      )}
    </nav>
  );
}
