"use client";

import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { resetPersonalization } from "../../services/api";
import { Button } from "../ui/Button/Button";
import { Dialog } from "../ui/Dialog/Dialog";
import { TextInput } from "../ui/Field/Field";
import { Alert } from "../ui/State/State";
import styles from "./Recommendations.module.css";

/**
 * Reset what personalization learned (Phase 5.6), behind a confirmation that says what is cleared
 * and what is kept — the same guarantees the server gives. The optional reason is recorded with
 * the reset in the control history.
 */
export function ResetPersonalization({ profileId, onReset }: { profileId: string; onReset: () => void }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [notice, setNotice] = useState("");

  async function confirm() {
    setBusy(true);
    setFailed(false);
    try {
      await resetPersonalization(profileId, reason.trim() || undefined);
      setOpen(false);
      setReason("");
      setNotice("What was learned has been reset. Your stated preferences and profile are unchanged.");
      onReset();
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.group}>
      <h3 className={styles.groupTitle}>Start over</h3>
      <p className={styles.muted}>Clears what was learned from your activity. What you stated stays.</p>
      <div>
        <Button variant="secondary" size="sm" leadingIcon={<RotateCcw size={16} aria-hidden="true" />} onClick={() => setOpen(true)}>
          Reset what was learned
        </Button>
      </div>
      <p role="status" className={styles.notice}>
        {notice}
      </p>

      <Dialog
        open={open}
        onClose={() => !busy && setOpen(false)}
        title="Reset what was learned?"
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)} disabled={busy}>
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
    </div>
  );
}
