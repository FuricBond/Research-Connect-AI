"use client";

/**
 * P9 — the author's controls on a posting's own page: where it stands, Edit, and the lifecycle
 * moves the server lists ("Cancel posting" and "Delete draft" ask first). They come with the page
 * (they sit above the posting, so arriving late they would push it down); the confirmations load
 * when asked for.
 */

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import type { PostingStatus, ResearchPosting } from "../../types/posting";
import { canEdit, MY_POSTINGS_HREF, postingActionsFor, postingVisibility } from "../../utils/postings";
import { postingStatusMeta } from "../../utils/status";
import { Button, ButtonLink } from "../ui/Button/Button";
import { Alert } from "../ui/State/State";
import { CancelPostingDialog, DeleteDraftDialog } from "./lazy";
import { usePostingChanges } from "./usePostingChanges";
import styles from "./Faculty.module.css";

/** The author's controls: where the posting stands, Edit, and the lifecycle moves the server lists. */
export function ManagePosting({ posting, onChanged }: { posting: ResearchPosting; onChanged: (posting: ResearchPosting) => void }) {
  const router = useRouter();
  const changes = usePostingChanges();
  const [confirming, setConfirming] = useState<"cancel" | "delete" | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const transition = async (target: PostingStatus) => {
    const answer = await changes.transition(posting, target);
    if (answer) onChanged(answer);
    // The button used was disabled while waiting (which drops focus) and may be gone with the new
    // status: if focus was lost, the section's heading takes it.
    window.setTimeout(() => {
      if (document.activeElement === document.body || document.activeElement === null) heading.current?.focus();
    }, 0);
    return answer;
  };
  const actions = postingActionsFor(posting);
  const pending = changes.pending.has(posting.id);
  const failure = changes.failure && changes.failure.posting.id === posting.id && confirming === null ? changes.failure : null;

  return (
    <section className={styles.manage} aria-labelledby="posting-manage">
      <h2 id="posting-manage" ref={heading} tabIndex={-1} className={styles.detailTitle}>
        Manage this posting
      </h2>
      <p className={styles.facts}>{postingVisibility(posting.status)}</p>
      <div className={styles.decisions} role="group" aria-label="Manage this posting">
        {canEdit(posting) && (
          <ButtonLink href={`/postings/${posting.id}/edit`} size="sm" variant="secondary">
            Edit
          </ButtonLink>
        )}
        {actions.map((action) => (
          <Button
            key={action.target}
            size="sm"
            variant={action.variant}
            disabled={pending}
            onClick={() => {
              if (action.confirm) {
                changes.dismissFailure();
                setConfirming("cancel");
                return;
              }
              void transition(action.target);
            }}
          >
            {action.label}
          </Button>
        ))}
        {posting.status === "DRAFT" && (
          <Button
            size="sm"
            variant="danger-ghost"
            disabled={pending}
            onClick={() => {
              changes.dismissFailure();
              setConfirming("delete");
            }}
          >
            Delete draft
          </Button>
        )}
        {pending && (
          <span className={styles.saving} role="status">
            Saving…
          </span>
        )}
      </div>
      <p role="status" className="rc-visually-hidden">
        {changes.announcement}
      </p>
      {failure && (
        <Alert tone="danger" announce>
          {failure.message} It is still {postingStatusMeta(posting.status).label.toLowerCase()}.
        </Alert>
      )}
      {confirming === "cancel" && (
        <CancelPostingDialog
          posting={posting}
          failure={changes.failure?.posting.id === posting.id ? changes.failure.message : null}
          onClose={() => setConfirming(null)}
          onConfirm={async () => {
            const answer = await transition("CANCELLED");
            if (answer) window.setTimeout(() => heading.current?.focus(), 0);
            return answer !== null;
          }}
        />
      )}
      {confirming === "delete" && (
        <DeleteDraftDialog
          posting={posting}
          failure={changes.failure?.posting.id === posting.id ? changes.failure.message : null}
          onClose={() => setConfirming(null)}
          onConfirm={async () => {
            const deleted = await changes.remove(posting);
            // The page has nothing left to show: back to the author's list.
            if (deleted) router.push(MY_POSTINGS_HREF);
            return deleted;
          }}
        />
      )}
    </section>
  );
}
