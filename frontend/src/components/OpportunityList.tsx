import { CalendarDays, ExternalLink } from "lucide-react";

import type { Opportunity } from "../types/opportunity";

const opportunities: Opportunity[] = [
  {
    id: "sample-cfp-1",
    title: "International Conference on AI Research",
    source: "Sample CFP feed",
    opportunityType: "Conference",
    deadline: "2026-11-15",
    summary:
      "A starter record that will later come from the backend, scraper pipeline, and recommendation layer.",
    url: "https://example.com/cfp/ai-research",
  },
];

export function OpportunityList() {
  return (
    <section className="opportunity-list" aria-label="Recommended opportunities">
      <div className="section-heading">
        <h2>Recommended opportunities</h2>
        <span>{opportunities.length} result</span>
      </div>

      {opportunities.map((opportunity) => (
        <article className="opportunity-card" key={opportunity.id}>
          <div>
            <p className="tag">{opportunity.opportunityType}</p>
            <h3>{opportunity.title}</h3>
            <p>{opportunity.summary}</p>
          </div>

          <footer>
            <span>
              <CalendarDays size={16} />
              Deadline {opportunity.deadline}
            </span>
            <a href={opportunity.url} rel="noreferrer" target="_blank">
              <ExternalLink size={16} />
              Source
            </a>
          </footer>
        </article>
      ))}
    </section>
  );
}
