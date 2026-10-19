"use client";

import { useRouter } from "next/navigation";
import { useMemo, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { ApiError, createPosting, updatePosting } from "../../services/api";
import type { CompensationType, PostingType, PostingWorkMode, ResearchPosting } from "../../types/posting";
import { COMMITMENT_TYPE_LABELS, COMPENSATION_TYPE_LABELS, POSTING_TYPE_LABELS, WORK_MODE_LABELS } from "../../types/posting";
import { MY_POSTINGS_HREF } from "../../utils/postings";
import { useSession } from "../auth/SessionProvider";
import { Breadcrumb } from "../ui/Breadcrumb/Breadcrumb";
import { Button, ButtonLink } from "../ui/Button/Button";
import { Checkbox, Select, TextArea, TextInput } from "../ui/Field/Field";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { Alert } from "../ui/State/State";
import { PreviewCard } from "./lazy";
import {
  COMMITMENT_TYPES,
  COMPENSATION_PERIODS,
  COMPENSATION_TYPES,
  createPayload,
  EMPTY_FORM,
  FIELD_ORDER,
  fromPosting,
  isStructured,
  LIMITS,
  parseSkills,
  POSTING_TYPES,
  updatePayload,
  validate,
  WORK_MODES,
  type FieldName,
  type FormErrors,
  type PostingFormValues,
} from "./postingForm";
import styles from "./Faculty.module.css";

const FIELD_LABELS: Record<FieldName, string> = {
  title: "Title",
  posting_type: "Category",
  summary: "Summary",
  description: "Description",
  skills: "Required skills",
  preferred_qualifications: "Preferred qualifications",
  institution: "Institution",
  department: "Department",
  location: "Location",
  country: "Country",
  work_mode: "Work mode",
  positions: "Positions available",
  deadline: "Application deadline",
  start: "Expected start",
  end: "Expected end",
  contact_email: "Contact email",
  external_url: "Official page",
  compensation_type: "Compensation",
  amount: "Amount",
  currency: "Currency",
  period: "Per",
  commitment: "Commitment",
  hours: "Hours per week",
  duration: "Duration in months",
  eligibility: "Eligibility",
  accepts: "Applications on this platform",
};

const fieldId = (field: FieldName) => `posting-${field}`;

function saveError(error: unknown, creating: boolean): string {
  const kept = "Nothing you entered was lost.";
  if (error instanceof ApiError) {
    if (error.status === 403) return `${creating ? "Only faculty and administrator accounts can write postings." : "Only the posting’s author can edit it."} ${kept}`;
    if (error.status === 409) return creating ? `Create your researcher profile before writing postings. ${kept}` : `An archived posting can no longer be edited. ${kept}`;
    if (error.status === 404) return `This posting no longer exists, or it is no longer visible to you. ${kept}`;
    if (error.status === 400 || error.status === 422) return `Some of the fields were not accepted. Check them and try again. ${kept}`;
    if (error.status === 429) return `Too many requests; wait a moment and try again. ${kept}`;
    return `The posting could not be saved. ${kept} Try again.`;
  }
  return `The posting could not be saved: check your connection. ${kept}`;
}

/** The PostingCard researchers will see, built from what is in the form. */
function previewOf(values: PostingFormValues, base: ResearchPosting | null, authorName: string | null): ResearchPosting {
  const now = new Date().toISOString();
  const trimmed = (value: string) => (value.trim() === "" ? null : value.trim());
  return {
    id: base?.id ?? "preview",
    author: base?.author ?? { profile_id: "preview", full_name: authorName, institution: null, department: null, academic_status: null },
    title: values.title.trim() || "Your posting’s title",
    posting_type: values.posting_type,
    status: base?.status ?? "DRAFT",
    summary: trimmed(values.summary),
    description: values.description,
    required_skills: parseSkills(values.skills),
    preferred_qualifications: trimmed(values.preferred_qualifications),
    institution: trimmed(values.institution),
    department: trimmed(values.department),
    location: trimmed(values.location),
    country: trimmed(values.country)?.toUpperCase() ?? null,
    work_mode: values.work_mode,
    positions_available: Number(values.positions) >= 1 ? Math.floor(Number(values.positions)) : 1,
    application_deadline: values.deadline ? new Date(values.deadline).toISOString() : null,
    expected_start_date: values.start || null,
    expected_end_date: values.end || null,
    contact_email: trimmed(values.contact_email),
    external_url: trimmed(values.external_url),
    topics: base?.topics ?? [],
    opening_terms: base?.opening_terms ?? {
      compensation_type: "UNSPECIFIED",
      compensation_amount: null,
      compensation_currency: null,
      compensation_period: null,
      commitment_type: null,
      hours_per_week: null,
      duration_months: null,
      eligibility_requirements: null,
      accepts_applications: false,
      is_structured_opening: false,
    },
    application_count: base?.application_count ?? 0,
    published_at: base?.published_at ?? null,
    closed_at: null,
    archived_at: null,
    status_note: null,
    created_at: base?.created_at ?? now,
    updated_at: now,
    is_accepting_applications: false,
    days_until_deadline: null,
    allowed_transitions: [],
    is_owner: true,
    viewer_application_id: null,
    viewer_application_status: null,
  };
}

/**
 * P9 — the posting editor (plan §14): a full page with sections (basics, description, skills,
 * dates and terms, contact) beside a live preview of the PostingCard researchers will see.
 *
 * Every rule the backend applies is checked first and explained at the field; nothing is sent
 * until the form passes, and the first field to fix takes focus. Saving sends one request (the
 * button waits, a second click does nothing). If the server refuses or the network fails,
 * everything entered stays in the form with the reason above it. A new posting is saved as a
 * draft; editing sends only the fields that changed, so nothing else is overwritten. Either way
 * the posting's own page opens afterwards.
 */
export function PostingEditor({ posting = null }: { posting?: ResearchPosting | null }) {
  const router = useRouter();
  const { user } = useSession();
  const creating = posting === null;
  const initial = useMemo(() => (posting ? fromPosting(posting) : null), [posting]);
  const [values, setValues] = useState<PostingFormValues>(() => initial ?? EMPTY_FORM);
  const [errors, setErrors] = useState<FormErrors>({});
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inFlight = useRef(false);
  const saveButton = useRef<HTMLButtonElement>(null);

  const set = <K extends FieldName>(field: K, value: PostingFormValues[K]) => {
    const next = { ...values, [field]: value };
    setValues(next);
    // Once a save was tried, errors follow the values, so a fixed field stops saying it is wrong.
    if (submitted) setErrors(validate(next, initial));
    setNotice(null);
  };
  const error = (field: FieldName) => (submitted ? errors[field] : undefined);
  const structured = isStructured(values.posting_type);
  const listed = (Object.keys(errors) as FieldName[]).filter((field) => structured || !["amount", "currency", "hours", "duration"].includes(field));

  const focusField = (field: FieldName) => document.getElementById(fieldId(field))?.focus();

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (inFlight.current) return;
    setSubmitted(true);
    setFailure(null);
    setNotice(null);
    const found = validate(values, initial);
    setErrors(found);
    const first = FIELD_ORDER.find((field) => found[field]);
    if (first) {
      window.setTimeout(() => focusField(first), 0);
      return;
    }
    const changes = posting && initial ? updatePayload(values, initial) : null;
    if (changes && Object.keys(changes).length === 0) {
      setNotice("Nothing has changed, so there is nothing to save.");
      return;
    }
    inFlight.current = true;
    setSaving(true);
    try {
      const saved = posting && changes ? await updatePosting(posting.id, changes) : await createPosting(createPayload(values));
      // Leaving the page: the button stays busy so the form cannot be sent twice meanwhile.
      router.push(`/postings/${saved.id}`);
    } catch (err) {
      inFlight.current = false;
      setSaving(false);
      setFailure(saveError(err, creating));
      // The button was disabled while saving, which drops focus: give it back once it is enabled again.
      window.setTimeout(() => saveButton.current?.focus(), 0);
    }
  };

  const title = creating ? "New posting" : "Edit posting";
  const preview = previewOf(values, posting, user?.full_name ?? null);

  return (
    <>
      <Breadcrumb items={[{ label: "My postings", href: MY_POSTINGS_HREF }, ...(posting ? [{ label: posting.title, href: `/postings/${posting.id}` }] : [])]} current={title} />
      <PageHeader
        title={title}
        description={
          creating
            ? "A new posting is saved as a draft that only you can see. Publish it from its page when it is ready."
            : "Only the fields you change are saved; everything else stays as it is."
        }
      />

      <div className={styles.editor}>
        <form className={styles.form} noValidate onSubmit={onSubmit} aria-label={title}>
          {submitted && listed.length > 0 && (
            <Alert tone="danger" announce title={`Check ${listed.length === 1 ? "this field" : `these ${listed.length} fields`} before saving:`}>
              <ul className={styles.errorList}>
                {FIELD_ORDER.filter((field) => listed.includes(field)).map((field) => (
                  <li key={field}>
                    <a
                      href={`#${fieldId(field)}`}
                      onClick={(event) => {
                        event.preventDefault();
                        focusField(field);
                      }}
                    >
                      {FIELD_LABELS[field]}: {errors[field]}
                    </a>
                  </li>
                ))}
              </ul>
            </Alert>
          )}
          {failure && (
            <Alert tone="danger" announce>
              {failure}
              {creating && failure.startsWith("Create your researcher profile") && (
                <>
                  {" "}
                  <Link href="/researcher">Go to your profile</Link>
                </>
              )}
            </Alert>
          )}

          <section className={styles.formSection} aria-labelledby="editor-basics">
            <h2 id="editor-basics" className={styles.formSectionTitle}>
              Basics
            </h2>
            <TextInput
              id={fieldId("title")}
              label="Title"
              required
              hint={`${LIMITS.titleMin} to ${LIMITS.titleMax} characters.`}
              maxLength={LIMITS.titleMax}
              value={values.title}
              error={error("title")}
              onChange={(event) => set("title", event.target.value)}
            />
            <div className={styles.formGrid}>
              <Select id={fieldId("posting_type")} label="Category" value={values.posting_type} onChange={(event) => set("posting_type", event.target.value as PostingType)}>
                {POSTING_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {POSTING_TYPE_LABELS[type]}
                  </option>
                ))}
              </Select>
              <Select id={fieldId("work_mode")} label="Work mode" value={values.work_mode} onChange={(event) => set("work_mode", event.target.value as PostingWorkMode)}>
                {WORK_MODES.map((mode) => (
                  <option key={mode} value={mode}>
                    {WORK_MODE_LABELS[mode]}
                  </option>
                ))}
              </Select>
              <TextInput
                id={fieldId("positions")}
                label="Positions available"
                type="number"
                inputMode="numeric"
                min={1}
                max={LIMITS.positionsMax}
                required
                value={values.positions}
                error={error("positions")}
                onChange={(event) => set("positions", event.target.value)}
              />
              <TextInput id={fieldId("location")} label="Location" hint="City, as researchers should read it." value={values.location} error={error("location")} onChange={(event) => set("location", event.target.value)} />
              <TextInput
                id={fieldId("country")}
                label="Country"
                hint="Two-letter code, such as US."
                maxLength={2}
                autoComplete="off"
                value={values.country}
                error={error("country")}
                onChange={(event) => set("country", event.target.value)}
              />
              <TextInput
                id={fieldId("institution")}
                label="Institution"
                hint={creating ? "Leave blank to use your profile’s institution." : undefined}
                value={values.institution}
                error={error("institution")}
                onChange={(event) => set("institution", event.target.value)}
              />
              <TextInput
                id={fieldId("department")}
                label="Department"
                hint={creating ? "Leave blank to use your profile’s department." : undefined}
                value={values.department}
                error={error("department")}
                onChange={(event) => set("department", event.target.value)}
              />
            </div>
            <TextInput
              id={fieldId("summary")}
              label="Summary"
              hint={`One line shown in lists, up to ${LIMITS.summaryMax} characters.`}
              maxLength={LIMITS.summaryMax}
              value={values.summary}
              error={error("summary")}
              onChange={(event) => set("summary", event.target.value)}
            />
          </section>

          <section className={styles.formSection} aria-labelledby="editor-description">
            <h2 id="editor-description" className={styles.formSectionTitle}>
              Description
            </h2>
            <TextArea
              id={fieldId("description")}
              label="Description"
              required
              rows={8}
              hint={`The research, what the appointee will do and how to apply; at least ${LIMITS.descriptionMin} characters.`}
              value={values.description}
              error={error("description")}
              onChange={(event) => set("description", event.target.value)}
            />
            <TextArea
              id={fieldId("preferred_qualifications")}
              label="Preferred qualifications"
              rows={3}
              value={values.preferred_qualifications}
              error={error("preferred_qualifications")}
              onChange={(event) => set("preferred_qualifications", event.target.value)}
            />
          </section>

          <section className={styles.formSection} aria-labelledby="editor-skills">
            <h2 id="editor-skills" className={styles.formSectionTitle}>
              Skills
            </h2>
            <TextInput
              id={fieldId("skills")}
              label="Required skills"
              hint={`Separate skills with commas; up to ${LIMITS.skillsMax}. Students see how many of them they have recorded.`}
              value={values.skills}
              error={error("skills")}
              onChange={(event) => set("skills", event.target.value)}
            />
          </section>

          <section className={styles.formSection} aria-labelledby="editor-terms">
            <h2 id="editor-terms" className={styles.formSectionTitle}>
              Dates and terms
            </h2>
            <div className={styles.formGrid}>
              <TextInput
                id={fieldId("deadline")}
                label="Application deadline"
                type="date"
                hint="Optional. Applications close at 00:00 UTC on this day."
                value={values.deadline}
                error={error("deadline")}
                onChange={(event) => set("deadline", event.target.value)}
              />
              <TextInput id={fieldId("start")} label="Expected start" type="date" value={values.start} error={error("start")} onChange={(event) => set("start", event.target.value)} />
              <TextInput id={fieldId("end")} label="Expected end" type="date" value={values.end} error={error("end")} onChange={(event) => set("end", event.target.value)} />
            </div>
            {structured ? (
              <>
                <p className={styles.facts}>This category is a funded appointment, so applicants look for its terms. “Unpaid” is better stated than left blank.</p>
                <div className={styles.formGrid}>
                  <Select id={fieldId("compensation_type")} label="Compensation" value={values.compensation_type} onChange={(event) => set("compensation_type", event.target.value as CompensationType)}>
                    {COMPENSATION_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {COMPENSATION_TYPE_LABELS[type]}
                      </option>
                    ))}
                  </Select>
                  <TextInput id={fieldId("amount")} label="Amount" type="number" inputMode="decimal" min={0} value={values.amount} error={error("amount")} onChange={(event) => set("amount", event.target.value)} />
                  <TextInput
                    id={fieldId("currency")}
                    label="Currency"
                    hint="Three-letter code, such as USD."
                    maxLength={3}
                    autoComplete="off"
                    value={values.currency}
                    error={error("currency")}
                    onChange={(event) => set("currency", event.target.value)}
                  />
                  <Select id={fieldId("period")} label="Per" value={values.period} onChange={(event) => set("period", event.target.value)}>
                    <option value="">Not specified</option>
                    {COMPENSATION_PERIODS.map((period) => (
                      <option key={period.value} value={period.value}>
                        {period.label}
                      </option>
                    ))}
                  </Select>
                  <Select id={fieldId("commitment")} label="Commitment" value={values.commitment} onChange={(event) => set("commitment", event.target.value)}>
                    <option value="">Not specified</option>
                    {COMMITMENT_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {COMMITMENT_TYPE_LABELS[type]}
                      </option>
                    ))}
                  </Select>
                  <TextInput
                    id={fieldId("hours")}
                    label="Hours per week"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={LIMITS.hoursMax}
                    value={values.hours}
                    error={error("hours")}
                    onChange={(event) => set("hours", event.target.value)}
                  />
                  <TextInput
                    id={fieldId("duration")}
                    label="Duration in months"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={LIMITS.durationMax}
                    value={values.duration}
                    error={error("duration")}
                    onChange={(event) => set("duration", event.target.value)}
                  />
                </div>
                <TextArea
                  id={fieldId("eligibility")}
                  label="Eligibility"
                  hint="Enrolment, visa or degree requirements."
                  rows={3}
                  value={values.eligibility}
                  onChange={(event) => set("eligibility", event.target.value)}
                />
                <Checkbox
                  id={fieldId("accepts")}
                  label="Take applications on this platform"
                  hint="Researchers apply here, and you review them under Applicants."
                  checked={values.accepts}
                  onChange={(event) => set("accepts", event.target.checked)}
                />
              </>
            ) : (
              <p className={styles.facts}>
                {POSTING_TYPE_LABELS[values.posting_type]} postings are supervisor-led: researchers contact you directly, so there are no appointment terms and no applications on the
                platform.
              </p>
            )}
          </section>

          <section className={styles.formSection} aria-labelledby="editor-contact">
            <h2 id="editor-contact" className={styles.formSectionTitle}>
              Contact
            </h2>
            <div className={styles.formGrid}>
              <TextInput
                id={fieldId("contact_email")}
                label="Contact email"
                type="email"
                autoComplete="email"
                value={values.contact_email}
                error={error("contact_email")}
                onChange={(event) => set("contact_email", event.target.value)}
              />
              <TextInput
                id={fieldId("external_url")}
                label="Official page"
                type="url"
                hint="A web address, if the posting has one elsewhere."
                value={values.external_url}
                error={error("external_url")}
                onChange={(event) => set("external_url", event.target.value)}
              />
            </div>
          </section>

          {notice && <Alert tone="info">{notice}</Alert>}
          <div className={styles.formActions}>
            <Button ref={saveButton} type="submit" variant="primary" loading={saving} disabled={saving}>
              {creating ? "Save draft" : "Save changes"}
            </Button>
            <ButtonLink href={posting ? `/postings/${posting.id}` : MY_POSTINGS_HREF} variant="secondary">
              Cancel
            </ButtonLink>
          </div>
        </form>

        <aside className={styles.preview} aria-labelledby="editor-preview">
          <h2 id="editor-preview" className={styles.formSectionTitle}>
            Preview
          </h2>
          <p className={styles.facts}>How researchers will see it in the list of research postings.</p>
          <PreviewCard posting={preview} linkTitle={false} />
        </aside>
      </div>
    </>
  );
}
