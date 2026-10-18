"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Check, ExternalLink, Plus, Trash2 } from "lucide-react";
import { useApiResource } from "../../../hooks/useApiResource";
import { deleteSubmission, fetchSubmissionDocuments, fetchSubmissionReadiness, transitionSubmissionStatus, updateSubmission } from "../../../services/api";
import type { ResearchSubmission, ResearchSubmissionUpdate, SubmissionStatus, SubmissionType } from "../../../types/submission";
import { readinessMeta, submissionStatusMeta } from "../../../utils/status";
import { cx } from "../../../utils/cx";
import { StatusBadge } from "../../ui/Badge/Badge";
import { Button } from "../../ui/Button/Button";
import { Dialog } from "../../ui/Dialog/Dialog";
import { Select, TextArea, TextInput } from "../../ui/Field/Field";
import { Alert, ErrorState, Skeleton, SkeletonList } from "../../ui/State/State";
import { actionError, shortDate, type Abilities } from "../workflow";
import { useKept } from "../item/useWorkspaceItem";
import { SubmissionDocuments } from "./SubmissionDocuments";
import { SubmissionHistory } from "./SubmissionHistory";
import { LIFECYCLE, SUBMISSION_TYPES, isForward, stepState, transitionLabel } from "./words";
import styles from "./Submission.module.css";

interface SubmissionViewProps {
  submission: ResearchSubmission;
  can: Abilities;
  onSaved: (submission: ResearchSubmission) => void;
  onDeleted: (submission: ResearchSubmission) => void;
  onWorkspaceChanged: () => void;
  onChanged: () => void;
  onStartAnother?: () => void;
}

type Draft = Required<{ [K in keyof ResearchSubmissionUpdate]: string }>;

const toDraft = (submission: ResearchSubmission): Draft => ({
  title: submission.title,
  abstract: submission.abstract ?? "",
  submission_type: submission.submission_type,
  venue: submission.venue ?? "",
  external_submission_id: submission.external_submission_id ?? "",
  submission_url: submission.submission_url ?? "",
  notes: submission.notes ?? "",
});

const isWebAddress = (value: string) => {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
};

/**
 * One submission: where it is in its lifecycle, whether it is ready (the server's readiness
 * check), the moves the server allows from here, its details, its documents and its history.
 * Requests: the readiness check and the documents; the history only when it is opened.
 */
