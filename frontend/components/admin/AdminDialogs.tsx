"use client";

import { useRef, useState, type ReactNode } from "react";
import type { AdminUserRead, PlatformRole } from "../../types/auth";
import { ROLE_LABELS } from "../../types/auth";
import { roleChangeConsequence } from "../../utils/admin";
import { Button } from "../ui/Button/Button";
import { Dialog } from "../ui/Dialog/Dialog";
import { Alert } from "../ui/State/State";
import styles from "./Admin.module.css";

interface ConfirmProps {
  title: ReactNode;
  children: ReactNode;
  confirmLabel: string;
  /** "danger" for what cannot simply be undone (deactivating, removing administration). */
  tone: "primary" | "danger";
  /** Sends the change; true when the server agreed (the dialog then closes). */
  onConfirm: () => Promise<boolean>;
  onClose: () => void;
  /** Shown in the dialog when the server refused or failed. */
  failure: string | null;
}

/**
 * A consequential account change, asked before anything is sent (DESIGN_SYSTEM.md §8.3 Modal; as
 * P9's ConfirmDialogs): the title names the person and the change, the body its consequences.
 * Cancel, Close, Escape and the backdrop send nothing; Confirm sends once (a second click while it
 * is being sent does nothing) and the dialog stays open with the reason if the server does not
 * agree. Focus starts on the title and returns to the control that opened it.
 */
function ConfirmChange({ title, children, confirmLabel, tone, onConfirm, onClose, failure }: ConfirmProps) {
  const [sending, setSending] = useState(false);
  const inFlight = useRef(false);
  return (
    <Dialog
      open
      size="sm"
      onClose={() => {
        if (!inFlight.current) onClose();
      }}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={sending}>
            Cancel
          </Button>
          <Button
            variant={tone}
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

function nameOf(user: AdminUserRead): string {
  return user.full_name.trim() || user.email;
}

/** "Change Ada Lovelace's role from Faculty to Administrator?" */
export function RoleChangeDialog({
  user,
  to,
  ownAccount,
  onConfirm,
  onClose,
  failure,
}: {
  user: AdminUserRead;
  to: PlatformRole;
  ownAccount: boolean;
  onConfirm: () => Promise<boolean>;
  onClose: () => void;
  failure: string | null;
}) {
  const name = nameOf(user);
  return (
    <ConfirmChange
      title={
        <>
          Change {ownAccount ? "your own" : `${name}’s`} role from {ROLE_LABELS[user.role]} to {ROLE_LABELS[to]}?
        </>
      }
      confirmLabel={`Make ${ownAccount ? "me" : name.split(" ")[0]} ${ROLE_LABELS[to].toLowerCase()}`}
      tone={user.role === "ADMIN" || to === "ADMIN" ? "danger" : "primary"}
      onConfirm={onConfirm}
      onClose={onClose}
      failure={failure}
    >
      <p>
        <span className={styles.strong}>{name}</span> <span className={styles.secondary}>{user.email}</span>
      </p>
      <p>{roleChangeConsequence(to, ownAccount)}</p>
    </ConfirmChange>
  );
}

/** Deactivating one's own account signs one out at once; Undo would not be reachable. */
export function DeactivateSelfDialog({ user, onConfirm, onClose, failure }: { user: AdminUserRead; onConfirm: () => Promise<boolean>; onClose: () => void; failure: string | null }) {
  return (
    <ConfirmChange title="Deactivate your own account?" confirmLabel="Deactivate my account" tone="danger" onConfirm={onConfirm} onClose={onClose} failure={failure}>
      <p>
        You ({user.email}) are signed out everywhere at once and cannot sign in again until another administrator reactivates the account.
      </p>
    </ConfirmChange>
  );
}
