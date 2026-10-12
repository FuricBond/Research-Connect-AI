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
import { ButtonLink } from "../ui/Button/Button";
import { ErrorState, Skeleton, SkeletonList } from "../ui/State/State";
import type { PlatformRole } from "../../types/auth";
import { ROLE_LABELS } from "../../types/auth";
import { useSession } from "./SessionProvider";
import styles from "./RequireAuth.module.css";

/**
 * While the session is checked (or the redirect to sign-in starts): the shape of a page — a
 * title, a line of description, a few rows — instead of a spinner in a dashed box, so the page
 * that follows replaces it rather than jumping in under it. One status message names the wait.
 */
function AuthPending({ label }: { label: string }) {
  return (
    <div className={styles.pending}>
      <div className={styles.header} aria-hidden="true">
        <Skeleton className={styles.title} />
        <Skeleton className={styles.description} />
      </div>
      <SkeletonList rows={3} lines={2} label={label} />
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
    // The design system's permission state (DESIGN_SYSTEM.md §10), with the same words as before.
    return (
      <ErrorState
        kind="permission"
        announce
        headingLevel={1}
        title={<>This page is for {permitted} accounts.</>}
        description={
          <>
            You are signed in as {user.full_name} ({ROLE_LABELS[user.role]}). Ask an administrator if you
            need access.
          </>
        }
        actions={<ButtonLink href="/">Back to discovery</ButtonLink>}
      />
    );
  }

  return <>{children}</>;
}
