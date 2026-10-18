"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Download, Trash2 } from "lucide-react";
import { useAddressSearch } from "../../hooks/useAddressSearch";
import { useApiResource } from "../../hooks/useApiResource";
import { downloadReadingListBibtex, fetchReadingList, removeReadingListItem, updateReadingListItem } from "../../services/api";
import type { ReadingListItem, ReadingStatus } from "../../types/reading_list";
import { ALL_READING_STATUSES, READING_STATUS_LABELS } from "../../types/reading_list";
import { bareDoi, doiHref } from "../../utils/research";
import { Button } from "../ui/Button/Button";
import { Dialog } from "../ui/Dialog/Dialog";
import { Select, TextArea } from "../ui/Field/Field";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { Pagination } from "../ui/Pagination/Pagination";
import { Alert, EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import { ChipCount } from "../workspace/ChipCount";
import { actionError } from "../workspace/workflow";
import { useKept } from "../workspace/item/useWorkspaceItem";
import styles from "./ReadingList.module.css";

const PAGE_SIZE = 50;
// The export takes the chosen ids in its URL, and the API accepts at most this many.
const EXPORT_SELECTION_LIMIT = 200;
const NEW_TAB_NOTE = "reading-list-new-tab";

export function readReadingQuery(params: URLSearchParams): { status: ReadingStatus | null; page: number } {
  const status = params.get("status");
  const page = Number.parseInt(params.get("page") ?? "1", 10);
  return {
    status: ALL_READING_STATUSES.includes(status as ReadingStatus) ? (status as ReadingStatus) : null,
    page: Number.isFinite(page) && page > 1 ? page : 1,
  };
}

function readingHref(status: ReadingStatus | null, page = 1): string {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (page > 1) params.set("page", String(page));
  const text = params.toString();
  return `/reading-list${text ? `?${text}` : ""}`;
}

function workHref(item: ReadingListItem): string | null {
  if (item.work.doi) return doiHref(item.work.doi);
  return item.work.landing_page_url;
}

function authorLine(authors: string[]): string {
  if (authors.length <= 3) return authors.join(", ");
  return `${authors.slice(0, 3).join(", ")} et al.`;
}

/**
 * P7 — /reading-list: the papers saved from Literature Search, filtered by reading status
 * (`?status=READING&page=2`, with counts), each with its status, private notes and a link to the
 * paper. A status change shows at once and is rolled back if the server refuses; notes save when
 * the box is left; removal asks first, naming the paper. BibTeX export is unchanged: the selected
 * papers, or the whole list (or the current status).
 */
export function ReadingListPage() {
  const [params, go] = useAddressSearch();
  const { status, page } = readReadingQuery(params);
  const offset = (page - 1) * PAGE_SIZE;
  const list = useApiResource(`reading-list:${status ?? "all"}:${offset}`, (signal) => fetchReadingList({ status: status ?? undefined, limit: PAGE_SIZE, offset }, signal));
  const shown = useKept(list);

  const [items, setItems] = useState<ReadingListItem[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [busy, setBusy] = useState<Set<string>>(() => new Set());
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [removing, setRemoving] = useState<ReadingListItem | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const requests = useRef(new Map<string, number>());

  useEffect(() => {
    if (!shown) return;
    // The last paper on a later page was removed: show the page before it instead.
    if (shown.items.length === 0 && offset > 0 && shown.total_count > 0) {
      go(readingHref(status, page - 1), { replace: true });
      return;
    }
    setItems(shown.items);
  }, [shown, offset, status, page, go]);

  const mark = (id: string, on: boolean) =>
    setBusy((current) => {
      const next = new Set(current);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  const replace = (updated: ReadingListItem) => setItems((current) => current && current.map((item) => (item.id === updated.id ? updated : item)));

  const choose = (next: ReadingStatus | null) => {
    setSelected(new Set());
    go(readingHref(next));
  };

  const changeStatus = async (item: ReadingListItem, next: ReadingStatus) => {
    const request = (requests.current.get(item.id) ?? 0) + 1;
    requests.current.set(item.id, request);
    setError(null);
    replace({ ...item, status: next });
    mark(item.id, true);
    try {
      const updated = await updateReadingListItem(item.id, { status: next });
      if (requests.current.get(item.id) !== request) return;
      replace(updated);
      setMessage(`${item.work.title}: ${READING_STATUS_LABELS[updated.status]}.`);
      // The counts change, and under a status filter the paper may leave this view.
      list.retry();
    } catch (err) {
      if (requests.current.get(item.id) !== request) return;
      replace(item);
      setError(actionError(err, `The status of ${item.work.title} could not be changed; it is still ${READING_STATUS_LABELS[item.status].toLowerCase()}.`));
    } finally {
      if (requests.current.get(item.id) === request) mark(item.id, false);
    }
  };

  const saveNotes = async (item: ReadingListItem, value: string) => {
    const notes = value.trim() ? value : null;
    if (notes === item.notes) return;
    setError(null);
    try {
      replace(await updateReadingListItem(item.id, { notes }));
      setMessage(`Notes on ${item.work.title} saved.`);
    } catch (err) {
      setError(actionError(err, `Your notes on ${item.work.title} could not be saved; they are still in the box.`));
    }
  };

  const remove = async () => {
    if (!removing || busy.has(removing.id)) return;
    const item = removing;
    mark(item.id, true);
    setRemoveError(null);
    try {
      await removeReadingListItem(item.id);
      setSelected((current) => {
        const next = new Set(current);
        next.delete(item.id);
        return next;
      });
      setItems((current) => current && current.filter((entry) => entry.id !== item.id));
      setRemoving(null);
      setMessage(`Removed ${item.work.title} from your reading list.`);
      list.retry();
    } catch (err) {
      setRemoveError(actionError(err, "The paper could not be removed."));
    } finally {
      mark(item.id, false);
    }
  };

  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const exportBibtex = async (itemIds?: string[]) => {
    if (itemIds && itemIds.length > EXPORT_SELECTION_LIMIT) {
      setError(`Select at most ${EXPORT_SELECTION_LIMIT} papers to export, or use Export all (.bib).`);
      return;
    }
    setExporting(true);
    setError(null);
    try {
      await downloadReadingListBibtex(itemIds ? { itemIds } : { status: status ?? undefined });
      setMessage("The BibTeX file is downloading.");
    } catch (err) {
      setError(actionError(err, "Your reading list could not be exported."));
    } finally {
      setExporting(false);
    }
  };

  const counts = shown?.counts_by_status;
  const totalSaved = counts ? ALL_READING_STATUSES.reduce((sum, value) => sum + (counts[value] ?? 0), 0) : null;
  const chips: { status: ReadingStatus | null; label: string; count: number | null }[] = [
    { status: null, label: "All", count: totalSaved },
    ...ALL_READING_STATUSES.map((value) => ({ status: value, label: READING_STATUS_LABELS[value], count: counts ? (counts[value] ?? 0) : null })),
  ];

  return (
    <>
      <PageHeader
        title="Reading list"
        description="Papers you saved from Literature Search. Track what you are reading, keep private notes and export citations as BibTeX. Your notes stay here: they are never exported."
        actions={
          <div className={styles.exports}>
            <Button variant="secondary" leadingIcon={<Download size={16} aria-hidden="true" />} disabled={selected.size === 0 || exporting} onClick={() => void exportBibtex([...selected])}>
              Export selected (.bib)
            </Button>
            <Button
              variant="secondary"
              leadingIcon={<Download size={16} aria-hidden="true" />}
              disabled={!totalSaved || exporting}
              aria-describedby="reading-export-scope"
              onClick={() => void exportBibtex()}
            >
              Export all (.bib)
            </Button>
            <span id="reading-export-scope" className="rc-visually-hidden">
              {status ? `Exports every paper marked ${READING_STATUS_LABELS[status].toLowerCase()}.` : "Exports your whole list."}
            </span>
          </div>
        }
      />

      <div className={styles.chips} role="group" aria-label="Filter by reading status">
        {chips.map((chip) => (
          <button key={chip.status ?? "ALL"} type="button" className={styles.chip} aria-pressed={chip.status === status} onClick={() => choose(chip.status)}>
            <span>
              {chip.label}
              <ChipCount count={chip.count} className={styles.chipCount} />
            </span>
          </button>
        ))}
      </div>

      <p role="status" className="rc-visually-hidden">
        {message}
      </p>
      <span id={NEW_TAB_NOTE} hidden>
        Opens in a new tab
      </span>
      {error && (
        <Alert tone="danger" announce className={styles.alert}>
          {error}
        </Alert>
      )}

      <h2 className={styles.resultsTitle}>{status ? READING_STATUS_LABELS[status] : "All papers"}</h2>
      {items === null ? (
        list.status === "error" ? (
          <ErrorState title="Your reading list could not be loaded" kind={list.error?.kind === "network" ? "offline" : "failed"} onRetry={list.retry} />
        ) : (
          <SkeletonList rows={3} lines={2} label="Loading your reading list" />
        )
      ) : items.length === 0 ? (
        status ? (
          <EmptyState
            variant="no-results"
            title={`No papers marked ${READING_STATUS_LABELS[status].toLowerCase()}.`}
            actions={
              <Button variant="secondary" onClick={() => choose(null)}>
                Show all papers
              </Button>
            }
          />
        ) : (
          <EmptyState
            title="Your reading list is empty."
            description={
              <>
                Use Save on a paper in <Link href="/">Literature Search</Link> to add it here.
              </>
            }
          />
        )
      ) : (
        <>
          <ul className={styles.list} aria-busy={list.status === "loading" || undefined}>
            {items.map((item) => (
              <ReadingItem
                key={item.id}
                item={item}
                selected={selected.has(item.id)}
                busy={busy.has(item.id)}
                onSelect={() => toggle(item.id)}
                onStatus={(next) => void changeStatus(item, next)}
                onNotes={(value) => void saveNotes(item, value)}
                onRemove={() => {
                  setRemoveError(null);
                  setRemoving(item);
                }}
              />
            ))}
          </ul>
          {shown && shown.total_count > PAGE_SIZE && (
            <Pagination page={page} total={shown.total_count} pageSize={PAGE_SIZE} noun="papers" label="Reading list pages" onPage={(next) => go(readingHref(status, next))} />
          )}
        </>
      )}

      <Dialog
        open={removing !== null}
        onClose={() => setRemoving(null)}
        size="sm"
        title={`Remove "${removing?.work.title ?? "this paper"}" from your reading list?`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setRemoving(null)}>
              Cancel
            </Button>
            <Button variant="danger" loading={removing !== null && busy.has(removing.id)} onClick={() => void remove()}>
              Remove
            </Button>
          </>
        }
      >
        <p>Your notes on it are deleted too. You can save the paper again from Literature Search.</p>
        {removeError && (
          <Alert tone="danger" announce>
            {removeError}
          </Alert>
        )}
      </Dialog>
    </>
  );
}

interface ReadingItemProps {
  item: ReadingListItem;
  selected: boolean;
  busy: boolean;
  onSelect: () => void;
  onStatus: (status: ReadingStatus) => void;
  onNotes: (value: string) => void;
  onRemove: () => void;
}

/** One saved paper: serif title linking to the paper, its authors, venue, year and DOI. */
function ReadingItem({ item, selected, busy, onSelect, onStatus, onNotes, onRemove }: ReadingItemProps) {
  const href = workHref(item);
  const titleId = `reading-${item.id}`;
  const facts = [item.work.authors.length > 0 ? authorLine(item.work.authors) : null, item.work.venue_name, item.work.publication_year ? String(item.work.publication_year) : null].filter(Boolean);

  return (
    <li className={styles.itemRow}>
      <article className={styles.item} aria-labelledby={titleId}>
        <div className={styles.head}>
          <span className={styles.check}>
            <input type="checkbox" checked={selected} onChange={onSelect} aria-label={`Select ${item.work.title}`} />
          </span>
          <div className={styles.main}>
            <h3 id={titleId} className={styles.title}>
              {href ? (
                <a href={href} target="_blank" rel="noopener noreferrer" aria-describedby={NEW_TAB_NOTE}>
                  {item.work.title}
                </a>
              ) : (
                item.work.title
              )}
            </h3>
            <p className={styles.facts}>
              {facts.map((fact) => (
                <span key={fact}>{fact}</span>
              ))}
              {item.work.doi && (
                <a href={doiHref(item.work.doi)} target="_blank" rel="noopener noreferrer" aria-describedby={NEW_TAB_NOTE}>
                  DOI: {bareDoi(item.work.doi)}
                </a>
              )}
            </p>
          </div>
        </div>
        <div className={styles.controls}>
          <Select label="Status" value={item.status} disabled={busy} onChange={(event) => onStatus(event.target.value as ReadingStatus)} className={styles.status}>
            {ALL_READING_STATUSES.map((value) => (
              <option key={value} value={value}>
                {READING_STATUS_LABELS[value]}
              </option>
            ))}
          </Select>
          {/* Open from the start when the paper has notes; otherwise one line until wanted. */}
          <details className={styles.notes} open={Boolean(item.notes)}>
            <summary className={styles.notesSummary}>
              {item.notes ? "Notes" : "Add notes"}
              <span className="rc-visually-hidden"> on {item.work.title}</span>
            </summary>
            <TextArea
              label="Notes"
              hint="Private; saved when you leave the box, never exported."
              rows={3}
              maxLength={10000}
              defaultValue={item.notes ?? ""}
              onBlur={(event) => onNotes(event.target.value)}
            />
          </details>
          <div className={styles.actions}>
            <Button variant="ghost" size="sm" leadingIcon={<Trash2 size={16} aria-hidden="true" />} disabled={busy} aria-label={`Remove ${item.work.title}`} onClick={onRemove}>
              Remove
            </Button>
          </div>
        </div>
      </article>
    </li>
  );
}
