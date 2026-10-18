"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Plus } from "lucide-react";
import { useApiResource } from "../../../hooks/useApiResource";
import { createSubmission, fetchWorkspaceSubmissions } from "../../../services/api";
import type { ResearchSubmission, SubmissionType } from "../../../types/submission";
import type { WorkspaceItem } from "../../../types/workspace";
import { submissionStatusMeta } from "../../../utils/status";
import { StatusBadge } from "../../ui/Badge/Badge";
import { Button } from "../../ui/Button/Button";
import { Select, TextInput } from "../../ui/Field/Field";
import { Alert, EmptyState, ErrorState, SkeletonList } from "../../ui/State/State";
import { actionError, shortDate, type Abilities } from "../workflow";
import { SubmissionView } from "./SubmissionView";
import { SUBMISSION_TYPES, submissionTypeLabel } from "./words";
import styles from "./Submission.module.css";

interface SubmissionPanelProps {
  item: WorkspaceItem;
  can: Abilities;
  /** The item changed on the server (a submission marked submitted moves it to Applied). */
  onWorkspaceChanged: () => void;
  onChanged: () => void;
}

/**
 * The Submission tab (plan §13: the submission workflow is a tab of the item, not a separate
 * page). One item can have several submission attempts; the newest is shown, the others can be
 * chosen. With none yet, editors draft one here. Replaces /workspace/[id]/submission.
 */
export function SubmissionPanel({ item, can, onWorkspaceChanged, onChanged }: SubmissionPanelProps) {
  const resource = useApiResource(`workspace:${item.id}:submissions`, (signal) => fetchWorkspaceSubmissions(item.id, undefined, signal));
  const [submissions, setSubmissions] = useState<ResearchSubmission[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!resource.data) return;
    setSubmissions(resource.data.items);
    setSelected((current) => (current && resource.data?.items.some((entry) => entry.id === current) ? current : (resource.data?.items[0]?.id ?? null)));
  }, [resource.data]);

  if (submissions === null) {
    if (resource.status === "error") {
      return <ErrorState title="The submission could not be loaded" kind={resource.error?.kind === "network" ? "offline" : "failed"} onRetry={resource.retry} />;
    }
    return <SkeletonList rows={3} lines={2} label="Loading the submission" />;
  }

  const active = submissions.find((entry) => entry.id === selected) ?? null;
  const replace = (updated: ResearchSubmission) => setSubmissions((current) => current && current.map((entry) => (entry.id === updated.id ? updated : entry)));

  const created = (submission: ResearchSubmission) => {
    setSubmissions((current) => [submission, ...(current ?? [])]);
    setSelected(submission.id);
    setCreating(false);
    setMessage(`Drafted ${submission.title}.`);
    onChanged();
  };

  const deleted = (submission: ResearchSubmission) => {
    const remaining = submissions.filter((entry) => entry.id !== submission.id);
    setSubmissions(remaining);
    setSelected(remaining[0]?.id ?? null);
    setMessage(`Deleted ${submission.title}.`);
    onChanged();
  };

  if (submissions.length === 0 || creating) {
    return (
      <div className={styles.stack}>
        <p role="status" className="rc-visually-hidden">
          {message}
        </p>
        {can.edit ? (
          <CreateSubmission item={item} onCreated={created} onCancel={submissions.length > 0 ? () => setCreating(false) : undefined} />
        ) : (
          <EmptyState title="No submission yet." description="The owner or an editor drafts the submission for this call." />
        )}
      </div>
    );
  }

  return (
    <div className={styles.stack}>
      <p role="status" className="rc-visually-hidden">
        {message}
      </p>
      {submissions.length > 1 && (
        <section className={styles.section} aria-labelledby="submission-attempts-heading">
          <h2 id="submission-attempts-heading" className={styles.sectionTitle}>
            Submissions for this call
          </h2>
          <ul className={styles.attempts}>
            {submissions.map((entry) => (
              <li key={entry.id}>
                <button type="button" className={styles.attempt} aria-pressed={entry.id === selected} onClick={() => setSelected(entry.id)}>
                  <span className={styles.attemptTitle}>{entry.title}</span>
                  <span className={styles.meta}>
                    <StatusBadge meta={submissionStatusMeta(entry.status)} />
                    <span>{submissionTypeLabel(entry.submission_type)}</span>
                    <span>Updated {shortDate(entry.updated_at)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {active && (
        <SubmissionView
          key={active.id}
          submission={active}
          can={can}
          onSaved={replace}
          onDeleted={deleted}
          onWorkspaceChanged={onWorkspaceChanged}
          onChanged={onChanged}
          onStartAnother={can.edit ? () => setCreating(true) : undefined}
        />
      )}
    </div>
  );
}

const TITLE_MAX = 500;

/** Drafting a submission: a title (required) and its format. Pressing twice creates one. */
function CreateSubmission({ item, onCreated, onCancel }: { item: WorkspaceItem; onCreated: (submission: ResearchSubmission) => void; onCancel?: () => void }) {
  const [title, setTitle] = useState("");
  const [type, setType] = useState<SubmissionType>("FULL_PAPER");
  const [titleError, setTitleError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const submitting = useRef(false);
  const titleRef = useRef<HTMLInputElement>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting.current) return;
    const value = title.trim();
    if (!value) {
      setTitleError("Give the submission a title: the manuscript's or the proposal's.");
      titleRef.current?.focus();
      return;
    }
    submitting.current = true;
    setSaving(true);
    setTitleError(null);
    setError(null);
    try {
      onCreated(await createSubmission({ workspace_item_id: item.id, title: value, submission_type: type }));
    } catch (err) {
      // What was typed stays; pressing "Create draft" again retries.
      setError(actionError(err, "The draft could not be created."));
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  };

  return (
    <section className={styles.section} aria-labelledby="submission-create-heading">
      <h2 id="submission-create-heading" className={styles.sectionTitle}>
        Draft a submission
      </h2>
      <p className={styles.text}>{"Start with the manuscript's title and format; add its details and documents next."}</p>
      <form className={styles.form} onSubmit={submit} noValidate>
        {error && (
          <Alert tone="danger" announce>
            {error}
          </Alert>
        )}
        <TextInput
          ref={titleRef}
          label="Title"
          required
          maxLength={TITLE_MAX}
          value={title}
          error={titleError}
          hint={item.opportunity?.title ? `For ${item.opportunity.title}` : undefined}
          onChange={(event) => {
            setTitle(event.target.value);
            if (titleError && event.target.value.trim()) setTitleError(null);
          }}
        />
        <Select label="Format" value={type} onChange={(event) => setType(event.target.value as SubmissionType)}>
          {SUBMISSION_TYPES.map((entry) => (
            <option key={entry.value} value={entry.value}>
              {entry.label}
            </option>
          ))}
        </Select>
        <div className={styles.actions}>
          <Button type="submit" loading={saving} leadingIcon={<Plus size={16} aria-hidden="true" />}>
            Create draft
          </Button>
          {onCancel && (
            <Button variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
          )}
        </div>
      </form>
    </section>
  );
}
