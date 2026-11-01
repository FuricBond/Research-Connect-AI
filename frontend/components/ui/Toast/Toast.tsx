"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { IconButton } from "../Button/Button";
import styles from "./Toast.module.css";

const TOAST_MS = 5_000;

/**
 * A transient confirmation of a completed action, with Undo when possible (DESIGN_SYSTEM.md §8.3).
 * Bottom right on wide screens, bottom on narrow ones, in a polite live region that exists before
 * the message does. It leaves after 5 seconds, but not while the pointer is on it or focus is in
 * it, so Undo stays reachable. Errors are never toasts: they need to stay.
 */
export function Toast({ message, action, onDismiss }: { message: ReactNode; action?: ReactNode; onDismiss: () => void }) {
  const [held, setHeld] = useState(false);
  const dismiss = useRef(onDismiss);
  dismiss.current = onDismiss;

  useEffect(() => {
    if (message === null || held) return;
    const timer = window.setTimeout(() => dismiss.current(), TOAST_MS);
    return () => window.clearTimeout(timer);
  }, [message, held]);

  return (
    <div className={styles.region} role="status" aria-live="polite">
      {message !== null && (
        <div
          className={styles.toast}
          onPointerEnter={() => setHeld(true)}
          onPointerLeave={() => setHeld(false)}
          onFocus={() => setHeld(true)}
          onBlur={() => setHeld(false)}
        >
          <p className={styles.message}>{message}</p>
          {action}
          <IconButton variant="ghost" size="sm" label="Dismiss" icon={<X size={16} aria-hidden="true" />} onClick={onDismiss} />
        </div>
      )}
    </div>
  );
}
