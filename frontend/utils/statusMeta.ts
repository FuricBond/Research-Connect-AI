/**
 * Domain status → words, tone and icon (DESIGN_SYSTEM.md §3.2, "StatusBadge").
 *
 * Every status shown to a person goes through one of these maps, so the interface never shows
 * an enum value (UNDER_REVIEW, IN_APP) and the same status looks the same everywhere.
 * Unknown values fall back to a sentence-case rendering, never to the raw enum.
 */
import type { LucideIcon } from "lucide-react";
import { CircleDashed } from "lucide-react";
import { humanizeEnum } from "./date";

export type StatusTone = "neutral" | "brand" | "brand-strong" | "info" | "success" | "warning" | "danger" | "muted";

export interface StatusMeta {
  label: string;
  tone: StatusTone;
  icon?: LucideIcon;
}

export function lookup(map: Record<string, StatusMeta>, value: string | null | undefined): StatusMeta {
  if (!value) return { label: "Unknown", tone: "muted", icon: CircleDashed };
  return map[value] ?? { label: humanizeEnum(value), tone: "neutral" };
}
