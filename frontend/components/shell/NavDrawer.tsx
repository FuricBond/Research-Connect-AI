"use client";

import { useEffect } from "react";
import { Drawer } from "../ui/Dialog/Dialog";
import { PrimaryNav } from "./PrimaryNav";
import styles from "./NavDrawer.module.css";

/** Where the sidebar takes over (AppShell.module.css). */
const SIDEBAR_QUERY = "(min-width: 1024px)";

/**
 * The navigation below 1024px: the primary navigation in a modal drawer from the left edge.
 * The P1 Drawer (native <dialog>) gives it the focus handling: focus moves into it on open,
 * Escape, the close button and a click outside close it, and focus returns to the Menu button.
 * Following a link closes it.
 */
export function NavDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  // Widened past 1024px while open (a rotated tablet): the sidebar now shows the same links.
  useEffect(() => {
    if (!open || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(SIDEBAR_QUERY);
    const onChange = (event: MediaQueryListEvent) => {
      if (event.matches) onClose();
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [open, onClose]);

  return (
    <Drawer open={open} onClose={onClose} side="start" title="Menu" size="sm" className={styles.drawer}>
      <PrimaryNav onNavigate={onClose} />
    </Drawer>
  );
}
