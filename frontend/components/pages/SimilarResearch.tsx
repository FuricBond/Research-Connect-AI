"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Megaphone } from "lucide-react";
import { useApiResource } from "../../hooks/useApiResource";
import { getSimilarResearch, lookupReadingList } from "../../services/api";
import { setSelectedWork } from "../../hooks/useSelectedWork";
import type { ResearchWorkRead } from "../../types/discovery";
import { useSession } from "../auth/SessionProvider";
import { PaperContextRequired } from "../discovery/PaperContextRequired";
import { SourcePaper } from "../discovery/SourcePaper";
import { usePaperContext } from "../discovery/paperContext";
import { PaperCard } from "../research/PaperCard";
import { EvidencePanel, PaperPanel } from "../research/lazyPanels";
import { fromSimilarItem, similarHref, venuesHref, type PaperItem } from "../research/paper";
import { Breadcrumb } from "../ui/Breadcrumb/Breadcrumb";
import { Button } from "../ui/Button/Button";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { Pagination } from "../ui/Pagination/Pagination";
import { EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import styles from "../discovery/PaperTools.module.css";

const PAGE_SIZE = 20;

const header = (
  <PageHeader title="Similar papers" description="Papers closest in meaning and topic to one paper you choose, each with the reasons it is similar." />
);

function SimilarPapers() {
  const { paperId, work, origin, headingRef, choose } = usePaperContext(similarHref);
  const [page, setPage] = useState(1);
  const [paper, setPaper] = useState<PaperItem | null>(null);
  const [evidence, setEvidence] = useState<PaperItem | null>(null);
  const resultsHeading = useRef<HTMLHeadingElement>(null);

  // A different paper starts again from its first page.
  const [pageFor, setPageFor] = useState(paperId);
  if (pageFor !== paperId) {
    setPageFor(paperId);
    setPage(1);
  }

  const similar = useApiResource(
    paperId ? `similar:${paperId}:${(page - 1) * PAGE_SIZE}:${PAGE_SIZE}` : null,
    (signal) => getSimilarResearch(paperId!, { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE, explain: true }, signal),
    { isEmpty: (data) => data.items.length === 0, scope: "public" }
  );
  const items = useMemo(() => (similar.data?.items ?? []).map(fromSimilarItem), [similar.data]);

  // Which of these the signed-in researcher has saved (for the Save buttons and the citation export).
  const { status: sessionStatus } = useSession();
  const [savedWorks, setSavedWorks] = useState<Record<string, string>>({});
  useEffect(() => {
    if (sessionStatus !== "authenticated" || items.length === 0) {
      setSavedWorks({});
      return;
    }
    const controller = new AbortController();
    lookupReadingList(
      items.map((item) => item.work.id),
      controller.signal
    )
      .then((result) => setSavedWorks(result.saved))
      .catch(() => undefined);
    return () => controller.abort();
  }, [items, sessionStatus]);
  const handleSaved = (workId: string, itemId: string) => setSavedWorks((previous) => ({ ...previous, [workId]: itemId }));

  if (!paperId) {
    return (
      <section className="similar-research-page empty-selection" aria-label="Similar papers">
        {header}
        <PaperContextRequired actionLabel="Find similar" onChoose={choose} />
      </section>
    );
  }

  const total = similar.data?.total ?? 0;
  const remember = (next: ResearchWorkRead) => setSelectedWork(next);
  const toPage = (next: number) => {
    setPage(next);
    resultsHeading.current?.focus();
  };

  return (
    <section className="similar-research-page" aria-label="Similar papers">
      <Breadcrumb items={[{ label: "Search", href: origin }, { label: work?.title ?? "Chosen paper" }]} current="Similar papers" />
      {header}

      <SourcePaper
        work={work}
        headingRef={headingRef}
        action={
          <Link href={venuesHref(paperId)} className={styles.toolLink}>
            <Megaphone size={16} aria-hidden="true" />
            Find venues for this paper
          </Link>
        }
      />

      <section className={styles.results} aria-labelledby="similar-results-heading" aria-busy={similar.status === "loading" || undefined}>
        <h2 id="similar-results-heading" ref={resultsHeading} tabIndex={-1} className={styles.resultsTitle}>
          {similar.status === "success" ? `${total.toLocaleString("en")} similar paper${total === 1 ? "" : "s"}` : "Similar papers"}
        </h2>
        <p role="status" className="rc-visually-hidden">
          {similar.status === "loading" ? "Finding similar papers…" : similar.status === "success" ? `${total} similar papers` : similar.status === "empty" ? "No similar papers found." : ""}
        </p>

        {similar.status === "loading" && <SkeletonList rows={4} lines={3} label="Finding similar papers" announce={false} />}
        {similar.status === "error" &&
          (similar.error?.kind === "not-found" ? (
            <ErrorState
              kind="not-found"
              title="This paper could not be found"
              description="It may have been removed from the corpus. Search for it again to choose it."
              actions={<Link href="/" className={styles.toolLink}>Go to search</Link>}
            />
          ) : (
            <ErrorState
              kind={similar.error?.kind === "network" ? "offline" : "failed"}
              title="Similar papers could not be loaded"
              description={similar.error?.kind === "network" ? "The server could not be reached. Check your connection and try again." : "Something went wrong while loading. Try again in a moment."}
              onRetry={similar.retry}
              announce={similar.retries > 0}
            />
          ))}
        {similar.status === "empty" &&
          (total > 0 ? (
            <EmptyState variant="no-results" title="This page is past the last one" actions={<Button onClick={() => toPage(1)}>Go to the first page</Button>} />
          ) : (
            <EmptyState variant="no-results" title="No similar papers found" description="No other paper in the corpus is close enough to this one in meaning or topic." />
          ))}
        {similar.status === "success" && (
          <>
            <ul className={styles.list}>
              {items.map((item) => (
                <li key={item.work.id}>
                  <PaperCard item={item} onOpen={setPaper} onExplain={setEvidence} onChoose={remember} saved={item.work.id in savedWorks} onSaved={handleSaved} />
                </li>
              ))}
            </ul>
            <Pagination page={page} total={total} pageSize={PAGE_SIZE} onPage={toPage} noun="similar papers" label="Similar papers pages" />
          </>
        )}
      </section>

      {paper && <PaperPanel item={paper} onClose={() => setPaper(null)} savedItemId={savedWorks[paper.work.id] ?? null} onSaved={handleSaved} onChoose={remember} />}
      {evidence && (
        <EvidencePanel
          subject={{ title: evidence.work.title, context: "similar", rank: evidence.rank, score: evidence.score, scoreKind: "similarity", explanation: evidence.explanation, sharedTopics: evidence.sharedTopics }}
          onClose={() => setEvidence(null)}
          rankingMode={similar.data?.ranking_mode}
        />
      )}
    </section>
  );
}

/**
 * Similar papers (`/similar?paper=<id>`, FRONTEND_REDESIGN_PLAN.md §10): reached from a paper —
 * its card or its panel — with a breadcrumb back to the search it came from and the paper
 * summarised at the top. Opened without a paper it explains itself (P0.7). One request per paper
 * and page; an answer always belongs to the paper it was asked for.
 */
export function SimilarResearchPage() {
  return (
    <Suspense fallback={header}>
      <SimilarPapers />
    </Suspense>
  );
}
