"use client";

import { useCallback, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { NavDrawer } from "./NavDrawer";
import { PrimaryNav } from "./PrimaryNav";
import { ShellHeader } from "./ShellHeader";
import styles from "./AppShell.module.css";

/**
 * The application shell (P2), rendered once in app/layout.tsx around every page.
 *
 *   ≥ 1024px  header (brand, search, notifications, account) + navigation sidebar + content
 *   < 1024px  the same header with a Menu button; the navigation opens in a drawer
 *
 * One primary navigation is exposed at a time: the sidebar is not displayed below 1024px, and
 * the drawer (a modal dialog holding the same navigation) only opens from the Menu button,
 * which is not displayed from 1024px.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  // The drawer stays open only on the page it was opened on, so following any link (or the
  // browser's back button) closes it without an effect; returning to that page later must not
  // reopen it, so the record is dropped as soon as the page changes.
  const [drawerOpenOn, setDrawerOpenOn] = useState<string | null>(null);
  if (drawerOpenOn !== null && drawerOpenOn !== pathname) setDrawerOpenOn(null);
  const drawerOpen = drawerOpenOn === pathname;
  const openDrawer = useCallback(() => setDrawerOpenOn(pathname), [pathname]);
  const closeDrawer = useCallback(() => setDrawerOpenOn(null), []);

  return (
    <div className={styles.shell}>
      <ShellHeader navOpen={drawerOpen} onOpenNav={openDrawer} />
      <div className={styles.body}>
        <div className={styles.sidebar}>
          <PrimaryNav />
        </div>
        <main id="main-content" className={styles.main} tabIndex={-1}>
          <div className={styles.page}>{children}</div>
        </main>
      </div>
      <NavDrawer open={drawerOpen} onClose={closeDrawer} />
    </div>
  );
}
