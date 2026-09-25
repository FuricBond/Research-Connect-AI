"use client";

/**
 * Phase 6.2 — Route protection.
 *
 * This is UX, not security. It keeps a signed-out visitor from landing on a page whose
 * every request would fail, and sends them somewhere useful instead. The backend still
 * authorises every request behind these pages, and a `roles` mismatch here only hides a
 * screen — it never grants anything.
 *
 * Children are never rendered while the session is still being restored, so protected
 * content cannot flash before we know who is there.
 */

import React, { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2, ShieldAlert } from "lucide-react";
import Link from "next/link";
import type { PlatformRole } from "../../types/auth";
import { ROLE_LABELS } from "../../types/auth";
import { useSession } from "./SessionProvider";

function AuthPending({ label }: { label: string }) {
  return (
    <div className="auth-pending" role="status" aria-live="polite">
      <Loader2 size={20} className="auth-spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function RequireAuth({
  children,
  roles,
}: {
  children: React.ReactNode;
  /** When given, only these roles see the page. Omit for any signed-in account. */
  roles?: readonly PlatformRole[];
}) {
  const { status, user } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status !== "unauthenticated") return;
    // Carry the intended destination so signing in returns the person to it.
    const next = pathname && pathname !== "/" ? `?next=${encodeURIComponent(pathname)}` : "";
    router.replace(`/login${next}`);
  }, [status, pathname, router]);

  if (status === "loading") {
    return <AuthPending label="Checking your session…" />;
  }

  if (status === "unauthenticated" || user === null) {
    return <AuthPending label="Taking you to sign in…" />;
  }

  if (roles !== undefined && !roles.includes(user.role)) {
    const permitted = roles.map((role) => ROLE_LABELS[role]).join(" or ");
    return (
      <div className="auth-denied" role="alert">
        <ShieldAlert size={18} aria-hidden="true" />
        <div>
          <p className="auth-denied-title">This page is for {permitted} accounts.</p>
          <p className="auth-denied-body">
            You are signed in as {user.full_name} ({ROLE_LABELS[user.role]}). Ask an
            administrator if you need access.
          </p>
          <Link href="/" className="auth-link">
            Back to discovery
          </Link>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
