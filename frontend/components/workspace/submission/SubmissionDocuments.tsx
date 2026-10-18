"use client";

import { useRef, useState, type FormEvent } from "react";
import { MoreHorizontal, Plus } from "lucide-react";
import { useApiResource, type ApiResource } from "../../../hooks/useApiResource";
import { createSubmissionDocument, deleteSubmissionDocument, fetchDocumentVersions, updateSubmissionDocument } from "../../../services/api";
import type { DocumentStatus, DocumentType, SubmissionDocument, SubmissionDocumentListResponse } from "../../../types/submission";
import { documentStatusMeta } from "../../../utils/status";
import { Badge, StatusBadge } from "../../ui/Badge/Badge";
import { Button } from "../../ui/Button/Button";
import { Dialog } from "../../ui/Dialog/Dialog";
import { Checkbox, Select, TextArea, TextInput } from "../../ui/Field/Field";
import { Menu } from "../../ui/Menu/Menu";
import { Alert, EmptyState, ErrorState, SkeletonList } from "../../ui/State/State";
import { actionError, dateTime, type Abilities } from "../workflow";
import { useKept } from "../item/useWorkspaceItem";
import { DOCUMENT_TYPES, NEW_DOCUMENT_STATUSES, VERSION_STATUSES, documentTypeLabel } from "./words";
import styles from "./Submission.module.css";

interface SubmissionDocumentsProps {
  submissionId: string;
  documents: ApiResource<SubmissionDocumentListResponse>;
  can: Abilities;
  onChanged: () => void;
}

type Open = { kind: "add" } | { kind: "version"; document: SubmissionDocument } | { kind: "history"; document: SubmissionDocument } | { kind: "delete"; document: SubmissionDocument };

/**
 * The documents a submission needs (manuscript, abstract, disclosures…), each with its status,
 * whether it is required, and its versions. Contributors add documents, mark them ready, record
 * versions and archive them; editors and the owner delete them (after a confirmation).
 */
