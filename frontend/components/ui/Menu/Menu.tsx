"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { cx } from "../../../utils/cx";
import styles from "./Menu.module.css";

export interface MenuItem {
  id: string;
  label: ReactNode;
  onSelect: () => void;
  disabled?: boolean;
  /** A destructive action: shown in the danger colour, with its word ("Delete"). */
  danger?: boolean;
}

interface MenuProps {
  /** What the trigger shows. */
  trigger: ReactNode;
  /** The trigger's accessible name when its content is not enough ("Status: Planning. Change"). */
  triggerLabel?: string;
  items: readonly MenuItem[];
  /** Which edge of the trigger the menu lines up with. */
  align?: "start" | "end";
  disabled?: boolean;
  /** Extra class for the trigger (the status menu looks like its badge). */
  triggerClassName?: string;
  /** Describes the trigger with the object it acts on (the row's title). */
  describedBy?: string;
}

/**
 * An action menu (DESIGN_SYSTEM.md §8.3 Popover / Dropdown): a button that opens a list of
 * actions. The menu pattern: the first action takes focus, Up/Down move (wrapping), Home/End go
 * to the ends, Escape closes and returns focus to the button, Tab or a click outside closes it.
 * Choosing an action closes the menu, returns focus to the button, then runs the action.
 */
export function Menu({ trigger, triggerLabel, items, align = "start", disabled, triggerClassName, describedBy }: MenuProps) {
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const menuId = `menu-${useId()}`;

  const enabled = items.map((item, index) => (item.disabled ? -1 : index)).filter((index) => index >= 0);

  useEffect(() => {
    if (!open) return;
    itemRefs.current[enabled[0] ?? 0]?.focus();
    const onPointer = (event: PointerEvent) => {
      if (wrapper.current && !wrapper.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
    // Focus moves only when the menu opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) button.current?.focus();
  };

  const onMenuKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const current = itemRefs.current.findIndex((node) => node === document.activeElement);
    const position = enabled.indexOf(current);
    let next: number | null = null;
    if (event.key === "ArrowDown") next = enabled[(position + 1) % enabled.length];
    else if (event.key === "ArrowUp") next = enabled[(position - 1 + enabled.length) % enabled.length];
    else if (event.key === "Home") next = enabled[0];
    else if (event.key === "End") next = enabled[enabled.length - 1];
    else if (event.key === "Escape") {
      event.preventDefault();
      close(true);
      return;
    } else if (event.key === "Tab") {
      setOpen(false);
      return;
    }
    if (next !== null && next !== undefined) {
      event.preventDefault();
      itemRefs.current[next]?.focus();
    }
  };

  return (
    <div ref={wrapper} className={styles.wrapper}>
      <button
        ref={button}
        type="button"
        className={cx(styles.trigger, triggerClassName)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={triggerLabel}
        aria-describedby={describedBy}
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" && !open) {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        {trigger}
      </button>
      {open && (
        <div id={menuId} role="menu" aria-label={triggerLabel} className={cx(styles.menu, align === "end" ? styles.end : styles.start)} onKeyDown={onMenuKey}>
          {items.map((item, index) => (
            <button
              key={item.id}
              ref={(node) => {
                itemRefs.current[index] = node;
              }}
              type="button"
              role="menuitem"
              tabIndex={-1}
              disabled={item.disabled}
              className={cx(styles.item, item.danger && styles.danger)}
              onClick={() => {
                close(true);
                item.onSelect();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
