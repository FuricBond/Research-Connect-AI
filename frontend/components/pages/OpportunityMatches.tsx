"use client";

import Link from "next/link";
import { Suspense, useRef, useState, type KeyboardEvent } from "react";
import { Compass } from "lucide-react";
import { useApiResource } from "../../hooks/useApiResource";
import { matchOpportunitiesForResearch } from "../../services/api";
import type { OpportunityMatchItem } from "../../types/discovery";
import type { WorkspaceItem } from "../../types/workspace";
import { CALL_TYPES, DELIVERY_MODES, callTypeLabel, deliveryModeLabel } from "../../utils/research";
import { PaperContextRequired } from "../discovery/PaperContextRequired";
import { SourcePaper } from "../discovery/SourcePaper";
import { usePaperContext } from "../discovery/paperContext";
import type { EvidenceSection } from "../research/EvidencePanel";
import { EvidencePanel } from "../research/lazyPanels";
import { OpportunityCard } from "../research/OpportunityCard";
import { similarHref, venuesHref } from "../research/paper";
import { useTrackedCalls } from "../research/trackedCalls";
import { Breadcrumb } from "../ui/Breadcrumb/Breadcrumb";
import { Button } from "../ui/Button/Button";
import { Checkbox, Select, TextInput } from "../ui/Field/Field";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { Pagination } from "../ui/Pagination/Pagination";
import { EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import styles from "../discovery/PaperTools.module.css";

const PAGE_SIZE = 20;

interface VenueFilters {
  type: string;
  mode: string;
  maxFee: number | null;
  location: string;
  knownFee: boolean;
  upcoming: boolean;
}

/** "Upcoming deadlines only" starts off (P5 decision on plan Q10): nothing is hidden unasked. */
const NO_FILTERS: VenueFilters = { type: "", mode: "", maxFee: null, location: "", knownFee: false, upcoming: false };

const header = (
  <PageHeader
    title="Find venues"
    description="Calls for papers ranked for one paper you choose, each with its deadline, its venue risk and the reasons it fits."
  />
);

/** A text filter that applies on Enter or on leaving the field, so typing asks the API once. */
function CommitField({ label, value, onCommit, type = "text", placeholder, hint }: { label: string; value: string; onCommit: (value: string) => void; type?: "text" | "number"; placeholder?: string; hint?: string }) {
  const [text, setText] = useState(value);
  const [shown, setShown] = useState(value);
  if (value !== shown) {
    setShown(value);
    setText(value);
  }
  const commit = () => {
    if (text.trim() !== value) onCommit(text.trim());
  };
  return (
    <TextInput
      label={label}
      type={type}
      inputMode={type === "number" ? "numeric" : undefined}
      min={type === "number" ? 0 : undefined}
      placeholder={placeholder}
      hint={hint}
      value={text}
      onChange={(event) => setText(event.target.value)}
      onBlur={commit}
      onKeyDown={(event: KeyboardEvent<HTMLInputElement>) => {
        if (event.key === "Enter") {
          event.preventDefault();
          commit();
        }
      }}
    />
  );
}

function Venues() {
  const { paperId, work, origin, headingRef, choose } = usePaperContext(venuesHref);
  const [filters, setFilters] = useState<VenueFilters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [evidence, setEvidence] = useState<{ item: OpportunityMatchItem; section: EvidenceSection } | null>(null);
  const [savedHere, setSavedHere] = useState<Record<string, WorkspaceItem>>({});
  const resultsHeading = useRef<HTMLHeadingElement>(null);
  const tracked = useTrackedCalls();

  // A different paper starts again from the first page.
  const [pageFor, setPageFor] = useState(paperId);
  if (pageFor !== paperId) {
    setPageFor(paperId);
    setPage(1);
  }

  const offset = (page - 1) * PAGE_SIZE;
  const filtersKey = JSON.stringify(filters);
  const matches = useApiResource(
    paperId ? `venues:${paperId}:${filtersKey}:${offset}:${PAGE_SIZE}` : null,
    (signal) =>
      matchOpportunitiesForResearch(
        paperId!,
        {
          limit: PAGE_SIZE,
          offset,
          opportunity_type: filters.type || undefined,
          delivery_mode: filters.mode || undefined,
          max_apc_usd: filters.maxFee ?? undefined,
          require_known_apc: filters.knownFee || undefined,
          location: filters.location || undefined,
          upcoming_only: filters.upcoming || undefined,
          explain: true,
        },
        signal
      ),
    { isEmpty: (data) => data.items.length === 0, scope: "public" }
  );

  if (!paperId) {
    return (
      <section className="opportunity-matches-page empty-selection" aria-label="Find venues">
        {header}
        <PaperContextRequired actionLabel="Find venues" onChoose={choose} />
      </section>
    );
  }

  const change = (next: Partial<VenueFilters>) => {
    setFilters((previous) => ({ ...previous, ...next }));
    setPage(1);
  };
  const toPage = (next: number) => {
    setPage(next);
    resultsHeading.current?.focus();
  };
  const filtered = JSON.stringify(filters) !== JSON.stringify(NO_FILTERS);
  const total = matches.data?.total ?? 0;
  const open = evidence?.item;

  return (
    <section className="opportunity-matches-page" aria-label="Find venues">
      <Breadcrumb items={[{ label: "Search", href: origin }, { label: work?.title ?? "Chosen paper" }]} current="Find venues" />
      {header}

      <SourcePaper
        work={work}
        headingRef={headingRef}
        action={
          <Link href={similarHref(paperId)} className={styles.toolLink}>
            <Compass size={16} aria-hidden="true" />
            Similar papers
          </Link>
        }
      />

      <form className={styles.filters} aria-label="Venue filters" onSubmit={(event) => event.preventDefault()}>
        <Select label="Type" value={filters.type} onChange={(event) => change({ type: event.target.value })}>
          <option value="">All types</option>
          {CALL_TYPES.map((type) => (
            <option key={type} value={type}>
              {callTypeLabel(type)}
            </option>
          ))}
        </Select>
        <Select label="Attendance" value={filters.mode} onChange={(event) => change({ mode: event.target.value })}>
          <option value="">Any</option>
          {DELIVERY_MODES.map((mode) => (
            <option key={mode} value={mode}>
              {deliveryModeLabel(mode)}
            </option>
          ))}
        </Select>
        <CommitField
          label="Highest fee (USD)"
          type="number"
          placeholder="e.g. 1000"
          value={filters.maxFee === null ? "" : String(filters.maxFee)}
          onCommit={(value) => {
            const fee = Number(value);
            change({ maxFee: value && Number.isFinite(fee) && fee >= 0 ? fee : null });
          }}
        />
        <CommitField label="Location" placeholder="e.g. London, online" value={filters.location} onCommit={(location) => change({ location })} />
        <Checkbox label="Only venues that state their fee" checked={filters.knownFee} onChange={(event) => change({ knownFee: event.target.checked })} />
        {/* The hint stays outside the label, so it describes the box without becoming its name. */}
        <div className={styles.check}>
          <Checkbox label="Upcoming deadlines only" aria-describedby="venues-upcoming-hint" checked={filters.upcoming} onChange={(event) => change({ upcoming: event.target.checked })} />
          <p id="venues-upcoming-hint" className={styles.note}>
            Leaves out calls whose deadline has passed and calls with no listed deadline.
          </p>
        </div>
      </form>

      <section className={styles.results} aria-labelledby="venue-results-heading" aria-busy={matches.status === "loading" || undefined}>
        <h2 id="venue-results-heading" ref={resultsHeading} tabIndex={-1} className={styles.resultsTitle}>
          {matches.status === "success" ? `${total.toLocaleString("en")} matching call${total === 1 ? "" : "s"}` : "Matching calls"}
        </h2>
        <p role="status" className="rc-visually-hidden">
          {matches.status === "loading" ? "Finding venues…" : matches.status === "success" ? `${total} matching calls` : matches.status === "empty" ? "No calls match." : ""}
        </p>

        {matches.status === "loading" && <SkeletonList rows={4} lines={3} label="Finding venues" announce={false} />}
        {matches.status === "error" &&
          (matches.error?.kind === "not-found" ? (
            <ErrorState
              kind="not-found"
              title="This paper could not be found"
              description="It may have been removed from the corpus. Search for it again to choose it."
              actions={<Link href="/" className={styles.toolLink}>Go to search</Link>}
            />
          ) : (
            <ErrorState
              kind={matches.error?.kind === "network" ? "offline" : "failed"}
              title="Venues could not be found"
              description={matches.error?.kind === "network" ? "The server could not be reached. Check your connection and try again." : "Something went wrong while matching. Try again in a moment."}
              onRetry={matches.retry}
              announce={matches.retries > 0}
            />
          ))}
        {matches.status === "empty" &&
          (total > 0 ? (
            <EmptyState variant="no-results" title="This page is past the last one" actions={<Button onClick={() => toPage(1)}>Go to the first page</Button>} />
          ) : (
            <EmptyState
              variant="no-results"
              title="No calls match this paper"
              description={filtered ? "Try fewer filters, or include calls without an upcoming deadline." : "No call in the collection is close enough to this paper's topic and type."}
              actions={filtered ? <Button onClick={() => change(NO_FILTERS)}>Clear filters</Button> : undefined}
            />
          ))}
        {matches.status === "success" && matches.data && (
          <>
            <ul className={styles.list}>
              {matches.data.items.map((item) => (
                <li key={item.opportunity.id}>
                  <OpportunityCard
                    call={item.opportunity}
                    match={{
                      rank: item.rank,
                      score: item.match_score,
                      explanation: item.explanation ?? null,
                      onExplain: (section) => setEvidence({ item, section }),
                    }}
                    saved={tracked.byCall.has(item.opportunity.id) || item.opportunity.id in savedHere}
                    onSaved={(saved) => setSavedHere((previous) => ({ ...previous, [item.opportunity.id]: saved }))}
                  />
                </li>
              ))}
            </ul>
            <Pagination page={page} total={total} pageSize={PAGE_SIZE} onPage={toPage} noun="calls" label="Matching calls pages" />
          </>
        )}
      </section>

      {open && evidence && (
        <EvidencePanel
          subject={{
            title: open.opportunity.title,
            context: "venue",
            rank: open.rank,
            score: open.match_score,
            scoreKind: "match",
            explanation: open.explanation ?? null,
            sharedTopics: open.shared_topic_names,
            call: {
              risk: open.risk_explanation ?? open.opportunity.risk_explanation ?? null,
              riskLevel: open.opportunity.risk_level,
              isPredatory: open.opportunity.is_predatory_flag,
              deadline: open.deadline_explanation ?? open.opportunity.deadline_intelligence ?? null,
              dates: open.opportunity,
            },
          }}
          section={evidence.section}
          onClose={() => setEvidence(null)}
          rankingMode={matches.data?.ranking_mode}
        />
      )}
    </section>
  );
}

/**
 * Find venues (`/opportunities?paper=<id>`, FRONTEND_REDESIGN_PLAN.md §10–11): calls for papers
 * ranked for one paper, reached from the paper, with a breadcrumb back to its search. Every call
 * shows its deadline and venue risk apart from each other; "Why this venue?", the risk badge and
 * "All dates" open the Evidence panel at their part. The filters are the API's; one request per
 * paper, filter set and page, and an answer always belongs to the request it was asked for.
 */
export function OpportunityMatchesPage() {
  return (
    <Suspense fallback={header}>
      <Venues />
    </Suspense>
  );
}
