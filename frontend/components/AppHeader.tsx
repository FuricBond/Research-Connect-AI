"use client";

import Link from "next/link";
import { GraduationCap } from "lucide-react";
import { AuthMenu } from "./auth/AuthMenu";
import { useSession } from "./auth/SessionProvider";

/**
 * AppHeader — the brand and the account control, rendered once in app/layout.tsx.
 * The brand leads home: the signed-in home for an account, literature search for a visitor.
 */
export function AppHeader() {
  const { status } = useSession();
  const home = status === "authenticated" ? "/dashboard" : "/";

  return (
    <header className="app-header">
      <div className="header-inner">
        <Link href={home} className="brand-wrap" aria-label="ResearchConnect AI home">
          <div className="brand-icon-box" aria-hidden="true">
            <GraduationCap size={22} />
          </div>
          <div>
            <span className="brand-name">ResearchConnect AI</span>
            <span className="brand-tagline">Academic Intelligence &amp; Discovery</span>
          </div>
        </Link>

        <div className="header-meta">
          <AuthMenu />
        </div>
      </div>
    </header>
  );
}
