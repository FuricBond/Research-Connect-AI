"use client";

import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";
import { X } from "lucide-react";
import { cx } from "../../../utils/cx";
import { IconButton } from "../Button/Button";
import styles from "./Dialog.module.css";

interface OverlayProps {
  open: boolean;
  /** Called on Escape, on the close button and on a click on the backdrop. */
  onClose: () => void;
  /** The accessible name and the visible heading. */
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  /** Actions; the primary one last (right). */
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
  className?: string;
  /** Close on a backdrop click (default true). */
  dismissible?: boolean;
  /** What takes focus on open; the title by default. A search sheet focuses its field. */
  initialFocusRef?: RefObject<HTMLElement | null>;
}

/**
 * Shared behaviour of Dialog and Drawer, on the native <dialog> element: showModal() makes the
 * rest of the page inert and puts the surface in the top layer. Focus moves to the title when
 * it opens and back to the element that had it when it closes; page scrolling is locked.
 */
function ModalSurface({ open, onClose, title, description, children, footer, size = "md", className, dismissible = true, initialFocusRef, side = "end", variant }: OverlayProps & { variant: "dialog" | "drawer"; side?: "start" | "end" }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const generated = useId();
  const titleId = `${variant}-${generated}-title`;
  const descriptionId = description ? `${variant}-${generated}-description` : undefined;

  // Whatever closed it, restore scrolling and focus.
  const restore = useRef(() => {
    document.documentElement.style.overflow = "";
    const target = returnFocus.current;
    returnFocus.current = null;
    if (target && target.isConnected) target.focus();
  });

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
      document.documentElement.style.overflow = "hidden";
      (initialFocusRef?.current ?? titleRef.current)?.focus();
    } else if (!open && dialog.open) {
      if (typeof dialog.close === "function") {
        dialog.close(); // fires `close`, which restores
      } else {
        dialog.removeAttribute("open");
        restore.current();
      }
    }
  }, [open, initialFocusRef]);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    // Escape fires `cancel`: let the owner decide (it controls `open`).
    const onCancel = (event: Event) => {
      event.preventDefault();
      onCloseRef.current();
    };
    const onClosed = () => restore.current();
    dialog.addEventListener("cancel", onCancel);
    dialog.addEventListener("close", onClosed);
    return () => {
      dialog.removeEventListener("cancel", onCancel);
      dialog.removeEventListener("close", onClosed);
    };
  }, []);

  // Unmounting while open still unlocks the page and returns focus.
  useEffect(() => {
    const onUnmount = restore.current;
    return () => onUnmount();
  }, []);

  return (
    <dialog
      ref={ref}
      className={cx(styles.dialog, variant === "drawer" && styles.drawer, variant === "drawer" && side === "start" && styles.start, styles[size], className)}
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onClick={(event) => {
        // A click on the <dialog> itself (not its content) is a click on the backdrop.
        if (dismissible && event.target === ref.current) onCloseRef.current();
      }}
    >
      {open && (
        <>
          <div className={styles.header}>
            <div className={styles.titles}>
              <h2 id={titleId} ref={titleRef} tabIndex={-1} className={styles.title}>
                {title}
              </h2>
              {description && (
                <p id={descriptionId} className={styles.description}>
                  {description}
                </p>
              )}
            </div>
            <IconButton label="Close" icon={<X size={18} aria-hidden="true" />} onClick={() => onCloseRef.current()} />
          </div>
          {/* Focusable so keyboard users can scroll long content (WCAG 2.1.1). */}
          <div className={styles.body} tabIndex={0}>
            {children}
          </div>
          {footer && <div className={styles.footer}>{footer}</div>}
        </>
      )}
    </dialog>
  );
}

/** A modal for decisions and short forms (max width 480). DESIGN_SYSTEM.md §8.3. */
export function Dialog(props: OverlayProps) {
  return <ModalSurface {...props} variant="dialog" />;
}

/**
 * A side sheet for secondary detail beside a list; full screen on phones. `side="start"` opens
 * it from the left (the navigation drawer); the default is the right edge.
 */
export function Drawer({ side, ...props }: OverlayProps & { side?: "start" | "end" }) {
  return <ModalSurface {...props} side={side} variant="drawer" />;
}