export function SubmissionDocuments({ submissionId, documents, can, onChanged }: SubmissionDocumentsProps) {
  const shown = useKept(documents);
  const [open, setOpen] = useState<Open | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  const quick = async (document: SubmissionDocument, status: DocumentStatus, done: string, failed: string) => {
    if (busy) return;
    setBusy(document.id);
    setError(null);
    try {
      await updateSubmissionDocument(submissionId, document.id, { status });
      setMessage(done);
      onChanged();
    } catch (err) {
      setError(actionError(err, failed));
    } finally {
      setBusy(null);
    }
  };

  const list = shown?.items ?? [];

  return (
    <section className={styles.section} aria-labelledby="submission-documents-heading">
      <div className={styles.sectionHead}>
        <h2 id="submission-documents-heading" className={styles.sectionTitle}>
          Documents
        </h2>
        {can.contribute && (
          <Button variant="secondary" leadingIcon={<Plus size={16} aria-hidden="true" />} onClick={() => setOpen({ kind: "add" })}>
            Add document
          </Button>
        )}
      </div>
      <p role="status" className="rc-visually-hidden">
        {message}
      </p>
      {error && (
        <Alert tone="danger" announce>
          {error}
        </Alert>
      )}
      {shown === undefined ? (
        documents.status === "error" ? (
          <ErrorState title="The documents could not be loaded" kind={documents.error?.kind === "network" ? "offline" : "failed"} onRetry={documents.retry} />
        ) : (
          <SkeletonList rows={2} label="Loading documents" />
        )
      ) : list.length === 0 ? (
        <EmptyState title="No documents yet." description="Add the manuscript, abstract, author biography or disclosures, to track their versions and readiness." />
      ) : (
        <ul className={styles.list} aria-busy={documents.status === "loading" || undefined}>
          {list.map((document) => {
            const format = document.file_metadata?.mime_type as string | undefined;
            const checksum = document.file_metadata?.checksum_sha256 as string | undefined;
            const archived = document.status === "ARCHIVED";
            return (
              <li key={document.id} className={styles.row}>
                <div className={styles.rowMain}>
                  <h3 className={styles.rowTitle}>{document.title}</h3>
                  <p className={styles.meta}>
                    <StatusBadge meta={documentStatusMeta(document.status)} />
                    <Badge tone={document.is_required ? "neutral" : "muted"}>{document.is_required ? "Required" : "Optional"}</Badge>
                    <span>{documentTypeLabel(document.document_type)}</span>
                    <span>Version {document.current_version}</span>
                    {format && <span>{format}</span>}
                  </p>
                  {document.description && <p className={styles.text}>{document.description}</p>}
                  {(document.storage_reference || checksum) && (
                    <p className={styles.meta}>
                      {document.storage_reference && (
                        <span>
                          Stored at <span className={styles.code}>{document.storage_reference}</span>
                        </span>
                      )}
                      {checksum && (
                        <span>
                          SHA-256 <span className={styles.code}>{String(checksum).slice(0, 12)}…</span>
                        </span>
                      )}
                    </p>
                  )}
                </div>
                <div className={styles.rowActions}>
                  {can.contribute && !archived && document.status !== "READY" && (
                    <Button size="sm" variant="secondary" loading={busy === document.id} onClick={() => void quick(document, "READY", `${document.title} is ready.`, `${document.title} could not be marked ready.`)}>
                      Mark ready<span className="rc-visually-hidden">: {document.title}</span>
                    </Button>
                  )}
                  <Menu
                    align="end"
                    triggerLabel={`More actions for ${document.title}`}
                    triggerClassName={styles.moreTrigger}
                    trigger={<MoreHorizontal size={16} aria-hidden="true" />}
                    disabled={busy === document.id}
                    items={[
                      ...(can.contribute ? [{ id: "version", label: "Record a new version", onSelect: () => setOpen({ kind: "version", document }) }] : []),
                      { id: "history", label: `Version history (${document.versions_count})`, onSelect: () => setOpen({ kind: "history", document }) },
                      ...(can.contribute && !archived
                        ? [{ id: "archive", label: "Archive", onSelect: () => void quick(document, "ARCHIVED", `Archived ${document.title}.`, `${document.title} could not be archived.`) }]
                        : []),
                      ...(can.edit ? [{ id: "delete", label: "Delete", danger: true, onSelect: () => setOpen({ kind: "delete", document }) }] : []),
                    ]}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <AddDocument
        open={open?.kind === "add"}
        submissionId={submissionId}
        onClose={() => setOpen(null)}
        onAdded={(title) => {
          setOpen(null);
          setMessage(`Added ${title}.`);
          onChanged();
        }}
      />
      <RecordVersion
        document={open?.kind === "version" ? open.document : null}
        submissionId={submissionId}
        onClose={() => setOpen(null)}
        onRecorded={(document) => {
          setOpen(null);
          setMessage(`Recorded version ${document.current_version + 1} of ${document.title}.`);
          onChanged();
        }}
      />
      <VersionHistory document={open?.kind === "history" ? open.document : null} submissionId={submissionId} onClose={() => setOpen(null)} />
      <DeleteDocument
        document={open?.kind === "delete" ? open.document : null}
        submissionId={submissionId}
        onClose={() => setOpen(null)}
        onDeleted={(document) => {
          setOpen(null);
          setMessage(`Deleted ${document.title}.`);
          onChanged();
        }}
      />
    </section>
  );
}

/** One submit at a time: a second press while the first is in flight does nothing. */
function useOnce() {
  const running = useRef(false);
  const [busy, setBusy] = useState(false);
  const run = async (task: () => Promise<void>) => {
    if (running.current) return;
    running.current = true;
    setBusy(true);
    try {
      await task();
    } finally {
      running.current = false;
      setBusy(false);
    }
  };
  return [busy, run] as const;
}

function AddDocument({ open, submissionId, onClose, onAdded }: { open: boolean; submissionId: string; onClose: () => void; onAdded: (title: string) => void }) {
  const [type, setType] = useState<DocumentType>("FULL_PAPER");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<DocumentStatus>("DRAFT");
  const [required, setRequired] = useState(true);
  const [mime, setMime] = useState("application/pdf");
  const [reference, setReference] = useState("");
  const [titleError, setTitleError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, run] = useOnce();
  const titleRef = useRef<HTMLInputElement>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = title.trim();
    if (!value) {
      setTitleError("Give the document a name.");
      titleRef.current?.focus();
      return;
    }
    void run(async () => {
      setTitleError(null);
      setError(null);
      try {
        await createSubmissionDocument(submissionId, {
          document_type: type,
          title: value,
          description: description.trim() || undefined,
          is_required: required,
          status,
          storage_reference: reference.trim() || undefined,
          file_metadata: { mime_type: mime.trim() || "application/pdf" },
        });
        setTitle("");
        setDescription("");
        setReference("");
        onAdded(value);
      } catch (err) {
        setError(actionError(err, "The document could not be added."));
      }
    });
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add a document"
      initialFocusRef={titleRef}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="submission-add-document" loading={saving}>
            Add document
          </Button>
        </>
      }
    >
      <form id="submission-add-document" className={styles.form} onSubmit={submit} noValidate>
        {error && (
          <Alert tone="danger" announce>
            {error}
          </Alert>
        )}
        <TextInput
          ref={titleRef}
          label="Name"
          required
          maxLength={255}
          value={title}
          error={titleError}
          hint="For example: Camera-ready draft."
          onChange={(event) => {
            setTitle(event.target.value);
            if (titleError && event.target.value.trim()) setTitleError(null);
          }}
        />
        <Select label="Kind of document" value={type} onChange={(event) => setType(event.target.value as DocumentType)}>
          {DOCUMENT_TYPES.map((entry) => (
            <option key={entry.value} value={entry.value}>
              {entry.label}
            </option>
          ))}
        </Select>
        <TextInput label="Description" value={description} onChange={(event) => setDescription(event.target.value)} />
        <div className={styles.formRow}>
          <Select label="Status" value={status} onChange={(event) => setStatus(event.target.value as DocumentStatus)}>
            {NEW_DOCUMENT_STATUSES.map((value) => (
              <option key={value} value={value}>
                {documentStatusMeta(value).label}
              </option>
            ))}
          </Select>
          <TextInput label="File type" value={mime} onChange={(event) => setMime(event.target.value)} hint="For example: application/pdf." />
        </div>
        <TextInput label="Where it is stored" value={reference} onChange={(event) => setReference(event.target.value)} hint="A link or a path, such as a shared drive location." />
        <Checkbox label="Required for this submission" checked={required} onChange={(event) => setRequired(event.target.checked)} />
      </form>
    </Dialog>
  );
}

function RecordVersion({ document, submissionId, onClose, onRecorded }: { document: SubmissionDocument | null; submissionId: string; onClose: () => void; onRecorded: (document: SubmissionDocument) => void }) {
  const [status, setStatus] = useState<DocumentStatus>("READY");
  const [reference, setReference] = useState("");
  const [mime, setMime] = useState("");
  const [checksum, setChecksum] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, run] = useOnce();
  const [forId, setForId] = useState<string | null>(null);

  // Start from the document's current values each time the dialog opens for a document.
  if (document && document.id !== forId) {
    setForId(document.id);
    setStatus(document.status);
    setReference(document.storage_reference ?? "");
    setMime((document.file_metadata?.mime_type as string | undefined) ?? "application/pdf");
    setChecksum("");
    setNotes("");
    setError(null);
  }

  const close = () => {
    setForId(null);
    onClose();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!document) return;
    void run(async () => {
      setError(null);
      try {
        await updateSubmissionDocument(submissionId, document.id, {
          status,
          storage_reference: reference.trim() || undefined,
          file_metadata: { mime_type: mime.trim() || undefined, checksum_sha256: checksum.trim() || undefined, version_notes: notes.trim() || undefined },
          create_new_version: true,
        });
        setForId(null);
        onRecorded(document);
      } catch (err) {
        setError(actionError(err, "The new version could not be recorded."));
      }
    });
  };

  return (
    <Dialog
      open={document !== null}
      onClose={close}
      title={`New version of ${document?.title ?? "the document"}`}
      description={document ? `It is at version ${document.current_version}; this records version ${document.current_version + 1} and keeps the current one in its history.` : undefined}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            Cancel
          </Button>
          <Button type="submit" form="submission-record-version" loading={saving}>
            Record version
          </Button>
        </>
      }
    >
      <form id="submission-record-version" className={styles.form} onSubmit={submit} noValidate>
        {error && (
          <Alert tone="danger" announce>
            {error}
          </Alert>
        )}
        <Select label="Status" value={status} onChange={(event) => setStatus(event.target.value as DocumentStatus)}>
          {VERSION_STATUSES.map((value) => (
            <option key={value} value={value}>
              {documentStatusMeta(value).label}
            </option>
          ))}
        </Select>
        <TextInput label="Where it is stored" value={reference} onChange={(event) => setReference(event.target.value)} />
        <div className={styles.formRow}>
          <TextInput label="File type" value={mime} onChange={(event) => setMime(event.target.value)} />
          <TextInput label="SHA-256 checksum" value={checksum} onChange={(event) => setChecksum(event.target.value)} hint="Optional." />
        </div>
        <TextArea label="What changed" rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} hint="For example: addressed the reviewers' comments on Figure 3." />
      </form>
    </Dialog>
  );
}

