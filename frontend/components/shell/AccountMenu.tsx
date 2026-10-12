"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState, type FocusEvent, type ReactNode } from "react";
import { ChevronDown, LogIn, LogOut, SunMoon, UserPlus } from "lucide-react";
import { logout as revokeTokens } from "../../services/api";
import { ROLE_LABELS } from "../../types/auth";
import { useSession } from "../auth/SessionProvider";
import { ThemeSwitcher } from "../ui/ThemeSwitcher/ThemeSwitcher";
import { accountItemsFor, currentHref } from "../../utils/navigation";
import styles from "./AccountMenu.module.css";

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
 * or moving focus out of it. It stays mounted while closed (hidden), so the theme control keeps
 * following the operating system while "Match system theme" is chosen.
 */
export function AccountMenu() {
  const { status, user, logout } = useSession();
  const [signingOut, setSigningOut] = useState(false);
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
        <Disclosure buttonClassName={styles.iconTrigger} label="Appearance" title="Appearance" button={<SunMoon size={20} aria-hidden="true" />}>
          <ThemeRow />
        </Disclosure>
      </div>
    );
  }

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      await revokeTokens();
    } catch {
      // Offline or already revoked: this browser is signed out either way.
    } finally {
      setSigningOut(false);
      // Whether or not the server answered, this browser is now signed out (as before).
      focusSignIn.current = true;
      logout();
    }
  };

  return (
    <div key="account" className={styles.account}>
      <Disclosure
        buttonClassName={styles.trigger}
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
        {(close, current) => (
          <>
            <div className={styles.identity}>
              <p className={styles.identityName}>{user.full_name}</p>
              <p className={styles.identityRole}>{ROLE_LABELS[user.role]} account</p>
            </div>
            <ul className={styles.links}>
              {accountItemsFor(user.role).map((item) => {
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link href={item.href} className={styles.link} aria-current={item.href === current ? "page" : undefined} onClick={close}>
                      <Icon size={16} aria-hidden="true" />
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
            <ThemeRow />
            <div className={styles.footer}>
              <button type="button" className={styles.signOut} onClick={handleSignOut} disabled={signingOut} aria-busy={signingOut || undefined}>
                <LogOut size={16} aria-hidden="true" />
                {signingOut ? "Signing out…" : "Sign out"}
              </button>
            </div>
          </>
        )}
      </Disclosure>
    </div>
  );
}

function ThemeRow() {
  return (
    <div className={styles.theme}>
      <span className={styles.themeLabel} aria-hidden="true">
        Theme
      </span>
      <ThemeSwitcher />
    </div>
  );
}

/**
 * A button that shows and hides a panel below it (WAI-ARIA disclosure). `children` may be a
 * function of (close, the current page's shell href) for panels with links.
 */
function Disclosure({
  button,
  buttonClassName,
  label,
  title,
  children,
}: {
  button: ReactNode;
  buttonClassName: string;
  /** The button's accessible name. */
  label: string;
  title?: string;
  children: ReactNode | ((close: () => void, current: string | null) => ReactNode);
}) {
  const pathname = usePathname() ?? "/";
  // Open only on the page it was opened on: following a link closes it without an effect (and
  // coming back to that page does not reopen it).
  const [openOn, setOpenOn] = useState<string | null>(null);
  if (openOn !== null && openOn !== pathname) setOpenOn(null);
  const open = openOn === pathname;
  const panelId = useId();
  const area = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const close = () => setOpenOn(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!area.current?.contains(event.target as Node)) setOpenOn(null);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpenOn(null);
      trigger.current?.focus();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  // Tabbing out of the open panel closes it (focus has already moved on; leave it there).
  const onBlur = (event: FocusEvent<HTMLDivElement>) => {
    const next = event.relatedTarget as Node | null;
    if (open && next !== null && !area.current?.contains(next)) setOpenOn(null);
  };

  return (
    <div ref={area} className={styles.disclosure} onBlur={onBlur}>
      <button
        ref={trigger}
        type="button"
        className={buttonClassName}
        aria-label={label}
        aria-expanded={open}
        aria-controls={panelId}
        title={title}
        onClick={() => setOpenOn(open ? null : pathname)}
      >
        {button}
      </button>
      <div id={panelId} className={styles.panel} hidden={!open}>
        {typeof children === "function" ? children(close, currentHref(pathname)) : children}
      </div>
    </div>
  );
}
