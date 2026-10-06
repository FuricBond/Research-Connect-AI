"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BookMarked, Search } from "lucide-react";
import { useSession } from "../auth/SessionProvider";
import { fetchReadingList } from "../../services/api";
import type { ResearchWorkRead } from "../../types/discovery";
import type { ReadingListWorkSummary } from "../../types/reading_list";

/** How many saved papers to offer; the full list is one link away. */
const SAVED_PAPERS_SHOWN = 5;

interface PaperContextRequiredProps {
  /** The result-card action that opens this tool, e.g. "Find Similar Research". */
  actionLabel: string;
  /** Called with the paper the person picked from their reading list. */
  onChoose: (work: ResearchWorkRead) => void;
}

/**
 * P0.7 — what Similar Research and the Opportunity Matcher show when no paper is selected.
 *
 * Both tools work from one paper. Instead of a dead end, this says why a paper is needed and
 * offers the two ways to provide one: find it in Literature Search, or (signed in) use a paper
 * already on the reading list. Nothing is ever selected on the person's behalf.
 */
export function PaperContextRequired({ actionLabel, onChoose }: PaperContextRequiredProps) {
  const { status } = useSession();
  const [saved, setSaved] = useState<ReadingListWorkSummary[]>([]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const controller = new AbortController();
    fetchReadingList({ limit: SAVED_PAPERS_SHOWN }, controller.signal)
      .then((response) => setSaved(response.items.map((item) => item.work)))
      // The reading list is a shortcut; without it the search path still works.
      .catch(() => setSaved([]));
    return () => controller.abort();
  }, [status]);

  return (
    <section className="paper-context-required" aria-labelledby="paper-context-heading">
      <h2 id="paper-context-heading">Choose a paper to start</h2>
      <p>
        This tool works from one paper you pick. Search for a topic in Literature Search, then
        choose <strong>{actionLabel}</strong> on a result.
        {saved.length > 0 && " You can also start from a paper on your reading list."}
      </p>
      <Link href="/" className="action-btn primary-btn paper-context-search">
        <Search size={16} aria-hidden="true" />
        <span>Find a paper in Literature Search</span>
      </Link>

      {saved.length > 0 && (
        <div className="paper-context-saved">
          <h3>
            <BookMarked size={16} aria-hidden="true" />
            From your reading list
          </h3>
          <ul>
            {saved.map((work) => (
              <li key={work.id} className="paper-context-saved-item">
                <div className="paper-context-saved-text">
                  <span className="paper-context-saved-title">{work.title}</span>
                  {(work.publication_year || work.venue_name) && (
                    <span className="paper-context-saved-meta">
                      {[work.venue_name, work.publication_year].filter(Boolean).join(" · ")}
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  className="action-btn secondary-btn"
                  aria-label={`Use this paper: ${work.title}`}
                  onClick={() =>
                    onChoose({
                      id: work.id,
                      title: work.title,
                      doi: work.doi,
                      publication_year: work.publication_year,
                      work_type: work.work_type,
                      landing_page_url: work.landing_page_url,
                    })
                  }
                >
                  Use this paper
                </button>
              </li>
            ))}
          </ul>
          <Link href="/reading-list" className="paper-context-all-saved">
            Open your reading list
          </Link>
        </div>
      )}
    </section>
  );
}

/** The one-line purpose shown at the top of a paper-based tool, with or without a paper. */
export function ToolPageHeader({ title, description }: { title: string; description: string }) {
  return (
    <header className="tool-page-header">
      <h1>{title}</h1>
      <p>{description}</p>
    </header>
  );
}
