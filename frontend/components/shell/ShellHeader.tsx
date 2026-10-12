"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { GraduationCap, Menu } from "lucide-react";
import { useSession } from "../auth/SessionProvider";
import { IconButton } from "../ui/Button/Button";
import { AccountMenu } from "./AccountMenu";
import { GlobalSearch } from "./GlobalSearch";
import { NotificationBell } from "./NotificationBell";
import styles from "./ShellHeader.module.css";

/**
 * The header: the Menu button (below 1024px), the brand (home: the signed-in home for an
 * account, literature search for a visitor), the global paper search, the notification bell
 * and the account controls. One row, 56px high, at every width at the default text size; its
 * layout follows its own width in rem, so with enlarged text it switches to the compact
 * controls and, if they still do not fit, wraps onto a second row instead of overflowing.
 */
export function ShellHeader({ navOpen, onOpenNav }: { navOpen: boolean; onOpenNav: () => void }) {
  const pathname = usePathname() ?? "/";
  const { status } = useSession();
  const home = status === "authenticated" ? "/dashboard" : "/";

  return (
    <header className={styles.header}>
      {/* The header is the full-width container its controls query; this row holds them. */}
      <div className={styles.row}>
        <div className={styles.start}>
          <IconButton
            className={styles.menuButton}
            label="Menu"
            icon={<Menu size={20} aria-hidden="true" />}
            aria-haspopup="dialog"
            aria-expanded={navOpen}
            onClick={onOpenNav}
          />
          <Link href={home} className={styles.brand} aria-label="ResearchConnect AI home">
            <span className={styles.mark} aria-hidden="true">
              <GraduationCap size={18} />
            </span>
            <span className={styles.brandName} aria-hidden="true">
              ResearchConnect AI
            </span>
          </Link>
        </div>

        {/* The literature search page has its own, larger search box. */}
        <div className={styles.search}>{pathname !== "/" && <GlobalSearch />}</div>

        <div className={styles.end}>
          {status === "authenticated" && <NotificationBell />}
          <AccountMenu />
        </div>
      </div>
    </header>
  );
}
