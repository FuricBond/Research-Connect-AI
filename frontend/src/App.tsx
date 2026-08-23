import { Search, Sparkles } from "lucide-react";

import { OpportunityList } from "./components/OpportunityList";

export function App() {
  return (
    <main className="app-shell">
      <section className="top-bar">
        <div>
          <p className="eyebrow">ResearchConnect AI</p>
          <h1>Research opportunities, organized in one place.</h1>
        </div>
        <button className="primary-action" type="button">
          <Sparkles size={18} />
          Match my profile
        </button>
      </section>

      <section className="search-panel" aria-label="Opportunity search">
        <Search size={20} />
        <input
          type="search"
          placeholder="Search conferences, journals, CFPs, workshops, and grants"
        />
      </section>

      <OpportunityList />
    </main>
  );
}
