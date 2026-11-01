"use client";

import { useRef, useState, type ReactNode } from "react";
import { Button } from "../Button/Button";
import { Alert } from "../State/State";
import { Dialog } from "./Dialog";
import styles from "./Dialog.module.css";

interface ConfirmDialogProps {
  title: ReactNode;
  children: ReactNode;
  confirmLabel: string;
  /** "danger" for what cannot simply be undone. */
  tone?: "primary" | "danger";
  /** Sends the change; true when the server agreed (the dialog then closes). */
  onConfirm: () => Promise<boolean>;
  onClose: () => void;
  /** Shown in the dialog when the server refused or failed. */
  failure: string | null;
}

/**
 * A consequential change, asked before anything is sent (DESIGN_SYSTEM.md §8.3 Modal): the title
 * names the change and its object, the body its consequences. While idle, Cancel, Close, Escape and
 * the backdrop send nothing and close it. Confirm sends once; while it is being sent nothing closes
 * the dialog, so the answer is never lost (audit UI-01), and if the server does not agree it stays
 * open with the reason. Focus starts on the title and returns to the control that opened it.
 */
export function ConfirmDialog({ title, children, confirmLabel, tone = "danger", onConfirm, onClose, failure }: ConfirmDialogProps) {
  const [sending, setSending] = useState(false);
  const inFlight = useRef(false);
  const closeUnlessSending = () => {
    if (!inFlight.current) onClose();
  };
  return (
    <Dialog
      open
      size="sm"
      onClose={closeUnlessSending}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={closeUnlessSending} disabled={sending}>
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
              let agreed = false;
              try {
                agreed = await onConfirm();
              } finally {
                inFlight.current = false;
                setSending(false);
              }
              if (agreed) onClose();
            }}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className={styles.confirmBody}>
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
