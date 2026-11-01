"use client";

import { useEffect, useRef } from "react";
import { ChevronDown } from "lucide-react";
import type { WorkspaceItem, WorkspaceStatus } from "../../types/workspace";
import { workspaceStatusMeta } from "../../utils/status";
import { StatusBadge } from "../ui/Badge/Badge";
import { Menu } from "../ui/Menu/Menu";
import styles from "./Workspace.module.css";

/** The workflow's order, for listing the allowed moves in a sensible sequence. */
const ORDER: WorkspaceStatus[] = ["SAVED", "CONSIDERING", "PLANNING", "APPLIED", "ACCEPTED", "REJECTED", "ARCHIVED"];

export function orderedTransitions(allowed: readonly WorkspaceStatus[]): WorkspaceStatus[] {
  return ORDER.filter((status) => allowed.includes(status));
}

interface StatusMenuProps {
  item: WorkspaceItem;
  /** A change is being saved: the new status shows, nothing else can be chosen. */
  saving: boolean;
  /** False when the viewer may not change the status (a viewer of a shared item). */
  canChange?: boolean;
  onChange: (target: WorkspaceStatus) => void;
  describedBy?: string;
}

/**
 * The status as a menu (plan §13: one control instead of four "Move to" buttons). It offers only
 * the moves the server listed for this item (`allowed_transitions`, from the backend's state
 * machine), in workflow order; with none, or while a change is saving, it is a plain status badge.
 */
export function StatusMenu({ item, saving, canChange = true, onChange, describedBy }: StatusMenuProps) {
  const meta = workspaceStatusMeta(item.status);
  const moves = orderedTransitions(item.allowed_transitions);
  // P11: a move swaps the menu for "Saving…" and then for a new menu, so the button that had focus
  // is gone twice; focus follows (to the status while saving, then to the new button) instead of
  // dropping to the page.
  const holder = useRef<HTMLSpanElement>(null);
  const following = useRef(false);
  useEffect(() => {
    if (!following.current) return;
    const active = document.activeElement;
    if (active === null || active === document.body || holder.current?.contains(active)) {
      (holder.current?.querySelector<HTMLElement>("button") ?? holder.current)?.focus();
    }
    if (!saving) following.current = false;
  }, [saving]);

  if (!canChange || saving || moves.length === 0) {
    return (
      <span ref={holder} tabIndex={-1} className={styles.statusStatic}>
        <StatusBadge meta={meta} />
        {saving && <span className={styles.saving}>Saving…</span>}
      </span>
    );
  }

  const Icon = meta.icon;
  return (
    <span ref={holder} className={styles.statusHolder}>
      <Menu
        triggerLabel={`Status: ${meta.label}. Change status`}
        describedBy={describedBy}
        triggerClassName={styles.statusTrigger}
        trigger={
          <>
            {Icon && <Icon size={14} aria-hidden="true" />}
            <span>{meta.label}</span>
            <ChevronDown size={14} aria-hidden="true" />
          </>
        }
        items={moves.map((status) => ({
          id: status,
          label: `Move to ${workspaceStatusMeta(status).label.toLowerCase()}`,
          onSelect: () => {
            following.current = true;
            onChange(status);
          },
        }))}
      />
    </span>
  );
}
