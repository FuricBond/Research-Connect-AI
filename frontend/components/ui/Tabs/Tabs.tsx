"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { cx } from "../../../utils/cx";
import styles from "./Tabs.module.css";

export interface TabItem {
  id: string;
  label: string;
  /** Shown after the label ("Tasks 4"); left out while unknown, never shown as 0. */
  count?: number | null;
}

interface TabsProps {
  /** The tab list's accessible name ("Workspace item"). */
  label: string;
  tabs: readonly TabItem[];
  selected: string;
  onSelect: (id: string) => void;
  /** Prefix for the tab and panel ids, unique on the page. */
  idPrefix: string;
  className?: string;
}

export const tabId = (prefix: string, id: string) => `${prefix}-tab-${id}`;
export const panelId = (prefix: string, id: string) => `${prefix}-panel-${id}`;

/**
 * Tabs (DESIGN_SYSTEM.md §8.3) — views of the same object. The ARIA tabs pattern: one Tab stop
 * (the selected tab), Left/Right move and select, Home/End go to the ends. On a narrow screen
 * (or with large text) the tabs wrap onto another line, so none is out of view and the page never
 * widens. Not for page navigation: that is links with `aria-current`.
 */
export function Tabs({ label, tabs, selected, onSelect, idPrefix, className }: TabsProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const move = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = tabs.length - 1;
    const target =
      event.key === "ArrowRight" ? (index === last ? 0 : index + 1)
      : event.key === "ArrowLeft" ? (index === 0 ? last : index - 1)
      : event.key === "Home" ? 0
      : event.key === "End" ? last
      : null;
    if (target === null) return;
    event.preventDefault();
    refs.current[target]?.focus();
    onSelect(tabs[target].id);
  };

  return (
    <div className={cx(styles.scroller, className)}>
      <div role="tablist" aria-label={label} className={styles.list}>
        {tabs.map((tab, index) => {
          const active = tab.id === selected;
          return (
            <button
              key={tab.id}
              ref={(node) => {
                refs.current[index] = node;
              }}
              type="button"
              role="tab"
              id={tabId(idPrefix, tab.id)}
              aria-selected={active}
              aria-controls={panelId(idPrefix, tab.id)}
              tabIndex={active ? 0 : -1}
              className={cx(styles.tab, active && styles.active)}
              onClick={() => onSelect(tab.id)}
              onKeyDown={(event) => move(event, index)}
            >
              <span>
                {tab.label}
                {typeof tab.count === "number" && (
                  <>
                    {" "}
                    <span className={styles.count}>{tab.count}</span>
                  </>
                )}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/**
 * The panel of one tab: named by its tab, and a Tab stop so its content can be reached. A panel
 * already opened can stay mounted but `hidden`, so going back to its tab shows what it had
 * (and its form drafts) without asking the server again.
 */
export function TabPanel({ idPrefix, id, children, className, hidden }: { idPrefix: string; id: string; children: ReactNode; className?: string; hidden?: boolean }) {
  return (
    <div role="tabpanel" id={panelId(idPrefix, id)} aria-labelledby={tabId(idPrefix, id)} tabIndex={0} hidden={hidden} className={cx(styles.panel, className)}>
      {children}
    </div>
  );
}
