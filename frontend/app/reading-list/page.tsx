"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import "../../styles/postings.css";
import "../../styles/peers.css";
import { AlertCircle, BookMarked, Download, Info, Trash2 } from "lucide-react";
import { RequireAuth } from "../../components/auth/RequireAuth";
import {
  downloadReadingListBibtex,
  fetchReadingList,
  removeReadingListItem,
  updateReadingListItem,
} from "../../services/api";
import type { ReadingListItem, ReadingListResponse, ReadingStatus } from "../../types/reading_list";
import { ALL_READING_STATUSES, READING_STATUS_LABELS } from "../../types/reading_list";

const PAGE_SIZE = 50;
// The export takes the chosen ids in its URL, and the API accepts at most this many.
const EXPORT_SELECTION_LIMIT = 200;

function workHref(item: ReadingListItem): string | null {
  if (item.work.doi) return `https://doi.org/${item.work.doi}`;
  return item.work.landing_page_url;
}

function authorLine(authors: string[]): string {
  if (authors.length <= 3) return authors.join(", ");
  return `${authors.slice(0, 3).join(", ")} et al.`;
}

function ReadingListPage() {
  const [statusFilter, setStatusFilter] = useState<ReadingStatus | null>(null);
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<ReadingListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busyId, setBusyId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError(null);
      try {
        const page = await fetchReadingList(
          { status: statusFilter ?? undefined, limit: PAGE_SIZE, offset },
          signal
        );
        if (signal?.aborted) return;
        if (page.items.length === 0 && offset > 0 && page.total_count > 0) {
          // The last item on a later page was removed: show the page before it instead.
          setOffset(Math.max(0, offset - PAGE_SIZE));
          return;
        }
        setResult(page);
      } catch (err) {
        if (signal?.aborted) return;
        setError(err instanceof Error ? err.message : "Failed to load your reading list");
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [statusFilter, offset]
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const chooseTab = (status: ReadingStatus | null) => {
    setStatusFilter(status);
    setOffset(0);
    setSelected(new Set());
  };

  const replaceItem = (updated: ReadingListItem) => {
    setResult((previous) =>
      previous && {
        ...previous,
        items: previous.items.map((item) => (item.id === updated.id ? updated : item)),
      }
    );
  };

  const changeStatus = async (item: ReadingListItem, status: ReadingStatus) => {
    setBusyId(item.id);
    setError(null);
    try {
      await updateReadingListItem(item.id, { status });
      // Reload: the counts change, and under a status filter the item may leave the view.
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update the status");
    } finally {
      setBusyId(null);
    }
  };

  const saveNotes = async (item: ReadingListItem, value: string) => {
    const notes = value.trim() ? value : null;
    if (notes === item.notes) return;
    setError(null);
    try {
      replaceItem(await updateReadingListItem(item.id, { notes }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save your notes");
    }
  };

  const remove = async (item: ReadingListItem) => {
    setBusyId(item.id);
    setError(null);
    try {
      await removeReadingListItem(item.id);
      setSelected((previous) => {
        const next = new Set(previous);
        next.delete(item.id);
        return next;
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove the paper");
    } finally {
      setBusyId(null);
    }
  };

  const toggleSelected = (itemId: string) => {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  };

  const exportBibtex = async (itemIds?: string[]) => {
    if (itemIds && itemIds.length > EXPORT_SELECTION_LIMIT) {
      setError(
        `Select at most ${EXPORT_SELECTION_LIMIT} papers to export, or use Export all (.bib).`
      );
      return;
    }
    setExporting(true);
    setError(null);
    try {
      await downloadReadingListBibtex(
        itemIds ? { itemIds } : { status: statusFilter ?? undefined }
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to export your reading list");
    } finally {
      setExporting(false);
    }
  };

  const counts = result?.counts_by_status;
  const totalSaved = counts ? ALL_READING_STATUSES.reduce((sum, s) => sum + (counts[s] ?? 0), 0) : 0;
  const tabs: { status: ReadingStatus | null; label: string; count: number }[] = [
    { status: null, label: "All", count: totalSaved },
    ...ALL_READING_STATUSES.map((status) => ({
      status,
      label: READING_STATUS_LABELS[status],
      count: counts?.[status] ?? 0,
    })),
  ];

  return (
    <div className="postings-page">
      <header className="postings-header">
        <div className="postings-title-group">
          <h1>
            <BookMarked size={20} aria-hidden="true" /> Reading List
          </h1>
          <p className="postings-subtitle">
            Papers you saved from Literature Search. Track what you are reading, keep private notes
            and export citations as BibTeX. Your notes stay here: they are never exported.
          </p>
        </div>
        <div className="posting-badges">
          <button
            type="button"
            className="posting-btn"
            onClick={() => exportBibtex([...selected])}
            disabled={selected.size === 0 || exporting}
          >
            <Download size={13} aria-hidden="true" />
            Export selected (.bib)
          </button>
          <button
            type="button"
            className="posting-btn"
            onClick={() => exportBibtex()}
            disabled={totalSaved === 0 || exporting}
            title={statusFilter ? `Exports every paper marked ${READING_STATUS_LABELS[statusFilter]}` : "Exports your whole list"}
          >
            <Download size={13} aria-hidden="true" />
            Export all (.bib)
          </button>
        </div>
      </header>

      {error && (
        <div className="postings-error" role="alert">
          <AlertCircle size={15} aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <div className="peer-interest-chips" role="group" aria-label="Filter by reading status">
        {tabs.map((tab) => {
          const active = tab.status === statusFilter;
          return (
            <button
              key={tab.status ?? "ALL"}
              type="button"
              className={`peer-chip${active ? " active" : ""}`}
              aria-pressed={active}
              onClick={() => chooseTab(tab.status)}
            >
              {tab.label} ({tab.count})
            </button>
          );
        })}
      </div>

      {loading && !result ? (
        <div className="postings-loading">Loading your reading list…</div>
      ) : result && result.items.length > 0 ? (
        <>
          <div className="postings-list">
            {result.items.map((item) => {
              const href = workHref(item);
              const busy = busyId === item.id;
              return (
                <article key={item.id} className="posting-card">
                  <div className="posting-card-head">
                    <input
                      type="checkbox"
                      checked={selected.has(item.id)}
                      onChange={() => toggleSelected(item.id)}
                      aria-label={`Select ${item.work.title}`}
                    />
                    <h3 className="posting-card-title">
                      {href ? (
                        <a href={href} target="_blank" rel="noopener noreferrer">
                          {item.work.title}
                        </a>
                      ) : (
                        item.work.title
                      )}
                    </h3>
                    <span className="posting-badge type">{READING_STATUS_LABELS[item.status]}</span>
                  </div>

                  <div className="posting-meta">
                    {item.work.authors.length > 0 && (
                      <span className="posting-meta-item">{authorLine(item.work.authors)}</span>
                    )}
                    {item.work.venue_name && (
                      <span className="posting-meta-item">{item.work.venue_name}</span>
                    )}
                    {item.work.publication_year && (
                      <span className="posting-meta-item">{item.work.publication_year}</span>
                    )}
                    {item.work.doi && (
                      <a
                        className="posting-meta-item"
                        href={`https://doi.org/${item.work.doi}`}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        DOI: {item.work.doi}
                      </a>
                    )}
                  </div>

                  <div className="posting-form-grid">
                    <div className="posting-field">
                      <label htmlFor={`status-${item.id}`}>Status</label>
                      <select
                        id={`status-${item.id}`}
                        value={item.status}
                        disabled={busy}
                        onChange={(e) => changeStatus(item, e.target.value as ReadingStatus)}
                      >
                        {ALL_READING_STATUSES.map((status) => (
                          <option key={status} value={status}>
                            {READING_STATUS_LABELS[status]}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="posting-field">
                    <label htmlFor={`notes-${item.id}`}>
                      Notes <span className="posting-field-hint">private, saved when you leave the box</span>
                    </label>
                    <textarea
                      id={`notes-${item.id}`}
                      rows={3}
                      maxLength={10000}
                      defaultValue={item.notes ?? ""}
                      onBlur={(e) => saveNotes(item, e.target.value)}
                      placeholder="What to remember about this paper."
                    />
                  </div>

                  <div>
                    <button
                      type="button"
                      className="posting-btn"
                      onClick={() => remove(item)}
                      disabled={busy}
                      aria-label={`Remove ${item.work.title}`}
                    >
                      <Trash2 size={13} aria-hidden="true" />
                      Remove
                    </button>
                  </div>
                </article>
              );
            })}
          </div>

          {result.total_count > PAGE_SIZE && (
            <div className="postings-filters">
              <button
                type="button"
                className="posting-btn"
                disabled={offset === 0 || loading}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </button>
              <span className="postings-subtitle">
                {offset + 1}–{Math.min(offset + PAGE_SIZE, result.total_count)} of {result.total_count}
              </span>
              <button
                type="button"
                className="posting-btn"
                disabled={offset + PAGE_SIZE >= result.total_count || loading}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="postings-empty">
          <Info size={15} aria-hidden="true" />
          {statusFilter ? (
            <p>No papers marked {READING_STATUS_LABELS[statusFilter]}.</p>
          ) : (
            <p>
              Your reading list is empty. Use Save on a paper in{" "}
              <Link href="/">Literature Search</Link> to add it here.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function ReadingListPageRoute() {
  return (
    <RequireAuth>
      <ReadingListPage />
    </RequireAuth>
  );
}
