import { useEffect, useState } from "react";
import { AlertCircle, CalendarDays, ExternalLink, Loader2 } from "lucide-react";

import { fetchOpportunities } from "../services/api";
import type { OpportunityListItem } from "../types/opportunity";
import { formatDeadlineDate } from "../utils/date";

const TYPE_LABELS: Record<string, string> = {
  CONFERENCE: "Conference",
  JOURNAL: "Journal",
  WORKSHOP: "Workshop",
  CALL_FOR_PAPERS: "Call for Papers",
  SPECIAL_ISSUE: "Special Issue",
};

function formatDeadline(iso: string | null): string | null {
  if (!iso) return null;
  return formatDeadlineDate(iso);
}

export function OpportunityList() {
  const [items, setItems] = useState<OpportunityListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setError(null);

    fetchOpportunities({ sort: "newest" })
      .then((data) => {
        if (!cancelled) {
          setItems(data.items);
          setTotal(data.total);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err.message ?? "Failed to load opportunities.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="opportunity-list" aria-label="Recommended opportunities">
      <div className="section-heading">
        <h2>Recommended opportunities</h2>
        {!loading && !error && (
          <span>
            {total} {total === 1 ? "result" : "results"}
          </span>
        )}
      </div>

      {loading && (
        <div className="status-row" aria-live="polite">
          <Loader2 size={18} className="spin" />
          <span>Loading opportunities…</span>
        </div>
      )}

      {!loading && error && (
        <div className="status-row status-error" role="alert">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <p className="status-empty">No opportunities found.</p>
      )}

      {!loading &&
        !error &&
        items.map((opportunity) => (
          <article className="opportunity-card" key={opportunity.id}>
            <div>
              <p className="tag">
                {TYPE_LABELS[opportunity.opportunity_type] ??
                  opportunity.opportunity_type}
              </p>
              <h3>{opportunity.title}</h3>
              {opportunity.publisher && (
                <p className="opportunity-publisher">{opportunity.publisher}</p>
              )}
              {opportunity.summary && <p>{opportunity.summary}</p>}
            </div>

            <footer>
              {opportunity.submission_deadline ? (
                <span>
                  <CalendarDays size={16} />
                  Deadline {formatDeadline(opportunity.submission_deadline)}
                </span>
              ) : null}

              {opportunity.location && (
                <span className="opportunity-location">
                  {opportunity.location}
                </span>
              )}

              {opportunity.website_url ? (
                <a href={opportunity.website_url} rel="noreferrer" target="_blank">
                  <ExternalLink size={16} />
                  Source
                </a>
              ) : null}
            </footer>
          </article>
        ))}
    </section>
  );
}
