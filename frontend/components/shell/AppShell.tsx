"use client";

import { lazy, Suspense, useCallback, useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { useSession } from "../auth/SessionProvider";
import { applyThemePreference, readThemePreference, watchSystemTheme } from "../../utils/theme";
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
const loadDrawer = () => import("./NavDrawer");
const NavDrawer = lazy(() => loadDrawer().then((module) => ({ default: module.NavDrawer })));

function SessionUnavailable() {
  const { status, retryCheck } = useSession();
  if (status !== "unavailable") return null;
  return (
    <div role="alert" className={styles.sessionUnavailable}>
      <p>We could not check your session, because the server did not answer. You have not been signed out.</p>
      <button type="button" className={styles.sessionRetry} onClick={retryCheck}>
        Try again
      </button>
    </div>
  );
}

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

  // While "Match system theme" is chosen, a change in the operating system is followed live.
  useEffect(
    () =>
      watchSystemTheme(() => {
        if (readThemePreference() === "system") applyThemePreference("system");
      }),
    []
  );

  return (
    <div className={styles.shell}>
      <ShellHeader navOpen={drawerOpen} onOpenNav={openDrawer} onPrepareNav={loadDrawer} />
      <div className={styles.body}>
        <div className={styles.sidebar}>
          <PrimaryNav />
        </div>
        <main id="main-content" className={styles.main} tabIndex={-1}>
          <div className={styles.page}>
            <SessionUnavailable />
            {children}
          </div>
        </main>
      </div>
      {drawerOpen && (
        <Suspense fallback={null}>
          <NavDrawer open onClose={closeDrawer} />
        </Suspense>
      )}
    </div>
  );
}
