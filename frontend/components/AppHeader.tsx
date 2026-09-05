"use client";

import { GraduationCap } from "lucide-react";

/**
 * AppHeader — static top navigation bar.
 * Extracted from App.tsx. Rendered once in app/layout.tsx.
 */
export function AppHeader() {
  return (
    <header className="app-header">
      <div className="header-inner">
        <div className="brand-wrap">
          <div className="brand-icon-box">
            <GraduationCap size={22} />
          </div>
          <div>
            <span className="brand-name">ResearchConnect AI</span>
            <span className="brand-tagline">Academic Intelligence &amp; Discovery</span>
          </div>
        </div>

        <div className="header-meta">
          <span className="phase-indicator">Phase 2.7 Intelligence Engine</span>
        </div>
      </div>
    </header>
  );
}
