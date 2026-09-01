import React from "react";
import { BookOpen, Calendar, Compass, Sparkles } from "lucide-react";

export type DiscoveryTab = "search" | "similar" | "opportunities" | "all_opportunities";

interface DiscoveryNavbarProps {
  activeTab: DiscoveryTab;
  onTabChange: (tab: DiscoveryTab) => void;
  selectedWorkTitle?: string | null;
}

export const DiscoveryNavbar: React.FC<DiscoveryNavbarProps> = ({
  activeTab,
  onTabChange,
  selectedWorkTitle,
}) => {
  return (
    <nav className="discovery-nav" aria-label="Main Discovery Navigation">
      <div className="discovery-nav-tabs">
        <button
          type="button"
          className={`discovery-nav-tab ${activeTab === "search" ? "active" : ""}`}
          onClick={() => onTabChange("search")}
        >
          <BookOpen size={16} />
          <span>Literature Search</span>
        </button>

        <button
          type="button"
          className={`discovery-nav-tab ${activeTab === "similar" ? "active" : ""}`}
          onClick={() => onTabChange("similar")}
        >
          <Compass size={16} />
          <span>Similar Research</span>
          {selectedWorkTitle && activeTab === "similar" && (
            <span className="nav-pill">Active</span>
          )}
        </button>

        <button
          type="button"
          className={`discovery-nav-tab ${activeTab === "opportunities" ? "active" : ""}`}
          onClick={() => onTabChange("opportunities")}
        >
          <Sparkles size={16} />
          <span>Opportunity Matcher</span>
          {selectedWorkTitle && activeTab === "opportunities" && (
            <span className="nav-pill">Active</span>
          )}
        </button>

        <button
          type="button"
          className={`discovery-nav-tab ${activeTab === "all_opportunities" ? "active" : ""}`}
          onClick={() => onTabChange("all_opportunities")}
        >
          <Calendar size={16} />
          <span>Browse All Calls</span>
        </button>
      </div>
    </nav>
  );
};
