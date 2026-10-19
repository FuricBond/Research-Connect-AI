/**
 * P9 — the posting editor's model: the form's values, the backend's rules for them
 * (backend/app/schemas/research_posting.py and research_posting_application.py), and the payloads.
 *
 * Creating sends every field that has a value. Editing sends only the fields that changed (the
 * backend's PATCH applies only what it is given), so a field nobody touched — or one changed
 * elsewhere meanwhile — is never overwritten. Topics are not edited here (there is no topic
 * picker); they are never sent, so they are kept.
 */

import type {
  CommitmentType,
  CompensationType,
  OpeningTermsUpdate,
  PostingCreatePayload,
  PostingType,
  PostingUpdatePayload,
  PostingWorkMode,
  ResearchPosting,
} from "../../types/posting";
import { STRUCTURED_OPENING_TYPES } from "../../types/posting";

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

export const LIMITS = { titleMin: 5, titleMax: 300, summaryMax: 500, descriptionMin: 20, skillsMax: 25, positionsMax: 100, textMax: 255, hoursMax: 80, durationMax: 120, amountMax: 100_000_000 } as const;

export interface PostingFormValues {
  title: string;
  posting_type: PostingType;
  summary: string;
  description: string;
  skills: string;
  preferred_qualifications: string;
  institution: string;
  department: string;
  location: string;
  country: string;
  work_mode: PostingWorkMode;
  positions: string;
  deadline: string;
  start: string;
  end: string;
  contact_email: string;
  external_url: string;
  compensation_type: CompensationType;
  amount: string;
  currency: string;
  period: string;
  commitment: string;
  hours: string;
  duration: string;
  eligibility: string;
  accepts: boolean;
}

export type FieldName = keyof PostingFormValues;
export type FormErrors = Partial<Record<FieldName, string>>;

export const EMPTY_FORM: PostingFormValues = {
  title: "",
  posting_type: "PROJECT",
  summary: "",
  description: "",
  skills: "",
  preferred_qualifications: "",
  institution: "",
  department: "",
  location: "",
  country: "",
  work_mode: "ONSITE",
  positions: "1",
  deadline: "",
  start: "",
  end: "",
  contact_email: "",
  external_url: "",
  compensation_type: "UNSPECIFIED",
  amount: "",
  currency: "",
  period: "",
  commitment: "",
  hours: "",
  duration: "",
  eligibility: "",
  accepts: false,
};

const text = (value: string | null | undefined) => value ?? "";
const number = (value: number | null | undefined) => (value === null || value === undefined ? "" : String(value));
/** The calendar day of a stored deadline, in UTC (the editor sends a day as midnight UTC). */
const isoDay = (value: string | null | undefined) => (value ? new Date(value).toISOString().slice(0, 10) : "");

export function fromPosting(posting: ResearchPosting): PostingFormValues {
  const terms = posting.opening_terms;
  return {
    title: posting.title,
    posting_type: posting.posting_type,
    summary: text(posting.summary),
    description: posting.description,
    skills: posting.required_skills.join(", "),
    preferred_qualifications: text(posting.preferred_qualifications),
    institution: text(posting.institution),
    department: text(posting.department),
    location: text(posting.location),
    country: text(posting.country),
    work_mode: posting.work_mode,
    positions: String(posting.positions_available),
    deadline: isoDay(posting.application_deadline),
    start: text(posting.expected_start_date),
    end: text(posting.expected_end_date),
    contact_email: text(posting.contact_email),
    external_url: text(posting.external_url),
    compensation_type: terms.compensation_type,
    amount: number(terms.compensation_amount),
    currency: text(terms.compensation_currency),
    period: text(terms.compensation_period),
    commitment: text(terms.commitment_type),
    hours: number(terms.hours_per_week),
    duration: number(terms.duration_months),
    eligibility: text(terms.eligibility_requirements),
    accepts: terms.accepts_applications,
  };
}

export const isStructured = (type: PostingType) => STRUCTURED_OPENING_TYPES.includes(type);

