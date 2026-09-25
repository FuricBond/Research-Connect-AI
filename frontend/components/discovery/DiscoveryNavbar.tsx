"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell, BookOpen, Briefcase, Calendar, CalendarDays, Compass, FileText, Megaphone, ShieldCheck, Sparkles, User, Users } from "lucide-react";
import { useSession } from "../auth/SessionProvider";

/**
 * DiscoveryNavbar — migrated from React tab-state to Next.js Link navigation.
 *
 * Active tab is detected from the current pathname instead of a prop,
 * so it works correctly with server-side rendering and browser history.
 *
 * Tabs whose pages need an account appear only once there is one, and the administration
 * tab only for an ADMIN account. Hiding a tab is a convenience, never a permission: the
 * pages behind them are guarded and the backend authorises every request.
 */
export function DiscoveryNavbar() {
  const pathname = usePathname();
  const { status, hasRole } = useSession();

  // Treat "still restoring" as not signed in: a tab that appears is better than one that
  // appears and then vanishes.
  const isAuthenticated = status === "authenticated";
  const isAdmin = isAuthenticated && hasRole("ADMIN");

  const isSearch = pathname === "/";
  const isSimilar = pathname === "/similar";
  const isOpportunities = pathname === "/opportunities";
  const isBrowse = pathname === "/browse";
  const isPostings = pathname.startsWith("/postings");
  const isPeers = pathname.startsWith("/peers");
  const isWorkspace = pathname.startsWith("/workspace");
  const isSubmissions = pathname.startsWith("/submissions");
  const isCalendar = pathname.startsWith("/calendar");
  const isResearcher = pathname.startsWith("/researcher");
  const isAdminRoute = pathname.startsWith("/admin");
  const isNotifications = pathname.startsWith("/notifications") || pathname.startsWith("/settings/notifications");

  return (
    <nav className="discovery-nav" aria-label="Main Discovery Navigation">
      <div className="discovery-nav-tabs">
        <Link
          href="/"
          className={`discovery-nav-tab ${isSearch ? "active" : ""}`}
        >
          <BookOpen size={16} />
          <span>Literature Search</span>
        </Link>

        <Link
          href="/similar"
          className={`discovery-nav-tab ${isSimilar ? "active" : ""}`}
        >
          <Compass size={16} />
          <span>Similar Research</span>
          {isSimilar && <span className="nav-pill">Active</span>}
        </Link>

        <Link
          href="/opportunities"
          className={`discovery-nav-tab ${isOpportunities ? "active" : ""}`}
        >
          <Sparkles size={16} />
          <span>Opportunity Matcher</span>
          {isOpportunities && <span className="nav-pill">Active</span>}
        </Link>

        <Link
          href="/browse"
          className={`discovery-nav-tab ${isBrowse ? "active" : ""}`}
        >
          <Calendar size={16} />
          <span>Browse All Calls</span>
        </Link>

        <Link
          href="/postings"
          className={`discovery-nav-tab ${isPostings ? "active" : ""}`}
        >
          <Megaphone size={16} />
          <span>Research Postings</span>
          {isPostings && <span className="nav-pill">Active</span>}
        </Link>

        {isAuthenticated && (
          <>
        <Link
          href="/workspace"
          className={`discovery-nav-tab ${isWorkspace ? "active" : ""}`}
        >
          <Briefcase size={16} />
          <span>Opportunity Workspace</span>
          {isWorkspace && <span className="nav-pill">Active</span>}
        </Link>

        <Link
          href="/submissions"
          className={`discovery-nav-tab ${isSubmissions ? "active" : ""}`}
        >
          <FileText size={16} />
          <span>Submissions</span>
          {isSubmissions && <span className="nav-pill">Active</span>}
        </Link>

        <Link
          href="/calendar"
          className={`discovery-nav-tab ${isCalendar ? "active" : ""}`}
        >
          <CalendarDays size={16} />
          <span>Research Calendar</span>
          {isCalendar && <span className="nav-pill">Active</span>}
        </Link>

        <Link
          href="/peers"
          className={`discovery-nav-tab ${isPeers ? "active" : ""}`}
        >
          <Users size={16} />
          <span>Find Peers</span>
          {isPeers && <span className="nav-pill">Active</span>}
        </Link>

        <Link
          href="/researcher"
          className={`discovery-nav-tab ${isResearcher ? "active" : ""}`}
        >
          <User size={16} />
          <span>Researcher Profile</span>
          {isResearcher && <span className="nav-pill">Active</span>}
        </Link>

        <Link
          href="/notifications"
          className={`discovery-nav-tab ${isNotifications ? "active" : ""}`}
        >
          <Bell size={16} />
          <span>Notifications</span>
          {isNotifications && <span className="nav-pill">Active</span>}
        </Link>
          </>
        )}

        {isAdmin && (
          <Link
            href="/admin"
            className={`discovery-nav-tab ${isAdminRoute ? "active" : ""}`}
          >
            <ShieldCheck size={16} />
            <span>Administration</span>
            {isAdminRoute && <span className="nav-pill">Active</span>}
          </Link>
        )}
      </div>
    </nav>
  );
}