function VersionHistory({ document, submissionId, onClose }: { document: SubmissionDocument | null; submissionId: string; onClose: () => void }) {
  const versions = useApiResource(document ? `submission:${submissionId}:document:${document.id}:versions` : null, (signal) => fetchDocumentVersions(submissionId, document?.id ?? "", undefined, signal));
  const list = versions.data ?? [];
  return (
    <Dialog
      open={document !== null}
      onClose={onClose}
      title={`Versions of ${document?.title ?? "the document"}`}
      footer={
        <Button variant="secondary" onClick={onClose}>
          Done
        </Button>
      }
    >
      {versions.status === "loading" || versions.status === "idle" ? (
        <SkeletonList rows={2} label="Loading versions" />
      ) : versions.status === "error" ? (
        <ErrorState bare headingLevel={3} title="The versions could not be loaded" onRetry={versions.retry} />
      ) : list.length === 0 ? (
        <p className={styles.text}>No earlier versions. It is at version {document?.current_version}.</p>
      ) : (
        <ol className={styles.versions}>
          {list.map((version) => {
            const size = version.file_metadata?.file_size_bytes as number | undefined;
            const format = version.file_metadata?.mime_type as string | undefined;
            const notes = version.file_metadata?.version_notes as string | undefined;
            return (
              <li key={version.id} className={styles.version}>
                <p className={styles.meta}>
                  <span className={styles.versionNumber}>Version {version.version_number}</span>
                  <StatusBadge meta={documentStatusMeta(version.status)} />
                  <span>{dateTime(version.created_at)}</span>
                  {size ? <span>{(size / 1024).toFixed(1)} KB</span> : null}
                  {format && <span>{format}</span>}
                </p>
                {version.storage_reference && (
                  <p className={styles.meta}>
                    Stored at <span className={styles.code}>{version.storage_reference}</span>
                  </p>
                )}
                {version.checksum && (
                  <p className={styles.meta}>
                    SHA-256 <span className={styles.code}>{version.checksum}</span>
                  </p>
                )}
                {notes && <p className={styles.text}>{notes}</p>}
              </li>
            );
          })}
        </ol>
      )}
    </Dialog>
  );
}

function DeleteDocument({ document, submissionId, onClose, onDeleted }: { document: SubmissionDocument | null; submissionId: string; onClose: () => void; onDeleted: (document: SubmissionDocument) => void }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, run] = useOnce();
  const remove = () => {
    if (!document) return;
    void run(async () => {
      setError(null);
      try {
        await deleteSubmissionDocument(submissionId, document.id);
        onDeleted(document);
      } catch (err) {
        setError(actionError(err, "The document could not be deleted."));
      }
    });
  };
  return (
    <Dialog
      open={document !== null}
      onClose={() => {
        setError(null);
        onClose();
      }}
      size="sm"
      title={`Delete ${document?.title ?? "the document"}?`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" loading={busy} onClick={remove}>
            Delete document
          </Button>
        </>
      }
    >
      <p>It is deleted with all its versions. To keep them, archive it instead. This cannot be undone.</p>
      {error && (
        <Alert tone="danger" announce>
          {error}
        </Alert>
      )}
    </Dialog>
  );
}
