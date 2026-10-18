"use client";

import Link from "next/link";
import { useState } from "react";
import { Compass, Download, ExternalLink, Megaphone } from "lucide-react";
import { useApiResource } from "../../hooks/useApiResource";
import { downloadReadingListBibtex, getSimilarResearch } from "../../services/api";
import type { ResearchWorkRead } from "../../types/discovery";
import { doiHref, plainSummary, topReasons, workTypeLabel } from "../../utils/research";
import { useSession } from "../auth/SessionProvider";
import { SaveToReadingListButton } from "../reading-list/SaveToReadingListButton";
import { Button } from "../ui/Button/Button";
import { Drawer } from "../ui/Dialog/Dialog";
import { SkeletonList } from "../ui/State/State";
import { CitationMetadata } from "./CitationMetadata";
import { MatchScore } from "./MatchScore";
import { TopicTags } from "./TopicTags";
import { similarHref, venuesHref, type PaperItem } from "./paper";
import styles from "./Details.module.css";

/** Similar papers shown in the panel; the rest are one link away. */
const SIMILAR_SHOWN = 5;

interface PaperPanelProps {
  item: PaperItem | null;
  onClose: () => void;
  /** The reading-list item id when the paper is saved (for the citation export). */
  savedItemId?: string | null;
  onSaved?: (workId: string, itemId: string) => void;
  /** Called before a link opens a paper-based page with this paper. */
  onChoose: (work: ResearchWorkRead) => void;
}

function SimilarPapers({ work, onChoose }: { work: ResearchWorkRead; onChoose: (work: ResearchWorkRead) => void }) {
  // Asked for only when the panel is open, and only for this paper; the answer belongs to it.
  const similar = useApiResource(
    `similar:${work.id}:0:${SIMILAR_SHOWN}`,
    (signal) => getSimilarResearch(work.id, { limit: SIMILAR_SHOWN, offset: 0 }, signal),
    { isEmpty: (data) => data.items.length === 0, scope: "public" }
  );

  if (similar.status === "loading" || similar.status === "idle") return <SkeletonList rows={3} label="Loading similar papers" />;
  if (similar.status === "error") {
    return (
      <div className={styles.group}>
        <p className={styles.text}>Similar papers could not be loaded.</p>
        <div>
          <Button size="sm" onClick={similar.retry}>
            Try again
          </Button>
        </div>
      </div>
    );
  }
  if (similar.status === "empty" || !similar.data) return <p className={styles.text}>No similar papers were found in the corpus.</p>;

  return (
    <>
      <ul className={styles.similarList}>
        {similar.data.items.map((entry) => (
          <li key={entry.work.id} className={styles.similarItem}>
            <p className={styles.similarTitle}>{entry.work.title}</p>
            <div className={styles.cluster}>
              <MatchScore score={entry.combined_similarity} kind="similarity" />
              {entry.work.publication_year && <span className={styles.muted}>{entry.work.publication_year}</span>}
            </div>
          </li>
        ))}
      </ul>
      {similar.data.total > SIMILAR_SHOWN && (
        <Link href={similarHref(work.id)} className={styles.link} onClick={() => onChoose(work)}>
          All {similar.data.total.toLocaleString("en")} similar papers
        </Link>
      )}
    </>
  );
}

/**
 * The paper panel (FRONTEND_REDESIGN_PLAN.md §10): everything the page already holds about one
 * paper, opened from its title — there is no paper page, because the API cannot fetch a paper
 * by id (plan Q4). The full title is the panel's name; then venue, year and type; shared topics;
 * the abstract in reading type; why it is here; the citation facts; the actions (saving is the
 * primary one); and the first five similar papers, asked for only when the panel opens. Authors
 * are not shown: the search response does not include them.
 */