/** Skills as the backend keeps them: trimmed, without blanks or case-insensitive repeats, in order. */
export function parseSkills(value: string): string[] {
  const seen = new Set<string>();
  const skills: string[] = [];
  for (const raw of value.split(",")) {
    const skill = raw.trim();
    if (!skill || seen.has(skill.toLowerCase())) continue;
    seen.add(skill.toLowerCase());
    skills.push(skill);
  }
  return skills;
}

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function isWebAddress(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

function wholeNumber(value: string, min: number, max: number): boolean {
  const n = Number(value);
  return value.trim() !== "" && Number.isInteger(n) && n >= min && n <= max;
}

/** Today's date (UTC), as the deadline's day is sent: a deadline must be a later day. */
function todayUtc(now: Date): string {
  return now.toISOString().slice(0, 10);
}

/**
 * The backend's rules, checked before anything is sent. When editing, only fields that changed are
 * checked: a value stored before these rules existed never blocks saving another field.
 */
export function validate(values: PostingFormValues, initial: PostingFormValues | null, now = new Date()): FormErrors {
  const errors: FormErrors = {};
  const check = (field: FieldName) => initial === null || values[field] !== initial[field];
  const title = values.title.trim();
  if (check("title") && (title.length < LIMITS.titleMin || title.length > LIMITS.titleMax)) errors.title = `Give a title of ${LIMITS.titleMin} to ${LIMITS.titleMax} characters.`;
  if (check("summary") && values.summary.trim().length > LIMITS.summaryMax) errors.summary = `Keep the summary to ${LIMITS.summaryMax} characters.`;
  if (check("description") && values.description.trim().length < LIMITS.descriptionMin) errors.description = `Describe the posting in at least ${LIMITS.descriptionMin} characters.`;
  if (check("skills") && parseSkills(values.skills).length > LIMITS.skillsMax) errors.skills = `List at most ${LIMITS.skillsMax} skills.`;
  if (check("positions") && !wholeNumber(values.positions, 1, LIMITS.positionsMax)) errors.positions = `Give a whole number from 1 to ${LIMITS.positionsMax}.`;
  for (const field of ["institution", "department", "location"] as const) {
    if (check(field) && values[field].trim().length > LIMITS.textMax) errors[field] = `Keep this to ${LIMITS.textMax} characters.`;
  }
  if (check("country") && values.country.trim() !== "" && !/^[A-Za-z]{2}$/.test(values.country.trim())) errors.country = "Use a two-letter country code, such as US.";
  if (check("contact_email") && values.contact_email.trim() !== "" && !EMAIL.test(values.contact_email.trim())) errors.contact_email = "Enter an email address, such as name@university.edu.";
  if (check("external_url") && values.external_url.trim() !== "" && !isWebAddress(values.external_url.trim())) errors.external_url = "Enter a web address that starts with https://.";
  // The backend refuses a deadline that is not in the future when a posting is created.
  if (initial === null && values.deadline !== "" && values.deadline <= todayUtc(now)) errors.deadline = "Choose a day after today.";
  if ((check("start") || check("end")) && values.start !== "" && values.end !== "" && values.end < values.start) errors.end = "The end cannot be before the start.";
  if (isStructured(values.posting_type)) {
    if (check("amount") && values.amount.trim() !== "" && !(Number(values.amount) >= 0 && Number(values.amount) <= LIMITS.amountMax)) errors.amount = "Give an amount of 0 or more.";
    if (check("currency") && values.currency.trim() !== "" && !/^[A-Za-z]{3}$/.test(values.currency.trim())) errors.currency = "Use a three-letter currency code, such as USD.";
    if (check("hours") && values.hours.trim() !== "" && !wholeNumber(values.hours, 1, LIMITS.hoursMax)) errors.hours = `Give a whole number from 1 to ${LIMITS.hoursMax}.`;
    if (check("duration") && values.duration.trim() !== "" && !wholeNumber(values.duration, 1, LIMITS.durationMax)) errors.duration = `Give a whole number from 1 to ${LIMITS.durationMax}.`;
  }
  return errors;
}

const optional = (value: string) => (value.trim() === "" ? null : value.trim());
const day = (value: string) => (value === "" ? null : new Date(value).toISOString());
const optionalNumber = (value: string) => (value.trim() === "" ? null : Number(value));

function terms(values: PostingFormValues): Required<OpeningTermsUpdate> {
  return {
    compensation_type: values.compensation_type,
    compensation_amount: optionalNumber(values.amount),
    compensation_currency: values.currency.trim() === "" ? null : values.currency.trim().toUpperCase(),
    compensation_period: values.period === "" ? null : values.period,
    commitment_type: (values.commitment === "" ? null : values.commitment) as CommitmentType | null,
    hours_per_week: optionalNumber(values.hours),
    duration_months: optionalNumber(values.duration),
    eligibility_requirements: optional(values.eligibility),
    accepts_applications: values.accepts,
  };
}

/** Each field as the backend takes it. Blank institution and department are left out on create (the author's own are used). */
function fields(values: PostingFormValues): Omit<Required<PostingCreatePayload>, "topic_ids" | "opening_terms"> {
  return {
    title: values.title.trim(),
    posting_type: values.posting_type,
    summary: optional(values.summary),
    description: values.description.trim(),
    required_skills: parseSkills(values.skills),
    preferred_qualifications: optional(values.preferred_qualifications),
    institution: optional(values.institution),
    department: optional(values.department),
    location: optional(values.location),
    country: values.country.trim() === "" ? null : values.country.trim().toUpperCase(),
    work_mode: values.work_mode,
    positions_available: Number(values.positions),
    application_deadline: day(values.deadline),
    expected_start_date: values.start === "" ? null : values.start,
    expected_end_date: values.end === "" ? null : values.end,
    contact_email: values.contact_email.trim() === "" ? null : values.contact_email.trim().toLowerCase(),
    external_url: optional(values.external_url),
  };
}

export function createPayload(values: PostingFormValues): PostingCreatePayload {
  const all = fields(values);
  const payload: PostingCreatePayload = { ...all };
  if (all.institution === null) delete payload.institution;
  if (all.department === null) delete payload.department;
  // Appointment terms only mean something for funded openings; the server ignores them otherwise.
  if (isStructured(values.posting_type)) payload.opening_terms = terms(values);
  return payload;
}

/** Which form fields make up each payload field (to know what changed). */
const SOURCES: Record<keyof ReturnType<typeof fields>, FieldName> = {
  title: "title",
  posting_type: "posting_type",
  summary: "summary",
  description: "description",
  required_skills: "skills",
  preferred_qualifications: "preferred_qualifications",
  institution: "institution",
  department: "department",
  location: "location",
  country: "country",
  work_mode: "work_mode",
  positions_available: "positions",
  application_deadline: "deadline",
  expected_start_date: "start",
  expected_end_date: "end",
  contact_email: "contact_email",
  external_url: "external_url",
};
const TERM_SOURCES: Record<keyof OpeningTermsUpdate, FieldName> = {
  compensation_type: "compensation_type",
  compensation_amount: "amount",
  compensation_currency: "currency",
  compensation_period: "period",
  commitment_type: "commitment",
  hours_per_week: "hours",
  duration_months: "duration",
  eligibility_requirements: "eligibility",
  accepts_applications: "accepts",
};

/** Only what changed; an empty object when nothing did. */
export function updatePayload(values: PostingFormValues, initial: PostingFormValues): PostingUpdatePayload {
  const next = fields(values);
  const payload: Record<string, unknown> = {};
  for (const [key, source] of Object.entries(SOURCES) as [keyof typeof next, FieldName][]) {
    if (key === "required_skills" ? parseSkills(values.skills).join("\n") !== parseSkills(initial.skills).join("\n") : values[source] !== initial[source]) {
      payload[key] = next[key];
    }
  }
  if (isStructured(values.posting_type)) {
    const nextTerms = terms(values);
    const changed: Record<string, unknown> = {};
    for (const [key, source] of Object.entries(TERM_SOURCES) as [keyof OpeningTermsUpdate, FieldName][]) {
      if (values[source] !== initial[source]) changed[key] = nextTerms[key];
    }
    if (Object.keys(changed).length > 0) payload.opening_terms = changed;
  } else if (isStructured(initial.posting_type) && initial.accepts) {
    // A supervisor-led category takes no applications on the platform. The backend only enforces
    // that when terms are sent, so the change of category sends it too, or students would still
    // be offered an application the server refuses.
    payload.opening_terms = { accepts_applications: false };
  }
  return payload as PostingUpdatePayload;
}

/** The fields in the order they appear, to move focus to the first one that needs attention. */
export const FIELD_ORDER: FieldName[] = [
  "title",
  "posting_type",
  "summary",
  "work_mode",
  "positions",
  "location",
  "country",
  "institution",
  "department",
  "description",
  "preferred_qualifications",
  "skills",
  "deadline",
  "start",
  "end",
  "compensation_type",
  "amount",
  "currency",
  "period",
  "commitment",
  "hours",
  "duration",
  "eligibility",
  "accepts",
  "contact_email",
  "external_url",
];
