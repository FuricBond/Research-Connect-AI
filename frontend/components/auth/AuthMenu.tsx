"use client";

/**
 * Phase 6.2 — The identity control in the application header.
 *
 * Shows who is signed in, the role the backend reports for them, and a way out. Signed
 * out, it offers the two ways in. The role shown here is display only.
 *
 * Phase 6.7: signing out first asks the backend to revoke the account's tokens, then clears
 * the stored session whether or not that request succeeded.
 */

import React, { useState } from "react";
import Link from "next/link";
import { LogIn, LogOut, UserPlus } from "lucide-react";
import { logout as revokeTokens } from "../../services/api";
import { ROLE_LABELS } from "../../types/auth";
import { useSession } from "./SessionProvider";

export function AuthMenu() {
  const { status, user, logout } = useSession();
  const [signingOut, setSigningOut] = useState(false);

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      await revokeTokens();
    } catch {
      // Offline or already revoked: this browser is signed out either way.
    } finally {
      setSigningOut(false);
      logout();
    }
  };

  // Render nothing rather than a guess while the stored session is being verified —
  // showing "Sign in" and then replacing it with a name reads as a glitch.
  if (status === "loading") {
    return <div className="auth-menu auth-menu-placeholder" aria-hidden="true" />;
  }

  if (status === "unauthenticated" || user === null) {
    return (
      <div className="auth-menu">
        <Link href="/login" className="auth-menu-btn">
          <LogIn size={14} aria-hidden="true" />
          Sign in
        </Link>
        <Link href="/register" className="auth-menu-btn primary">
          <UserPlus size={14} aria-hidden="true" />
          Create account
        </Link>
      </div>
    );
  }

  return (
    <div className="auth-menu">
      <div className="auth-menu-identity">
        <span className="auth-menu-name">{user.full_name}</span>
        <span className="auth-menu-role">{ROLE_LABELS[user.role]}</span>
      </div>
      <button type="button" className="auth-menu-btn" onClick={handleSignOut} disabled={signingOut}>
        <LogOut size={14} aria-hidden="true" />
        {signingOut ? "Signing out…" : "Sign out"}
      </button>
    </div>
  );
}
