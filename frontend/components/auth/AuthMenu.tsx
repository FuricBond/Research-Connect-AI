"use client";

/**
 * Phase 6.2 — The identity control in the application header.
 *
 * Shows who is signed in, the role the backend reports for them, and a way out. Signed
 * out, it offers the two ways in. The role shown here is display only.
 */

import React from "react";
import Link from "next/link";
import { LogIn, LogOut, UserPlus } from "lucide-react";
import { ROLE_LABELS } from "../../types/auth";
import { useSession } from "./SessionProvider";

export function AuthMenu() {
  const { status, user, logout } = useSession();

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
      <button type="button" className="auth-menu-btn" onClick={logout}>
        <LogOut size={14} aria-hidden="true" />
        Sign out
      </button>
    </div>
  );
}