export function SubmissionView({ submission, can, onSaved, onDeleted, onWorkspaceChanged, onChanged, onStartAnother }: SubmissionViewProps) {
  const readiness = useApiResource(`submission:${submission.id}:readiness`, (signal) => fetchSubmissionReadiness(submission.id, undefined, signal));
  const documents = useApiResource(`submission:${submission.id}:documents`, (signal) => fetchSubmissionDocuments(submission.id, {}, undefined, signal));
  const check = useKept(readiness);
  const documentList = useKept(documents);
  const status = submission.status;
  const meta = submissionStatusMeta(status);

  const [moving, setMoving] = useState<SubmissionStatus | null>(null);
  const [moveNote, setMoveNote] = useState("");
  const [moveError, setMoveError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [historyVersion, setHistoryVersion] = useState(0);

  const [deleting, setDeleting] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const changed = () => {
    setHistoryVersion((n) => n + 1);
    onChanged();
  };

  const move = async (target: SubmissionStatus) => {
    if (moving || !submission.allowed_transitions.includes(target)) return;
    setMoving(target);
    setMoveError(null);
    try {
      const updated = await transitionSubmissionStatus(submission.id, { target_status: target, notes: moveNote.trim() || undefined });
      onSaved(updated);
      setMoveNote("");
      setMessage(`${updated.title}: ${submissionStatusMeta(updated.status).label}.`);
      readiness.retry();
      changed();
      // Marking it submitted moves the call to Applied on the server.
      if (updated.workspace_status !== submission.workspace_status || target === "SUBMITTED") onWorkspaceChanged();
    } catch (err) {
      setMoveError(actionError(err, `It could not be moved to ${submissionStatusMeta(target).label.toLowerCase()}.`));
    } finally {
      setMoving(null);
    }
  };

  const remove = async () => {
    if (deleteBusy) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await deleteSubmission(submission.id);
      setDeleting(false);
      onDeleted(submission);
    } catch (err) {
      setDeleteError(actionError(err, "The submission could not be deleted."));
    } finally {
      setDeleteBusy(false);
    }
  };

  const blocked = check ? !check.can_mark_submission_ready : false;
  const moves = submission.allowed_transitions;
  const decided = status === "ACCEPTED" || status === "REJECTED";
  const submitted = shortDate(submission.submitted_at);
  const decision = shortDate(submission.decision_at);
  const canDelete = can.manage && (status === "DRAFT" || status === "WITHDRAWN");
  // The view appears once its two first answers are in (or have failed), so the readiness check
  // does not push the status actions and the details down when it arrives (P7 CLS).
  const answered = (resource: { status: string }, kept: unknown) => kept !== undefined || resource.status === "error";
  if (!answered(readiness, check) || !answered(documents, documentList)) {
    return <SkeletonList rows={4} lines={2} label="Loading the submission" />;
  }

  return (
    <div className={styles.stack}>
      <section className={styles.section} aria-labelledby="submission-status-heading">
        <div className={styles.sectionHead}>
          <div className={styles.headText}>
            <h2 id="submission-status-heading" className={styles.sectionTitle}>
              {submission.title}
            </h2>
            <p className={styles.meta}>
              <StatusBadge meta={meta} />
              {submitted && <span>Submitted {submitted}</span>}
              {decision && <span>Decision recorded {decision}</span>}
            </p>
          </div>
          {onStartAnother && (
            <Button variant="secondary" size="sm" leadingIcon={<Plus size={16} aria-hidden="true" />} onClick={onStartAnother}>
              Start another submission
            </Button>
          )}
        </div>

        <ol className={styles.steps} aria-label="Submission progress">
          {LIFECYCLE.map((step, index) => {
            const state = stepState(step.status, status);
            const label = step.status === "ACCEPTED" && decided ? submissionStatusMeta(status).label : step.label;
            return (
              <li key={step.status} className={cx(styles.step, styles[state])} aria-current={state === "current" ? "step" : undefined}>
                <span className={styles.stepMark} aria-hidden="true">
                  {state === "done" ? <Check size={14} /> : index + 1}
                </span>
                <span className={styles.stepLabel}>{label}</span>
                <span className="rc-visually-hidden">{state === "done" ? ", done" : state === "current" ? ", current step" : ""}</span>
              </li>
            );
          })}
        </ol>
        {status === "WITHDRAWN" && <p className={styles.text}>This submission was withdrawn. Reopen it as a draft to continue.</p>}

        <div className={styles.readiness}>
          <h3 className={styles.subTitle}>Readiness</h3>
          {check ? (
            <>
              {/* The facts in words; the server's own summary repeats them with enum values. */}
              <p className={styles.meta}>
                <StatusBadge meta={readinessMeta(check.overall_readiness)} />
                <span>
                  {check.completed_document_count} of {check.required_document_count} required documents ready
                </span>
                <span>Details {Math.round(Math.min(1, check.metadata_completeness) * 100)}% filled in</span>
              </p>
              {check.blocking_issues.length > 0 && (
                <div>
                  <h4 className={styles.listTitle}>To fix before it can be marked ready</h4>
                  <ul className={styles.issues}>
                    {check.blocking_issues.map((issue, index) => (
                      <li key={`${issue.code}-${index}`}>{issue.message}</li>
                    ))}
                  </ul>
                </div>
              )}
              {check.warnings.length > 0 && (
                <div>
                  <h4 className={styles.listTitle}>Worth checking</h4>
                  <ul className={styles.issues}>
                    {check.warnings.map((issue, index) => (
                      <li key={`${issue.code}-${index}`}>{issue.message}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : readiness.status === "error" ? (
            <ErrorState bare headingLevel={4} title="The readiness check could not be loaded" onRetry={readiness.retry} />
          ) : (
            <Skeleton width="min(24rem, 100%)" height="1.25rem" />
          )}
        </div>

        {can.edit && moves.length > 0 && (
          <div className={styles.moves}>
            <h3 className={styles.subTitle}>Change status</h3>
            {moveError && (
              <Alert tone="danger" announce>
                {moveError}
              </Alert>
            )}
            <TextInput label="Note for this change" hint="Optional. If you write one, it replaces the submission's notes." value={moveNote} onChange={(event) => setMoveNote(event.target.value)} maxLength={500} />
            <div className={styles.actions}>
              {moves.map((target) => {
                const gated = target === "READY" && blocked;
                return (
                  <Button
                    key={target}
                    variant={isForward(target, status) ? "primary" : "secondary"}
                    loading={moving === target}
                    disabled={gated || (moving !== null && moving !== target)}
                    aria-describedby={gated ? "submission-ready-blocked" : undefined}
                    onClick={() => void move(target)}
                  >
                    {transitionLabel(target, status)}
                  </Button>
                );
              })}
            </div>
            {blocked && moves.includes("READY") && (
              <p id="submission-ready-blocked" className={styles.text}>
                It can be marked ready once the items under Readiness are fixed.
              </p>
            )}
          </div>
        )}
        <p role="status" className="rc-visually-hidden">
          {message}
        </p>
      </section>

      <SubmissionDetails submission={submission} can={can} onSaved={(updated) => {
        onSaved(updated);
        readiness.retry();
        changed();
      }} />

      <SubmissionDocuments
        submissionId={submission.id}
        documents={documents}
        can={can}
        onChanged={() => {
          documents.retry();
          readiness.retry();
          changed();
        }}
      />

      <SubmissionHistory submissionId={submission.id} version={historyVersion} />

      {canDelete && (
        <section className={styles.section} aria-labelledby="submission-delete-heading">
          <h2 id="submission-delete-heading" className={styles.subTitle}>
            Delete this submission
          </h2>
          <p className={styles.text}>Only a draft or a withdrawn submission can be deleted, with its documents and history.</p>
          <div>
            <Button variant="danger" leadingIcon={<Trash2 size={16} aria-hidden="true" />} onClick={() => {
              setDeleteError(null);
              setDeleting(true);
            }}>
              Delete submission
            </Button>
          </div>
        </section>
      )}

      <Dialog
        open={deleting}
        onClose={() => setDeleting(false)}
        size="sm"
        title={`Delete the submission "${submission.title}"?`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleting(false)}>
              Cancel
            </Button>
            <Button variant="danger" loading={deleteBusy} onClick={() => void remove()}>
              Delete submission
            </Button>
          </>
        }
      >
        <p>Its details, documents with their versions, and its history are deleted. This cannot be undone.</p>
        {deleteError && (
          <Alert tone="danger" announce>
            {deleteError}
          </Alert>
        )}
      </Dialog>
    </div>
  );
}

const LIMITS = { title: 500, venue: 255, external_submission_id: 255, submission_url: 1000 } as const;

/**
 * The submission's details. Saved together; the title is required and the portal must be a web
 * address. A failure keeps everything typed, so "Save details" can be pressed again.
 */
function SubmissionDetails({ submission, can, onSaved }: { submission: ResearchSubmission; can: Abilities; onSaved: (submission: ResearchSubmission) => void }) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(submission));
  const [errors, setErrors] = useState<Partial<Record<keyof Draft, string>>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const submitting = useRef(false);
  const titleRef = useRef<HTMLInputElement>(null);
  const urlRef = useRef<HTMLInputElement>(null);

  const saved = toDraft(submission);
  // A newer server copy (after a status change, say) updates the fields not being edited.
  const base = useRef(saved);
  useEffect(() => {
    const previous = base.current;
    const next = toDraft(submission);
    base.current = next;
    setDraft((current) => {
      const merged = { ...current };
      for (const key of Object.keys(next) as (keyof Draft)[]) if (current[key] === previous[key]) merged[key] = next[key];
      return merged;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submission.updated_at]);
  const dirty = (Object.keys(draft) as (keyof Draft)[]).some((key) => draft[key] !== saved[key]);
  const set = (key: keyof Draft, value: string) => {
    setDraft((current) => ({ ...current, [key]: value }));
    if (errors[key]) setErrors((current) => ({ ...current, [key]: undefined }));
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting.current) return;
    const next: Partial<Record<keyof Draft, string>> = {};
    if (!draft.title.trim()) next.title = "The title cannot be empty.";
    const url = draft.submission_url.trim();
    if (url && !isWebAddress(url)) next.submission_url = "Enter a web address starting with https:// or http://.";
    setErrors(next);
    if (next.title) {
      titleRef.current?.focus();
      return;
    }
    if (next.submission_url) {
      urlRef.current?.focus();
      return;
    }
    submitting.current = true;
    setSaving(true);
    setError(null);
    setMessage("");
    try {
      const updated = await updateSubmission(submission.id, {
        title: draft.title.trim(),
        abstract: draft.abstract,
        submission_type: draft.submission_type as SubmissionType,
        venue: draft.venue.trim(),
        external_submission_id: draft.external_submission_id.trim(),
        submission_url: url,
        notes: draft.notes,
      });
      onSaved(updated);
      setDraft(toDraft(updated));
      setMessage("Details saved.");
    } catch (err) {
      setError(actionError(err, "The details could not be saved."));
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  };

  if (!can.edit) {
    const facts: [string, string][] = [
      ["Format", SUBMISSION_TYPES.find((entry) => entry.value === submission.submission_type)?.label ?? submission.submission_type],
      ["Venue or track", submission.venue ?? ""],
      ["Submission ID", submission.external_submission_id ?? ""],
    ];
    return (
      <section className={styles.section} aria-labelledby="submission-details-heading">
        <h2 id="submission-details-heading" className={styles.sectionTitle}>
          Details
        </h2>
        <dl className={styles.facts}>
          {facts
            .filter(([, value]) => value)
            .map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
        </dl>
        {submission.submission_url && isWebAddress(submission.submission_url) && (
          <a href={submission.submission_url} target="_blank" rel="noopener noreferrer" className={styles.external}>
            Open the submission portal
            <ExternalLink size={14} aria-hidden="true" />
            <span className="rc-visually-hidden"> (opens in a new tab)</span>
          </a>
        )}
        {submission.abstract && <p className={styles.prose}>{submission.abstract}</p>}
      </section>
    );
  }

  const portal = draft.submission_url.trim();
  return (
    <section className={styles.section} aria-labelledby="submission-details-heading">
      <h2 id="submission-details-heading" className={styles.sectionTitle}>
        Details
      </h2>
      <form className={styles.form} onSubmit={save} noValidate>
        {error && (
          <Alert tone="danger" announce>
            {error}
          </Alert>
        )}
        <TextInput ref={titleRef} label="Title" required maxLength={LIMITS.title} value={draft.title} error={errors.title} onChange={(event) => set("title", event.target.value)} />
        <div className={styles.formRow}>
          <Select label="Format" value={draft.submission_type} onChange={(event) => set("submission_type", event.target.value)}>
            {SUBMISSION_TYPES.map((entry) => (
              <option key={entry.value} value={entry.value}>
                {entry.label}
              </option>
            ))}
          </Select>
          <TextInput label="Venue or track" maxLength={LIMITS.venue} value={draft.venue} onChange={(event) => set("venue", event.target.value)} hint="For example: Main track, Oral." />
        </div>
        <div className={styles.formRow}>
          <TextInput
            label="Submission ID"
            maxLength={LIMITS.external_submission_id}
            value={draft.external_submission_id}
            onChange={(event) => set("external_submission_id", event.target.value)}
            hint="The ID the submission system gave it."
          />
          <TextInput
            ref={urlRef}
            label="Submission portal"
            type="url"
            inputMode="url"
            maxLength={LIMITS.submission_url}
            value={draft.submission_url}
            error={errors.submission_url}
            onChange={(event) => set("submission_url", event.target.value)}
          />
        </div>
        {portal && isWebAddress(portal) && (
          <a href={portal} target="_blank" rel="noopener noreferrer" className={styles.external}>
            Open the submission portal
            <ExternalLink size={14} aria-hidden="true" />
            <span className="rc-visually-hidden"> (opens in a new tab)</span>
          </a>
        )}
        <TextArea label="Abstract" rows={5} value={draft.abstract} onChange={(event) => set("abstract", event.target.value)} />
        <TextArea label="Notes" rows={3} value={draft.notes} onChange={(event) => set("notes", event.target.value)} hint="Co-author tasks, rebuttal plans, reviewer feedback." />
        <div className={styles.actions}>
          <Button type="submit" loading={saving} disabled={!dirty && !saving}>
            Save details
          </Button>
          {dirty && !saving && (
            <Button
              variant="ghost"
              onClick={() => {
                setDraft(saved);
                setErrors({});
                setError(null);
              }}
            >
              Discard changes
            </Button>
          )}
        </div>
        <p role="status" className={styles.notice}>
          {message}
        </p>
      </form>
    </section>
  );
}
