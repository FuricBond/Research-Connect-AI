"use client";

import { useState } from "react";
import type { PostingApplication, ResearchPosting } from "../../types/posting";
import { ConfirmDialog } from "../ui/Dialog/ConfirmDialog";
import { TextArea } from "../ui/Field/Field";

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
