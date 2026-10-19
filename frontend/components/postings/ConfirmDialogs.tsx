"use client";

import { useRef, useState, type ReactNode } from "react";
import type { PostingApplication, ResearchPosting } from "../../types/posting";
import { Button } from "../ui/Button/Button";
import { Dialog } from "../ui/Dialog/Dialog";
import { TextArea } from "../ui/Field/Field";
import { Alert } from "../ui/State/State";
import styles from "./Faculty.module.css";

interface ConfirmProps {
  title: ReactNode;
  children: ReactNode;
  confirmLabel: string;
  /** Sends the change; true when the server agreed (the dialog then closes). */
  onConfirm: () => Promise<boolean>;
  onClose: () => void;
  /** Shown in the dialog when the server refused or failed. */
  failure: string | null;
}

/**
 * A consequential change, asked before it is sent (DESIGN_SYSTEM.md §8.3 Modal): the title names
 * the change and its object, the body its consequences. Cancel, Close, Escape and the backdrop
 * send nothing; Confirm sends once (a second click while it is being sent does nothing) and the
 * dialog stays open with the reason if the server does not agree. Focus starts on the title and
 * returns to the button that opened it.
 */
function ConfirmDialog({ title, children, confirmLabel, onConfirm, onClose, failure }: ConfirmProps) {
  const [sending, setSending] = useState(false);
  const inFlight = useRef(false);
  return (
    <Dialog
      open
      size="sm"
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={sending}
            disabled={sending}
            onClick={async () => {
              if (inFlight.current) return;
              inFlight.current = true;
              setSending(true);
              const agreed = await onConfirm();
              inFlight.current = false;
              setSending(false);
              if (agreed) onClose();
            }}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className={styles.dialogBody}>
        {children}
        {failure && (
          <Alert tone="danger" announce>
            {failure}
          </Alert>
        )}
      </div>
    </Dialog>
  );
}

/** "Not selected": final for the applicant, who is told; an optional message goes with it. */
export function NotSelectedDialog({
  application,
  onConfirm,
  onClose,
  failure,
}: {
  application: PostingApplication;
  onConfirm: (decisionReason: string) => Promise<boolean>;
  onClose: () => void;
  failure: string | null;
}) {
  const [message, setMessage] = useState("");
  const name = application.applicant.full_name ?? "this applicant";
  const posting = application.posting_title ?? "this posting";
  return (
    <ConfirmDialog
      title={<>Mark {name} as not selected for “{posting}”?</>}
      confirmLabel="Mark not selected"
      onConfirm={() => onConfirm(message)}
      onClose={onClose}
      failure={failure}
    >
      <p>
        {application.status === "OFFERED" ? "The offer you made is withdrawn. " : ""}
        The application ends here and cannot be reopened: you will not be able to shortlist {name} or make an offer for this posting afterwards. {name} is notified that
        the application was not successful.
      </p>
      <TextArea
        label="Message to the applicant (optional)"
        hint="Shown to them with the decision. Your private notes are never shared."
        maxLength={2000}
        rows={3}
        value={message}
        onChange={(event) => setMessage(event.target.value)}
      />
    </ConfirmDialog>
  );
}

/** "Cancel posting": researchers stop seeing it; it can never be reopened, only archived. */
export function CancelPostingDialog({ posting, onConfirm, onClose, failure }: { posting: ResearchPosting; onConfirm: () => Promise<boolean>; onClose: () => void; failure: string | null }) {
  return (
    <ConfirmDialog title={<>Cancel “{posting.title}”?</>} confirmLabel="Cancel posting" onConfirm={onConfirm} onClose={onClose} failure={failure}>
      <p>
        {posting.status === "DRAFT"
          ? "The draft will never be published. "
          : "Researchers no longer see it and can no longer apply. "}
        A cancelled posting cannot be published or reopened again; afterwards it can only be archived.
        {posting.application_count > 0 ? " The applications it received are kept, and you can still decide on them." : ""}
      </p>
    </ConfirmDialog>
  );
}

/** Deleting a draft is permanent (the backend allows it only for drafts). */
export function DeleteDraftDialog({ posting, onConfirm, onClose, failure }: { posting: ResearchPosting; onConfirm: () => Promise<boolean>; onClose: () => void; failure: string | null }) {
  return (
    <ConfirmDialog title={<>Delete the draft “{posting.title}”?</>} confirmLabel="Delete draft" onConfirm={onConfirm} onClose={onClose} failure={failure}>
      <p>The draft is removed permanently. This cannot be undone.</p>
    </ConfirmDialog>
  );
}