export function PaperPanel({ item, onClose, savedItemId, onSaved, onChoose }: PaperPanelProps) {
  const { status } = useSession();
  const [exportFailed, setExportFailed] = useState(false);
  const [exporting, setExporting] = useState(false);

  if (!item) return <Drawer open={false} onClose={onClose} title="" size="lg">{null}</Drawer>;

  const { work, explanation, sharedTopics, venue, score, scoreKind } = item;
  const facts = [venue, work.publication_year ? String(work.publication_year) : null, workTypeLabel(work.work_type)].filter(Boolean).join(" · ");
  const reasons = topReasons(explanation, 3);
  const summary = explanation ? plainSummary(explanation, item.rank) : null;
  const publisher = work.landing_page_url ?? (work.doi ? doiHref(work.doi) : null);

  const exportCitation = async () => {
    if (!savedItemId || exporting) return;
    setExporting(true);
    setExportFailed(false);
    try {
      await downloadReadingListBibtex({ itemIds: [savedItemId] });
    } catch {
      setExportFailed(true);
    } finally {
      setExporting(false);
    }
  };

  return (
    <Drawer open onClose={onClose} title={work.title} description={facts || undefined} size="lg" className="paper-panel">
      <div className={styles.stack}>
        {sharedTopics.length > 0 && (
          <div className={styles.group}>
            <h3 className={styles.groupTitle}>{item.context === "search" ? "Topics shared with your search" : "Topics shared with the chosen paper"}</h3>
            <TopicTags topics={sharedTopics} shared label="Shared topics" />
          </div>
        )}

        <section className={styles.section} aria-label="Abstract">
          <h3 className={styles.sectionTitle}>Abstract</h3>
          {work.abstract?.trim() ? <p className={styles.reading}>{work.abstract.trim()}</p> : <p className={styles.muted}>No abstract available.</p>}
        </section>

        <section className={styles.section} aria-label={scoreKind === "similarity" ? "Why it is similar" : "Why it is in the results"}>
          <h3 className={styles.sectionTitle}>{scoreKind === "similarity" ? "Why it is similar" : "Why it is in the results"}</h3>
          <div className={styles.cluster}>
            <MatchScore score={score} kind={scoreKind} />
            {reasons.length > 0 && <span className={styles.muted}>{reasons.join(" · ")}</span>}
          </div>
          {summary && <p className={styles.text}>{summary}</p>}
          <CitationMetadata work={work} />
        </section>

        <section className={styles.section} aria-label="Actions">
          <h3 className="rc-visually-hidden">Actions</h3>
          <div className={styles.actions}>
            <SaveToReadingListButton workId={work.id} isSaved={Boolean(savedItemId)} onSaved={onSaved} variant="primary" size="md" />
            {status === "authenticated" && (
              <Button onClick={exportCitation} loading={exporting} disabled={!savedItemId} aria-describedby={savedItemId ? undefined : "paper-export-hint"} leadingIcon={<Download size={16} aria-hidden="true" />}>
                Export citation
              </Button>
            )}
            <Link href={similarHref(work.id)} className={styles.link} onClick={() => onChoose(work)}>
              <Compass size={16} aria-hidden="true" />
              Find similar
            </Link>
            <Link href={venuesHref(work.id)} className={styles.link} onClick={() => onChoose(work)}>
              <Megaphone size={16} aria-hidden="true" />
              Find venues
            </Link>
            {publisher && (
              <a href={publisher} className={styles.link} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={16} aria-hidden="true" />
                Open publisher page
                <span className="rc-visually-hidden"> (opens in new tab)</span>
              </a>
            )}
          </div>
          {status === "authenticated" && !savedItemId && (
            <p id="paper-export-hint" className={styles.muted}>
              Save the paper to export its citation (BibTeX).
            </p>
          )}
          {exportFailed && (
            <p className={styles.text} role="alert">
              The citation could not be exported. Try again.
            </p>
          )}
        </section>

        <section className={styles.section} aria-label="Similar papers">
          <h3 className={styles.sectionTitle}>Similar papers</h3>
          <SimilarPapers work={work} onChoose={onChoose} />
        </section>
      </div>
    </Drawer>
  );
}
