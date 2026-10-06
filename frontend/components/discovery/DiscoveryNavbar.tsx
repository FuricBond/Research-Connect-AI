"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, Menu } from "lucide-react";
import { useSession } from "../auth/SessionProvider";
import { useUnreadNotificationCount } from "../../hooks/useUnreadNotificationCount";
import { NAV_GROUP_LABELS, menuGroups, navigationFor, type ResolvedNavItem } from "../../utils/navigation";

/**
 * The header navigation (P0 bridge to the future application shell).
 *
 * The destinations come from utils/navigation.ts. Each one is either shown in the bar from a
 * given width or listed in the "More" menu (called "Menu" on phones), and the menu lists
 * exactly the destinations the bar is not showing at that width — so nothing is lost when the
 * window is narrow. The bar never scrolls sideways. The current page carries
 * aria-current="page", in the bar and in the menu.
 *
 * Tabs whose pages need an account appear only once there is one, and role-specific tabs only
 * for that role. Hiding a tab is a convenience, never a permission: the pages behind them are
 * guarded and the backend authorises every request.
 */
export function DiscoveryNavbar() {
  const pathname = usePathname() ?? "/";
  const { status, role } = useSession();

  // Treat "still restoring" as not signed in: a tab that appears is better than one that
  // appears and then vanishes.
  const isAuthenticated = status === "authenticated" && role !== null;
  // Phase 5.16: refreshed every 30 s while the tab is visible.
  const unreadCount = useUnreadNotificationCount(isAuthenticated);

  const items = navigationFor(isAuthenticated ? role : null, pathname);
  const barItems = items.filter((item) => item.placement !== "menu");
  const groups = menuGroups(items);
  const activeItem = items.find((item) => item.active);

  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();
  const menuButton = useRef<HTMLButtonElement>(null);
  const menuArea = useRef<HTMLDivElement>(null);

  // Following a link closes the menu.
  useEffect(() => setMenuOpen(false), [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!menuArea.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButton.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  return (
    <nav className="discovery-nav" aria-label="Main">
      <ul className="discovery-nav-tabs">
        {barItems.map((item) => (
          <li key={item.href} className="discovery-nav-item" data-inline={item.placement}>
            <NavLink item={item} className="discovery-nav-tab" unreadCount={unreadCount} />
          </li>
        ))}
      </ul>

      {groups.length > 0 && (
        <div className="discovery-nav-more" ref={menuArea}>
          <button
            ref={menuButton}
            type="button"
            className="discovery-nav-more-btn"
            aria-expanded={menuOpen}
            aria-controls={menuId}
            onClick={() => setMenuOpen((open) => !open)}
            // The button marks the current section only while that section's link is inside the
            // menu at this width (see the styles keyed on data-active-inline).
            data-active-inline={activeItem && activeItem.placement !== "always" ? activeItem.placement : undefined}
          >
            <Menu size={16} aria-hidden="true" className="discovery-nav-more-icon-narrow" />
            <span className="discovery-nav-more-label-wide">More</span>
            <span className="discovery-nav-more-label-narrow">Menu</span>
            <ChevronDown size={14} aria-hidden="true" className="discovery-nav-more-chevron" />
          </button>

          <div id={menuId} className="discovery-nav-menu" hidden={!menuOpen}>
            {groups.map(({ group, items: groupItems }) => (
              <div
                key={group}
                className="discovery-nav-menu-group"
                role="group"
                aria-labelledby={`${menuId}-${group}`}
                data-hide-from={emptyFrom(groupItems)}
              >
                <p id={`${menuId}-${group}`} className="discovery-nav-menu-heading">
                  {NAV_GROUP_LABELS[group]}
                </p>
                <ul>
                  {groupItems.map((item) => (
                    <li key={item.href} className="discovery-nav-menu-item" data-inline={item.placement}>
                      <NavLink item={item} className="discovery-nav-menu-link" unreadCount={unreadCount} />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}
    </nav>
  );
}

const WIDTH_ORDER = ["md", "lg", "xl"] as const;

/**
 * The width from which every destination of a menu group is in the bar, so the group (and its
 * heading) has nothing left to show; undefined when the group always keeps something.
 */
function emptyFrom(items: readonly ResolvedNavItem[]): (typeof WIDTH_ORDER)[number] | undefined {
  if (items.some((item) => item.placement === "menu")) return undefined;
  let widest: (typeof WIDTH_ORDER)[number] | undefined;
  for (const item of items) {
    const index = WIDTH_ORDER.indexOf(item.placement as (typeof WIDTH_ORDER)[number]);
    if (index >= 0 && (widest === undefined || index > WIDTH_ORDER.indexOf(widest))) widest = WIDTH_ORDER[index];
  }
  return widest;
}

function NavLink({
  item,
  className,
  unreadCount,
}: {
  item: ResolvedNavItem;
  className: string;
  unreadCount: number | null;
}) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      className={`${className}${item.active ? " active" : ""}`}
      aria-current={item.active ? "page" : undefined}
    >
      <Icon size={16} aria-hidden="true" />
      <span>{item.label}</span>
      {item.showsUnreadCount && unreadCount !== null && unreadCount > 0 && (
        <span className="nav-unread-badge">
          {unreadCount > 99 ? "99+" : unreadCount}
          <span className="visually-hidden"> unread</span>
        </span>
      )}
    </Link>
  );
}
