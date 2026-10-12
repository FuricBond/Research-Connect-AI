/**
 * The application's destinations: one list for the whole shell (P2).
 *
 * The primary navigation (the sidebar from 1024px, the navigation drawer below) shows the
 * destinations grouped by task; the account menu shows the account's own pages; the
 * notification bell is the one way to the notifications. Each destination says who may see
 * it. Hiding a destination is a convenience, never a permission: every page behind these links
 * is guarded and the backend authorises every request.
 */
import type { LucideIcon } from "lucide-react";
import {
  BookMarked,
  BookOpen,
  Briefcase,
  CalendarDays,
  ClipboardList,
  Compass,
  FileText,
  GraduationCap,
  House,
  Megaphone,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  User,
  Users,
} from "lucide-react";
import type { PlatformRole } from "../types/auth";

export type NavGroup = "start" | "discover" | "research" | "people" | "admin";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Shown to signed-out visitors as well. */
  public?: boolean;
  /** Only these roles see it; omitted means every signed-in role. */
  roles?: readonly PlatformRole[];
}

export interface NavSection {
  group: NavGroup;
  /** The visible group label; the first group (Home) has none. */
  label?: string;
  items: readonly NavItem[];
}

/** The primary navigation, in display order: grouped by what a person is doing. */
export const NAV_SECTIONS: readonly NavSection[] = [
  {
    group: "start",
    items: [{ href: "/dashboard", label: "Home", icon: House }],
  },
  {
    group: "discover",
    label: "Discover",
    items: [
      { href: "/", label: "Literature search", icon: BookOpen, public: true },
      { href: "/browse", label: "Calls for papers", icon: Megaphone, public: true },
      { href: "/postings", label: "Research postings", icon: ClipboardList, public: true },
      { href: "/similar", label: "Similar research", icon: Compass, public: true },
      { href: "/opportunities", label: "Opportunity matcher", icon: Sparkles, public: true },
    ],
  },
  {
    group: "research",
    label: "My research",
    items: [
      { href: "/workspace", label: "Workspace", icon: Briefcase },
      { href: "/submissions", label: "Submissions", icon: FileText },
      { href: "/reading-list", label: "Reading list", icon: BookMarked },
      { href: "/calendar", label: "Calendar", icon: CalendarDays },
    ],
  },
  {
    group: "people",
    label: "People",
    items: [
      { href: "/supervisors", label: "Find a supervisor", icon: GraduationCap, roles: ["STUDENT"] },
      { href: "/peers", label: "Find peers", icon: Users },
    ],
  },
  {
    group: "admin",
    label: "Administration",
    items: [{ href: "/admin", label: "Platform administration", icon: ShieldCheck, roles: ["ADMIN"] }],
  },
];

/**
 * The account's own pages, in the account menu (signed-in only). P3: Settings (the account and
 * its password, with the way to the notification settings beneath it) replaces the direct link
 * to the notification settings, as the plan's account menu has it.
 */
export const ACCOUNT_ITEMS: readonly NavItem[] = [
  { href: "/researcher", label: "Researcher profile", icon: User },
  { href: "/researcher/preferences", label: "Research preferences", icon: SlidersHorizontal },
  { href: "/settings", label: "Settings", icon: Settings },
];

/** The notification bell's destination. */
export const NOTIFICATIONS_HREF = "/notifications";

/** Every href the shell links to, for the route-coverage test. */
export const SHELL_HREFS: readonly string[] = [
  ...NAV_SECTIONS.flatMap((section) => section.items.map((item) => item.href)),
  ...ACCOUNT_ITEMS.map((item) => item.href),
  NOTIFICATIONS_HREF,
];

/** Whether `pathname` is `href` or a page beneath it ("/" only matches itself). */
export function isWithin(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * The one shell link that stands for the current page: the most specific href the pathname
 * is within, so /researcher/preferences is "Research preferences", not "Researcher profile".
 * Null when no shell link stands for it (sign-in, a posting's own page is still "Research
 * postings").
 */
export function currentHref(pathname: string, hrefs: readonly string[] = SHELL_HREFS): string | null {
  let best: string | null = null;
  for (const href of hrefs) {
    if (isWithin(pathname, href) && (best === null || href.length > best.length)) best = href;
  }
  return best;
}

function visibleTo(item: NavItem, role: PlatformRole | null): boolean {
  if (role === null) return Boolean(item.public);
  return !item.roles || item.roles.includes(role);
}

/**
 * The primary navigation this visitor may see, empty groups left out. `role` is null for a
 * signed-out visitor.
 */
export function navigationFor(role: PlatformRole | null): NavSection[] {
  return NAV_SECTIONS.map((section) => ({ ...section, items: section.items.filter((item) => visibleTo(item, role)) })).filter(
    (section) => section.items.length > 0
  );
}

/** The account menu's pages for a signed-in role. */
export function accountItemsFor(role: PlatformRole): NavItem[] {
  return ACCOUNT_ITEMS.filter((item) => visibleTo(item, role));
}
