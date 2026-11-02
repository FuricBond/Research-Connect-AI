"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useApiResource } from "../../hooks/useApiResource";
import { notifyNotificationsChanged } from "../../hooks/useUnreadNotificationCount";
import { acceptMyWorkspaceInvitation, ApiError, declineMyWorkspaceInvitation, fetchMyWorkspaceInvitations } from "../../services/api";
import type { MyWorkspaceInvitation } from "../../types/collaboration";
import { EmailConfirmationPrompt } from "../auth/EmailConfirmationPrompt";
import { useSession } from "../auth/SessionProvider";
import { Button } from "../ui/Button/Button";
import { Alert, ErrorState } from "../ui/State/State";
import styles from "./Invitations.module.css";

const ROLE_WORDS: Record<string, string> = { EDITOR: "an editor", CONTRIBUTOR: "a contributor", VIEWER: "a viewer" };

/** What can be read from a refusal: the API words these for the invitee. Anything else may be retried. */
function refusal(error: unknown, fallback: string): { text: string; final: boolean } {
  if (error instanceof ApiError && (error.status === 400 || error.status === 403 || error.status === 404) && error.detail && !error.detail.startsWith("Request failed")) {
    return { text: error.detail, final: true };
  }
  if (error instanceof ApiError && error.status === 401) return { text: "Please sign in again to answer this invitation.", final: false };
  return { text: `${fallback} Nothing was changed. Try again.`, final: false };
}

/**
 * Workspace invitations waiting for an answer (audit FUNC-01), on the notifications page: the
 * account's confirmed address is the proof, so nothing is copied or pasted and no token reaches the
 * browser. An account that has not confirmed its address sees the same words whether or not an
 * invitation exists for it, and a way to confirm (Decision C). A refusal (withdrawn, expired, already answered) is said in the API's words and the list is read
 * again; a failure leaves the invitation here to try again. Renders nothing while there is nothing
 * to answer, so a page without invitations does not change.
 */
export function PendingInvitations() {
  const { user } = useSession();
  const resource = useApiResource("workspace-invitations:mine", (signal) => fetchMyWorkspaceInvitations(signal));
  const [busy, setBusy] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [outcome, setOutcome] = useState<{ text: string; href?: string; tone: "success" | "info" } | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  const invitations = resource.data?.invitations ?? [];

  const answer = async (invitation: MyWorkspaceInvitation, action: "accept" | "decline") => {
    if (busy) return;
    setBusy(invitation.id);
    setErrors(({ [invitation.id]: _gone, ...rest }) => rest);
    try {
      if (action === "accept") {
        await acceptMyWorkspaceInvitation(invitation.id);
        setOutcome({ tone: "success", text: `You joined “${invitation.workspace_title ?? "the workspace"}”.`, href: `/workspace/${invitation.workspace_id}` });
      } else {
        await declineMyWorkspaceInvitation(invitation.id);
        setOutcome({ tone: "info", text: `You declined the invitation to “${invitation.workspace_title ?? "the workspace"}”.` });
      }
      notifyNotificationsChanged();
      resource.retry();
      heading.current?.focus();
    } catch (error) {
      const said = refusal(error, action === "accept" ? "The invitation could not be accepted." : "The invitation could not be declined.");
      setErrors((before) => ({ ...before, [invitation.id]: said.text }));
      if (said.final) {
        setOutcome({ tone: "info", text: said.text });
        resource.retry();
        heading.current?.focus();
      }
    } finally {
      setBusy(null);
    }
  };

  if (user?.email_verified === false || resource.data?.email_verified === false) {
    return (
      <section id="invitations" className={styles.section} aria-labelledby="invitations-heading">
        <h2 id="invitations-heading" tabIndex={-1} className={styles.title}>
          Workspace invitations
        </h2>
        <EmailConfirmationPrompt why={`Invitations sent to ${user?.email ?? "your address"} appear here once you confirm that it is yours.`} />
      </section>
    );
  }

  if (resource.status === "error" && !resource.data) {
    return (
      <section id="invitations" className={styles.section} aria-labelledby="invitations-heading">
        <h2 id="invitations-heading" ref={heading} tabIndex={-1} className={styles.title}>
          Workspace invitations
        </h2>
        <ErrorState bare headingLevel={3} title="Your invitations could not be loaded" kind={resource.error?.kind === "network" ? "offline" : "failed"} onRetry={resource.retry} />
      </section>
    );
  }
  if (invitations.length === 0 && !outcome) return null;

  return (
    <section id="invitations" className={styles.section} aria-labelledby="invitations-heading">
      <h2 id="invitations-heading" ref={heading} tabIndex={-1} className={styles.title}>
        Workspace invitations
      </h2>
      {outcome && (
        <Alert tone={outcome.tone} announce>
          {outcome.text} {outcome.href && <Link href={outcome.href}>Open the workspace</Link>}
        </Alert>
      )}
      {invitations.length > 0 && (
        <ul className={styles.list}>
          {invitations.map((invitation) => (
            <li key={invitation.id} className={styles.row}>
              <div className={styles.main}>
                <h3 className={styles.name}>{invitation.workspace_title ?? "A research workspace"}</h3>
                <p className={styles.meta}>
                  {invitation.inviter_name ?? "Someone"} invited you to join as {ROLE_WORDS[invitation.role] ?? "a collaborator"}. Open until{" "}
                  {new Date(invitation.expires_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}.
                </p>
                {errors[invitation.id] && (
                  <Alert tone="danger" announce>
                    {errors[invitation.id]}
                  </Alert>
                )}
              </div>
              <div className={styles.actions}>
                <Button size="sm" loading={busy === invitation.id} disabled={busy !== null} onClick={() => void answer(invitation, "accept")}>
                  Accept<span className="rc-visually-hidden"> the invitation to {invitation.workspace_title ?? "this workspace"}</span>
                </Button>
                <Button size="sm" variant="secondary" disabled={busy !== null} onClick={() => void answer(invitation, "decline")}>
                  Decline<span className="rc-visually-hidden"> the invitation to {invitation.workspace_title ?? "this workspace"}</span>
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
