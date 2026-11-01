import { humanizeEnum } from "./date";

/* On its own so a page that only names a person's career stage (an applicant card) does not load the
   personalization words of utils/personalization.ts, which re-exports it (P12). */

const ACADEMIC_STATUS: Record<string, string> = {
  UNDERGRADUATE: "Undergraduate",
  POSTGRADUATE: "Postgraduate",
  PHD: "PhD",
  POSTDOC: "Postdoctoral researcher",
  FACULTY: "Faculty",
  RESEARCHER: "Researcher",
  OTHER: "Other",
};

/** A career stage in words ("PhD", not "Phd"); an unset stage is null, never shown as "Unknown". */
export function academicStatusLabel(status: string | null | undefined): string | null {
  if (!status || status === "UNKNOWN") return null;
  return ACADEMIC_STATUS[status] ?? humanizeEnum(status);
}
