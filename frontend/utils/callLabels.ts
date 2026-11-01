import { humanizeEnum } from "./date";

/*
 * A call's type, delivery mode, fee and status in words. On their own so a page that only names a
 * call (a workspace row, a workspace item) does not load the search and evidence words of
 * utils/research.ts, which re-exports these (P12).
 */

/* ── Calls for papers ───────────────────────────────────────────────────────────────────── */

const CALL_TYPE_LABELS: Record<string, string> = {
  CONFERENCE: "Conference",
  JOURNAL: "Journal",
  WORKSHOP: "Workshop",
  CALL_FOR_PAPERS: "Call for papers",
  SPECIAL_ISSUE: "Special issue",
};

export const CALL_TYPES = Object.keys(CALL_TYPE_LABELS);

export function callTypeLabel(type: string | null | undefined): string {
  if (!type) return "Call";
  return CALL_TYPE_LABELS[type] ?? humanizeEnum(type);
}

const DELIVERY_MODE_LABELS: Record<string, string> = {
  OFFLINE: "In person",
  ONLINE: "Online",
  HYBRID: "Hybrid",
};

export const DELIVERY_MODES = Object.keys(DELIVERY_MODE_LABELS);

export function deliveryModeLabel(mode: string | null | undefined): string | null {
  if (!mode) return null;
  return DELIVERY_MODE_LABELS[mode] ?? humanizeEnum(mode);
}

/**
 * A call's fee as the API records it (`apc_or_fee`), in words: "No fee", "USD 1,200",
 * "Fee charged (amount not stated)", or null when nothing is recorded.
 */
export function feeLabel(fee: Record<string, unknown> | null | undefined): string | null {
  if (!fee) return null;
  if (fee.has_fee === false || fee.amount === 0) return "No fee";
  if (typeof fee.amount === "number") {
    const currency = typeof fee.currency === "string" && fee.currency ? fee.currency : "USD";
    return `${currency} ${fee.amount.toLocaleString("en")}`;
  }
  if (fee.has_fee === true) return "Fee charged (amount not stated)";
  return null;
}

const CALL_STATUS_LABELS: Record<string, string> = {
  ACTIVE: "Open",
  EXPIRED: "Closed",
  UNVERIFIED: "Not yet verified",
  ARCHIVED: "Archived",
  DRAFT: "Draft",
};

/** A call's lifecycle status as the API records it, in words. */
export function callStatusLabel(status: string | null | undefined): string | null {
  if (!status) return null;
  return CALL_STATUS_LABELS[status] ?? humanizeEnum(status);
}
