/**
 * P9 — the faculty side of research postings, in words and order (FRONTEND_REDESIGN_PLAN.md §14).
 *
 * The server says which moves are possible (`allowed_transitions`); these helpers only decide how
 * they are named and in which order they are offered. The server sends both lists sorted by their
 * enum names (OFFERED, REJECTED, SHORTLISTED, UNDER_REVIEW), so that order is never used.
 */

import type { ApplicationStatus, PostingApplication, PostingStatus, ResearchPosting } from "../types/posting";

// ── Applications: the author's review decisions ──────────────────────────────

/**
 * The review pipeline (backend AUTHOR_TRANSITIONS): every forward move goes SUBMITTED →
 * UNDER_REVIEW → SHORTLISTED → OFFERED, never back. Decisions are offered in that order, and
 * "Not selected" (REJECTED) — possible from every open stage, final, and the end of the process
 * for the applicant — comes last, apart, and only after a confirmation (plan §14, P1-9).
 */
export const DECISION_PIPELINE: readonly ApplicationStatus[] = ["UNDER_REVIEW", "SHORTLISTED", "OFFERED"];
export const NOT_SELECTED: ApplicationStatus = "REJECTED";

const DECISION_LABELS: Partial<Record<ApplicationStatus, string>> = {
  UNDER_REVIEW: "Mark under review",
  SHORTLISTED: "Shortlist",
  OFFERED: "Make offer",
  REJECTED: "Not selected",
};

export interface Decision {
  target: ApplicationStatus;
  label: string;
  /** One primary per card: Shortlist while submitted or under review, Make offer once shortlisted. */
  variant: "primary" | "secondary" | "danger-ghost";
  /** Asks before it is sent ("Not selected"). */
  confirm: boolean;
}

/**
 * The decisions the posting's author may take on this application now, in pipeline order with
 * "Not selected" last. Empty for anyone else (the applicant's own moves are not decisions) and
 * for a decided application.
 */
export function decisionsFor(application: Pick<PostingApplication, "allowed_transitions" | "is_posting_author">): Decision[] {
  if (!application.is_posting_author) return [];
  const allowed = new Set(application.allowed_transitions);
  const forward = DECISION_PIPELINE.filter((target) => allowed.has(target));
  const primary = forward.includes("SHORTLISTED") ? "SHORTLISTED" : forward.includes("OFFERED") ? "OFFERED" : null;
  const decisions: Decision[] = forward.map((target) => ({
    target,
    label: DECISION_LABELS[target] ?? target,
    variant: target === primary ? "primary" : "secondary",
    confirm: false,
  }));
  if (allowed.has(NOT_SELECTED)) decisions.push({ target: NOT_SELECTED, label: DECISION_LABELS.REJECTED!, variant: "danger-ghost", confirm: true });
  return decisions;
}

/** The words for a decision the server refused or that failed: "Ada Lovelace could not be shortlisted." */
export function decisionFailed(name: string, target: ApplicationStatus): string {
  switch (target) {
    case "UNDER_REVIEW":
      return `${name} could not be marked under review.`;
    case "SHORTLISTED":
      return `${name} could not be shortlisted.`;
    case "OFFERED":
      return `The offer to ${name} could not be made.`;
    case "REJECTED":
      return `${name} could not be marked not selected.`;
    default:
      return `The application of ${name} could not be changed.`;
  }
}

/** What happens next, for an application with nothing (more) for the author to decide. */
export function applicationOutcome(status: ApplicationStatus): string | null {
  switch (status) {
    case "OFFERED":
      return "Waiting for the applicant to accept or decline your offer.";
    case "ACCEPTED":
      return "The applicant accepted your offer.";
    case "DECLINED":
      return "The applicant declined your offer.";
    case "REJECTED":
      return "Not selected. The applicant has been told.";
    case "WITHDRAWN":
      return "The applicant withdrew this application.";
    default:
      return null;
  }
}

/** Statuses in pipeline order, for filters and counts. */
export const APPLICATION_STATUSES: readonly ApplicationStatus[] = ["SUBMITTED", "UNDER_REVIEW", "SHORTLISTED", "OFFERED", "ACCEPTED", "REJECTED", "DECLINED", "WITHDRAWN"];

/** Waiting on the author (the dashboard's "Needs your decision"). */
export const AWAITING_DECISION: ReadonlySet<ApplicationStatus> = new Set(["SUBMITTED", "UNDER_REVIEW"]);

// ── Postings: the author's lifecycle actions ────────────────────────────────

/**
 * The order lifecycle actions are offered in (backend VALID_TRANSITIONS decides which): publish or
 * reopen first, then Close and Mark filled (the main ways a posting ends), then the quieter moves,
 * and "Cancel posting" — final, it can only be archived afterwards — last, after a confirmation.
 */
const POSTING_ACTION_ORDER: readonly PostingStatus[] = ["OPEN", "CLOSED", "FILLED", "DRAFT", "ARCHIVED", "CANCELLED"];

export interface PostingAction {
  target: PostingStatus;
  label: string;
  variant: "primary" | "secondary" | "ghost" | "danger-ghost";
  confirm: boolean;
}

