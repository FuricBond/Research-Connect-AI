"use client";

import { useState } from "react";
import { resetPersonalization } from "../../services/api";
import { Button } from "../ui/Button/Button";
import { Dialog } from "../ui/Dialog/Dialog";
import { TextInput } from "../ui/Field/Field";
import { Alert } from "../ui/State/State";
import styles from "./Recommendations.module.css";

/**
 * The confirmation of a reset: what is cleared and what is kept, the same guarantees the server
 * gives. The optional reason is recorded with the reset in the control history. Loaded when asked
 * for (ResetPersonalization); closing unmounts it, which hands focus back.
 */
export function ResetDialog({ profileId, onClose, onDone }: { profileId: string; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function confirm() {
    setBusy(true);
    setFailed(false);
    try {
      await resetPersonalization(profileId, reason.trim() || undefined);
      onDone();
    } catch {
      setFailed(true);
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      onClose={() => !busy && onClose()}
      title="Reset what was learned?"
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="danger" onClick={confirm} loading={busy}>
            Reset
          </Button>
        </>
      }
    >
      <p>This clears:</p>
      <ul className={styles.plainList}>
        <li>signals learned from your saves, feedback and dismissals</li>
        <li>calibration and context adjustments</li>
      </ul>
      <p>This keeps:</p>
      <ul className={styles.plainList}>
        <li>the preferences you stated</li>
        <li>your researcher profile and publications</li>
        <li>your account, your workspace and the record of past activity</li>
      </ul>
      <p className={styles.muted}>Activity before the reset is kept on record but no longer shapes recommendations.</p>
      <TextInput label="Reason (optional)" hint="Kept with the reset in your control history." value={reason} onChange={(event) => setReason(event.target.value)} maxLength={200} />
      {failed && (
        <Alert tone="danger" announce>
          The reset did not go through. Try again.
        </Alert>
      )}
    </Dialog>
  );
}
