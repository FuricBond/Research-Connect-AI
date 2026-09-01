import React, { useState } from "react";
import { Sparkles, GraduationCap } from "lucide-react";
import { DiscoveryNavbar, type DiscoveryTab } from "./components/discovery/DiscoveryNavbar";
import { DiscoverySearch } from "./pages/DiscoverySearch";
import { SimilarResearch } from "./pages/SimilarResearch";
import { OpportunityMatches } from "./pages/OpportunityMatches";
import { OpportunityList } from "./components/OpportunityList";
import type { ResearchWorkRead } from "./types/discovery";

export function App() {
  const [activeTab, setActiveTab] = useState<DiscoveryTab>("search");
  const [selectedWork, setSelectedWork] = useState<ResearchWorkRead | null>(null);

  const handleFindSimilar = (work: ResearchWorkRead) => {
    setSelectedWork(work);
    setActiveTab("similar");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleMatchOpportunities = (work: ResearchWorkRead) => {
    setSelectedWork(work);
    setActiveTab("opportunities");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleBackToSearch = () => {
    setActiveTab("search");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="app-layout">
      {/* Top Application Header */}
      <header className="app-header">
        <div className="header-inner">
          <div className="brand-wrap">
            <div className="brand-icon-box">
              <GraduationCap size={22} />
            </div>
            <div>
              <span className="brand-name">ResearchConnect AI</span>
              <span className="brand-tagline">Academic Intelligence & Discovery</span>
            </div>
          </div>

          <div className="header-meta">
            <span className="phase-indicator">Phase 2.4 Discovery Engine</span>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="app-shell">
        <DiscoveryNavbar
          activeTab={activeTab}
          onTabChange={setActiveTab}
          selectedWorkTitle={selectedWork?.title}
        />

        {/* View Switcher */}
        {activeTab === "search" && (
          <DiscoverySearch
            onFindSimilar={handleFindSimilar}
            onMatchOpportunities={handleMatchOpportunities}
          />
        )}

        {activeTab === "similar" && (
          <SimilarResearch
            selectedWork={selectedWork}
            onBackToSearch={handleBackToSearch}
            onMatchOpportunities={handleMatchOpportunities}
          />
        )}

        {activeTab === "opportunities" && (
          <OpportunityMatches
            selectedWork={selectedWork}
            onBackToSearch={handleBackToSearch}
          />
        )}

        {activeTab === "all_opportunities" && (
          <section className="browse-calls-section" aria-label="Browse All Opportunities">
            <div className="section-intro">
              <span className="eyebrow">Academic Feed</span>
              <h2>All Ingested Calls & Venues</h2>
              <p>Explore all active conferences, journals, workshops, and calls for papers.</p>
            </div>
            <OpportunityList />
          </section>
        )}
      </main>
    </div>
  );
}
export default App;