export function postingActionsFor(posting: Pick<ResearchPosting, "allowed_transitions" | "is_owner" | "status" | "published_at">): PostingAction[] {
  if (!posting.is_owner) return [];
  const allowed = new Set(posting.allowed_transitions);
  return POSTING_ACTION_ORDER.filter((target) => allowed.has(target)).map((target): PostingAction => {
    switch (target) {
      case "OPEN":
        // Publishing a draft is the one main action; reopening a closed posting is a choice.
        return posting.status === "DRAFT" && posting.published_at === null
          ? { target, label: "Publish", variant: "primary", confirm: false }
          : { target, label: posting.status === "DRAFT" ? "Publish again" : "Reopen", variant: "secondary", confirm: false };
      case "CLOSED":
        return { target, label: "Close", variant: "secondary", confirm: false };
      case "FILLED":
        return { target, label: "Mark filled", variant: "secondary", confirm: false };
      case "DRAFT":
        return { target, label: "Return to draft", variant: "ghost", confirm: false };
      case "ARCHIVED":
        return { target, label: "Archive", variant: "ghost", confirm: false };
      default:
        return { target, label: "Cancel posting", variant: "danger-ghost", confirm: true };
    }
  });
}

/** What a posting's status means for researchers, in one line (the author's view). */
export function postingVisibility(status: PostingStatus): string {
  switch (status) {
    case "DRAFT":
      return "Draft: only you can see it until you publish it.";
    case "OPEN":
      return "Published: researchers can find it.";
    case "CLOSED":
      return "Closed: researchers no longer see it. You can reopen it.";
    case "FILLED":
      return "Filled: researchers no longer see it.";
    case "CANCELLED":
      return "Cancelled: researchers no longer see it. It can only be archived.";
    default:
      return "Archived: kept for your records; it can no longer change.";
  }
}

/** The backend's edit rule (update_posting): everything but an archived posting can be edited. */
export function canEdit(posting: Pick<ResearchPosting, "is_owner" | "status">): boolean {
  return posting.is_owner && posting.status !== "ARCHIVED";
}

// ── Addresses ────────────────────────────────────────────────────────────────

export const POSTING_STATUSES: readonly PostingStatus[] = ["DRAFT", "OPEN", "CLOSED", "FILLED", "CANCELLED", "ARCHIVED"];
export const MY_POSTINGS_HREF = "/postings?view=mine";
export const APPLICANTS_HREF = "/postings/applicants";
export const NEW_POSTING_HREF = "/postings/new";
export const MINE_PAGE_SIZE = 25;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export interface MineQuery {
  status: PostingStatus | null;
  page: number;
}

/** `/postings?view=mine&status=DRAFT&page=2`; anything else in the address is ignored. */
export function readMineQuery(params: URLSearchParams): MineQuery {
  const status = params.get("status");
  const page = Number(params.get("page"));
  return {
    status: POSTING_STATUSES.includes(status as PostingStatus) ? (status as PostingStatus) : null,
    page: Number.isInteger(page) && page > 1 ? page : 1,
  };
}

export function mineHref(query: MineQuery): string {
  const params = new URLSearchParams({ view: "mine" });
  if (query.status) params.set("status", query.status);
  if (query.page > 1) params.set("page", String(query.page));
  return `/postings?${params.toString()}`;
}

export interface InboxQuery {
  status: ApplicationStatus | null;
  posting: string | null;
}

/** `/postings/applicants?status=SUBMITTED&posting=<id>`. */
export function readInboxQuery(params: URLSearchParams): InboxQuery {
  const status = params.get("status");
  const posting = params.get("posting");
  return {
    status: APPLICATION_STATUSES.includes(status as ApplicationStatus) ? (status as ApplicationStatus) : null,
    posting: posting && UUID.test(posting) ? posting : null,
  };
}

export function inboxHref(query: InboxQuery): string {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.posting) params.set("posting", query.posting);
  const text = params.toString();
  return `${APPLICANTS_HREF}${text ? `?${text}` : ""}`;
}

// ── The inbox's aggregation ──────────────────────────────────────────────────

/**
 * Postings the inbox reads applications for: there is no aggregate endpoint (plan Q4), so one
 * request per posting, for at most this many (plan §14: "the 10 most recent open postings").
 */
export const INBOX_POSTINGS = 10;

function newestFirst(a: ResearchPosting, b: ResearchPosting): number {
  const at = (posting: ResearchPosting) => Date.parse(posting.published_at ?? posting.created_at) || 0;
  return at(b) - at(a) || b.id.localeCompare(a.id);
}

/**
 * Which postings the inbox asks about: the INBOX_POSTINGS most recently published open postings
 * that have applications (a posting without any has nothing to show, so it costs no request).
 * `later` are open postings with applications beyond the cap; `closed` are postings that are no
 * longer open but have applications — both are named and linked, never silently dropped.
 */
export function inboxPostings(postings: readonly ResearchPosting[]): { read: ResearchPosting[]; later: ResearchPosting[]; closed: ResearchPosting[] } {
  const own = postings.filter((posting) => posting.is_owner && posting.application_count > 0);
  const open = own.filter((posting) => posting.status === "OPEN").sort(newestFirst);
  return {
    read: open.slice(0, INBOX_POSTINGS),
    later: open.slice(INBOX_POSTINGS),
    closed: own.filter((posting) => posting.status !== "OPEN").sort(newestFirst),
  };
}

/** Only web addresses become links: text someone typed is never a script or another scheme. */
export function webAddress(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
}

/** Whether a server answer is at least as new as another of the same object. */
export function isNewer(candidate: { updated_at: string }, than: { updated_at: string }): boolean {
  return (Date.parse(candidate.updated_at) || 0) >= (Date.parse(than.updated_at) || 0);
}
