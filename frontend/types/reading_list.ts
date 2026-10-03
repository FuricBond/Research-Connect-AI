/**
 * Phase 5.14 — Personal reading list.
 *
 * Mirrors backend/app/schemas/reading_list.py. Items belong to the signed-in user; notes are
 * private and never appear in a BibTeX export.
 */

export type ReadingStatus = "TO_READ" | "READING" | "DONE";

export interface ReadingListWorkSummary {
  id: string;
  title: string;
  doi: string | null;
  publication_year: number | null;
  work_type: string | null;
  venue_name: string | null;
  authors: string[];
  landing_page_url: string | null;
}

export interface ReadingListItem {
  id: string;
  work_id: string;
  status: ReadingStatus;
  notes: string | null;
  status_updated_at: string;
  /** First time the item entered READING. */
  started_at: string | null;
  /** When it entered DONE; null again if it leaves DONE. */
  finished_at: string | null;
  created_at: string;
  updated_at: string;
  work: ReadingListWorkSummary;
}

export interface ReadingListResponse {
  items: ReadingListItem[];
  total_count: number;
  limit: number;
  offset: number;
  /** Counts across the whole list, regardless of the status filter. */
  counts_by_status: Record<ReadingStatus, number>;
}

export interface ReadingListLookupResponse {
  /** work_id -> reading list item id, for the works already saved. */
  saved: Record<string, string>;
}

export interface ReadingListItemUpdate {
  status?: ReadingStatus;
  /** null clears the notes. */
  notes?: string | null;
}

export const READING_STATUS_LABELS: Record<ReadingStatus, string> = {
  TO_READ: "To read",
  READING: "Reading",
  DONE: "Done",
};

export const ALL_READING_STATUSES: ReadingStatus[] = ["TO_READ", "READING", "DONE"];
