"use client";

import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState, type FocusEvent, type ReactNode } from "react";
import { currentHref } from "../../utils/navigation";

/**
 * A button that shows and hides a panel below it (WAI-ARIA disclosure). `children` may be a
 * function of (close, the current page's shell href) for panels with links.
 */
export function Disclosure({
  button,
  buttonClassName,
  className,
  panelClassName,
  label,
  title,
  children,
}: {
  button: ReactNode;
  buttonClassName: string;
  /** The wrapper: positioned for a panel anchored to the button, static to anchor it higher up. */
  className?: string;
  panelClassName: string;

  /** The button's accessible name. */
  label: string;
  title?: string;
  /** A function also gets whether the panel is open, to render what it loads only while open. */
  children: ReactNode | ((close: () => void, current: string | null, open: boolean) => ReactNode);
}) {
  const pathname = usePathname() ?? "/";
  // Open only on the page it was opened on: following a link closes it without an effect (and
  // coming back to that page does not reopen it).
  const [openOn, setOpenOn] = useState<string | null>(null);
  if (openOn !== null && openOn !== pathname) setOpenOn(null);
  const open = openOn === pathname;
  const panelId = useId();
  const area = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const close = () => setOpenOn(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!area.current?.contains(event.target as Node)) setOpenOn(null);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpenOn(null);
      trigger.current?.focus();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  // Tabbing out of the open panel closes it (focus has already moved on; leave it there).
  const onBlur = (event: FocusEvent<HTMLDivElement>) => {
    const next = event.relatedTarget as Node | null;
    if (open && next !== null && !area.current?.contains(next)) setOpenOn(null);
  };

  return (
    <div ref={area} className={className} onBlur={onBlur}>
      <button
        ref={trigger}
        type="button"
        className={buttonClassName}
        aria-label={label}
        aria-expanded={open}
        aria-controls={panelId}
        title={title}
        onClick={() => setOpenOn(open ? null : pathname)}
      >
        {button}
      </button>
      <div id={panelId} className={panelClassName} hidden={!open}>
        {typeof children === "function" ? children(close, currentHref(pathname), open) : children}
      </div>
    </div>
  );
}
