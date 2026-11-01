"use client";

import type { AdminUserRead, PlatformRole } from "../../types/auth";
import { ROLE_LABELS } from "../../types/auth";
import { roleChangeConsequence } from "../../utils/adminUsers";
import { ConfirmDialog } from "../ui/Dialog/ConfirmDialog";
import styles from "./Admin.module.css";

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
    <ConfirmDialog
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
    </ConfirmDialog>
  );
}

/** Deactivating one's own account signs one out at once; Undo would not be reachable. */
export function DeactivateSelfDialog({ user, onConfirm, onClose, failure }: { user: AdminUserRead; onConfirm: () => Promise<boolean>; onClose: () => void; failure: string | null }) {
  return (
    <ConfirmDialog title="Deactivate your own account?" confirmLabel="Deactivate my account" tone="danger" onConfirm={onConfirm} onClose={onClose} failure={failure}>
      <p>
        You ({user.email}) are signed out everywhere at once and cannot sign in again until another administrator reactivates the account.
      </p>
    </ConfirmDialog>
  );
}
