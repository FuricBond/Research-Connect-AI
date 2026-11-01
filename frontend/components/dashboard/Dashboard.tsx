"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { lazy, Suspense, useEffect } from "react";
import { Plus } from "lucide-react";
import { AuthPending } from "../auth/RequireAuth";
import { useSession } from "../auth/SessionProvider";
import { NEW_POSTING_HREF } from "../../utils/postingLinks";
import { ButtonLink } from "../ui/Button/Button";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { SkeletonList } from "../ui/State/State";
import { VerificationNotice } from "../postings/VerificationNotice";
import styles from "./Dashboard.module.css";

/**
 * P10: an administrator's home, the administration overview (utils/navigation.ts "Overview"). A
 * literal: importing the navigation's config or utils/admin here would add their code to this page.
 */
const ADMIN_HOME_HREF = "/admin";

const StudentDashboard = lazy(() => import("./StudentDashboard").then((module) => ({ default: module.StudentDashboard })));
const FacultyDashboard = lazy(() => import("./FacultyDashboard").then((module) => ({ default: module.FacultyDashboard })));

const DESCRIPTION = {
  STUDENT: "What needs your attention, what is new for you, and what is coming up.",
  FACULTY: "Applications waiting for you, your open postings, and what is coming up.",
} as const;

/**
 * P4 — the signed-in home (`/dashboard`, FRONTEND_REDESIGN_PLAN.md §8): student and faculty
 * modules, each loading and failing on its own, at most seven requests (see resources.ts).
 * P10: an administrator's home is the administration overview (plan §8), so /dashboard — where
 * signing in lands — takes them there, replacing itself in the history.
 */
export function Dashboard() {
  const { user, role, profileId } = useSession();
  if (user === null || role === null) return null;
  if (role === "ADMIN") return <AdminHome />;
  return (
    <div className={styles.page}>
      <PageHeader
        display
        title={<>Welcome back, {user.full_name.trim() || "researcher"}</>}
        description={DESCRIPTION[role]}
        // P9: the recruiting home's one main action.
        actions={
          role === "FACULTY" && user.is_verified && (
            <ButtonLink href={NEW_POSTING_HREF} variant="primary" leadingIcon={<Plus size={16} aria-hidden="true" />}>
              New posting
            </ButtonLink>
          )
        }
      />
      {role === "FACULTY" && !user.is_verified && <VerificationNotice />}
      {/* One role's modules are never downloaded for another (audit PERF-04). */}
      <Suspense fallback={<SkeletonList rows={4} lines={2} label="Loading your home" />}>
        {role === "STUDENT" && <StudentDashboard profileId={profileId} />}
        {role === "FACULTY" && <FacultyDashboard profileId={profileId} />}
      </Suspense>
    </div>
  );
}

function AdminHome() {
  const router = useRouter();
  useEffect(() => {
    router.replace(ADMIN_HOME_HREF);
  }, [router]);
  return (
    <>
      <AuthPending label="Opening the administration overview…" />
      <p className={styles.reason}>
        <Link href={ADMIN_HOME_HREF}>Go to the administration overview</Link>
      </p>
    </>
  );
}
