"use client";

import Link from "next/link";
import { lazy, Suspense, useCallback, useRef } from "react";
import { ChevronDown, LogIn, SunMoon, UserPlus } from "lucide-react";
import { useSession } from "../auth/SessionProvider";
import { Disclosure } from "./Disclosure";
import styles from "./AccountMenu.module.css";

const loadPanel = () => import("./AccountPanel");
const AccountPanel = lazy(() => loadPanel().then((module) => ({ default: module.AccountPanel })));
const ThemeRow = lazy(() => loadPanel().then((module) => ({ default: module.ThemeRow })));

/** Up to two initials for the avatar: "Ada Lovelace" → "AL". */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts;
  return letters.map((part) => part[0]?.toUpperCase() ?? "").join("") || "?";
}

/**
 * The account controls at the right of the header.
 *
 * Signed in: a disclosure button (avatar and name) opening a panel with the account's pages,
 * the colour theme and Sign out. Signed out: Sign in, Create account, and an "Appearance"
 * button for the colour theme. While the stored session is checked: a placeholder the size of
 * the signed-in controls, so nothing is offered that is about to change.
 *
 * The panel is a disclosure, not an ARIA menu: it holds links, a radio group and a button,
 * reached with Tab. Escape closes it and returns focus to its button; so does a click outside
 * or moving focus out of it. Its code loads when the button is about to be used; following the
 * operating system while "Match system theme" is chosen is the shell's (AppShell.tsx).
 */
export function AccountMenu() {
  const { status, user, logout } = useSession();
  // Set when this browser has just signed out: the Sign in link takes focus as it appears, so
  // keyboard focus is not lost with the Sign out button (P2 audit).
  const focusSignIn = useRef(false);
  const signInRef = useCallback((link: HTMLAnchorElement | null) => {
    if (link && focusSignIn.current) {
      focusSignIn.current = false;
      link.focus();
    }
  }, []);

  if (status === "loading") {
    return <div key="pending" className={styles.placeholder} aria-hidden="true" />;
  }

  if (status === "unauthenticated" || user === null) {
    return (
      <div key="visitor" className={styles.visitor}>
        <Link href="/login" className={styles.signIn} ref={signInRef}>
          <LogIn size={16} aria-hidden="true" />
          Sign in
        </Link>
        <Link href="/register" className={styles.register}>
          <UserPlus size={16} aria-hidden="true" />
          Create account
        </Link>
        <Disclosure onPrepare={loadPanel} className={styles.disclosure} panelClassName={styles.panel} buttonClassName={styles.iconTrigger} label="Appearance" title="Appearance" button={<SunMoon size={20} aria-hidden="true" />}>
          {(_close, _current, open) =>
            open ? (
              <Suspense fallback={null}>
                <ThemeRow />
              </Suspense>
            ) : null
          }
        </Disclosure>
      </div>
    );
  }

  return (
    <div key="account" className={styles.account}>
      <Disclosure
        className={styles.disclosure}
        panelClassName={styles.panel}
        buttonClassName={styles.trigger}
        onPrepare={loadPanel}
        // Starts with the name shown on the button (WCAG 2.5.3), then says what it opens.
        label={`${user.full_name}, account menu`}
        button={
          <>
            <span className={styles.avatar} aria-hidden="true">
              {initials(user.full_name)}
            </span>
            <span className={styles.name}>{user.full_name}</span>
            <ChevronDown size={16} aria-hidden="true" className={styles.chevron} />
          </>
        }
      >
        {(close, current, open) =>
          open ? (
            <Suspense fallback={null}>
              <AccountPanel
                user={user}
                close={close}
                current={current}
                onSignedOut={() => {
                  focusSignIn.current = true;
                  logout();
                }}
              />
            </Suspense>
          ) : null
        }
      </Disclosure>
    </div>
  );
}
