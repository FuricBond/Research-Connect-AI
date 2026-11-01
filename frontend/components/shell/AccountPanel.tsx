"use client";

import Link from "next/link";
import { useState } from "react";
import { LogOut } from "lucide-react";
import { logout as revokeTokens } from "../../services/api";
import type { AuthenticatedUser } from "../../types/auth";
import { ROLE_LABELS } from "../../types/auth";
import { accountItemsFor } from "../../utils/navigation";
import { ThemeSwitcher } from "../ui/ThemeSwitcher/ThemeSwitcher";
import styles from "./AccountMenu.module.css";

export function ThemeRow() {
  return (
    <div className={styles.theme}>
      <span className={styles.themeLabel} aria-hidden="true">
        Theme
      </span>
      <ThemeSwitcher />
    </div>
  );
}

/** What the account button opens. Loaded when the button is about to be used. */
export function AccountPanel({ user, close, current, onSignedOut }: { user: AuthenticatedUser; close: () => void; current: string | null; onSignedOut: () => void }) {
  const [signingOut, setSigningOut] = useState(false);

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      await revokeTokens();
    } catch {
      // Offline or already revoked: this browser is signed out either way.
    } finally {
      setSigningOut(false);
      // Whether or not the server answered, this browser is now signed out (as before).
      onSignedOut();
    }
  };

  return (
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
  );
}
