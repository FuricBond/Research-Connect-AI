import type { CommitmentType, CompensationType, PostingType, PostingWorkMode } from "../../types/posting";

/** The choices a posting offers. On their own: lists and filters need these, not the editor's rules. */
export const POSTING_TYPES: PostingType[] = ["PROJECT", "THESIS_TOPIC", "COLLABORATION", "LAB_ROTATION", "INTERNSHIP", "RESEARCH_ASSISTANTSHIP", "POSTDOC"];
export const WORK_MODES: PostingWorkMode[] = ["ONSITE", "REMOTE", "HYBRID"];
export const COMPENSATION_TYPES: CompensationType[] = ["UNSPECIFIED", "STIPEND", "SALARY", "HOURLY", "SCHOLARSHIP", "GRANT_FUNDED", "UNPAID"];
export const COMMITMENT_TYPES: CommitmentType[] = ["FULL_TIME", "PART_TIME", "FLEXIBLE"];
/** backend COMPENSATION_PERIODS */
export const COMPENSATION_PERIODS: { value: string; label: string }[] = [
  { value: "HOUR", label: "Hour" },
  { value: "WEEK", label: "Week" },
  { value: "MONTH", label: "Month" },
  { value: "YEAR", label: "Year" },
  { value: "TOTAL", label: "In total" },
];
