/** A workspace item's priority in words and level (DESIGN_SYSTEM.md §3.2). */
import { humanizeEnum } from "./date";

/** Priority is a word (with a level glyph), never a status colour. */
const PRIORITY: Record<string, { label: string; level: 1 | 2 | 3 | 4 }> = {
  LOW: { label: "Low", level: 1 },
  MEDIUM: { label: "Medium", level: 2 },
  HIGH: { label: "High", level: 3 },
  URGENT: { label: "Urgent", level: 4 },
};

export function priorityMeta(priority: string | null | undefined): { label: string; level: 1 | 2 | 3 | 4 } {
  if (!priority) return { label: "No priority", level: 1 };
  return PRIORITY[priority] ?? { label: humanizeEnum(priority), level: 2 };
}
