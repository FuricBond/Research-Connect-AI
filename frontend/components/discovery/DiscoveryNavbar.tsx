"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, Calendar, Compass, Sparkles } from "lucide-react";

/**
 * DiscoveryNavbar — migrated from React tab-state to Next.js Link navigation.
 *
 * Active tab is detected from the current pathname instead of a prop,
 * so it works correctly with server-side rendering and browser history.
 */
export function DiscoveryNavbar() {
  const pathname = usePathname();

  const isSearch = pathname === "/";
  const isSimilar = pathname === "/similar";
  const isOpportunities = pathname === "/opportunities";
  const isBrowse = pathname === "/browse";

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
      </div>
    </nav>
  );
}
