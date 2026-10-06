/**
 * P0 navigation model — the single list of destinations the header navigation renders.
 *
 * Each destination says who may see it, which group it belongs to in the "More" menu, and from
 * which viewport width it is shown directly in the bar (`inline`). Everything not shown in the
 * bar at the current width is listed in the menu, so no destination is ever lost to overflow.
 * Hiding a destination is a convenience, never a permission: every page behind these links is
 * guarded and the backend authorises every request.
 */
import type { LucideIcon } from "lucide-react";
import {
  Bell,
  BookMarked,
  BookOpen,
  Briefcase,
  Calendar,
  CalendarDays,
  Compass,
  FileText,
  GraduationCap,
  House,
  Megaphone,
  ShieldCheck,
  Sparkles,
  User,
  Users,
} from "lucide-react";
import type { PlatformRole } from "../types/auth";

/**
 * From which width a destination sits in the bar: `always` at every width, `md` from 768px,
 * `lg` from 1024px, `xl` from 1280px; `menu` only ever in the "More" menu.
 * The matching media queries live with the navigation styles in styles/globals.css.
 */
export type NavInline = "always" | "md" | "lg" | "xl" | "menu";

export type NavGroup = "start" | "discover" | "research" | "people" | "admin";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  group: NavGroup;
  /** Shown to signed-out visitors as well. */
  public?: boolean;
  /** Only these roles see it; omitted means every signed-in role. */
  roles?: readonly PlatformRole[];
  /** Where it sits for a signed-in account, and for a visitor when it is public. */
  inline: NavInline;
  inlineSignedOut?: NavInline;
  /** Whether a pathname belongs to this destination. */
  matches: (pathname: string) => boolean;
  /** Carries the unread notification count. */
  showsUnreadCount?: boolean;
}

const exactly = (path: string) => (pathname: string) => pathname === path;
const under = (path: string) => (pathname: string) => pathname === path || pathname.startsWith(`${path}/`);

export const NAV_GROUP_LABELS: Record<NavGroup, string> = {
  start: "Start",
  discover: "Discover",
  research: "My research",
  people: "People and profile",
  admin: "Administration",
};

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/dashboard", label: "Home", icon: House, group: "start", inline: "md", matches: exactly("/dashboard") },
  { href: "/", label: "Literature Search", icon: BookOpen, group: "discover", public: true, inline: "md", inlineSignedOut: "md", matches: exactly("/") },
  { href: "/browse", label: "Browse All Calls", icon: Calendar, group: "discover", public: true, inline: "lg", inlineSignedOut: "md", matches: exactly("/browse") },
  { href: "/postings", label: "Research Postings", icon: Megaphone, group: "discover", public: true, inline: "xl", inlineSignedOut: "md", matches: under("/postings") },
  { href: "/similar", label: "Similar Research", icon: Compass, group: "discover", public: true, inline: "menu", inlineSignedOut: "menu", matches: exactly("/similar") },
  { href: "/opportunities", label: "Opportunity Matcher", icon: Sparkles, group: "discover", public: true, inline: "menu", inlineSignedOut: "menu", matches: exactly("/opportunities") },
  { href: "/workspace", label: "Opportunity Workspace", icon: Briefcase, group: "research", inline: "lg", matches: under("/workspace") },
  { href: "/submissions", label: "Submissions", icon: FileText, group: "research", inline: "menu", matches: under("/submissions") },
  { href: "/reading-list", label: "Reading List", icon: BookMarked, group: "research", inline: "menu", matches: under("/reading-list") },
  { href: "/calendar", label: "Research Calendar", icon: CalendarDays, group: "research", inline: "menu", matches: under("/calendar") },
  { href: "/peers", label: "Find Peers", icon: Users, group: "people", inline: "menu", matches: under("/peers") },
  { href: "/supervisors", label: "Find a Supervisor", icon: GraduationCap, group: "people", roles: ["STUDENT"], inline: "menu", matches: under("/supervisors") },
  { href: "/researcher", label: "Researcher Profile", icon: User, group: "people", inline: "menu", matches: under("/researcher") },
  { href: "/admin", label: "Administration", icon: ShieldCheck, group: "admin", roles: ["ADMIN"], inline: "menu", matches: under("/admin") },
  {
    href: "/notifications",
    label: "Notifications",
    icon: Bell,
    group: "start",
    inline: "always",
    showsUnreadCount: true,
    matches: (pathname) => under("/notifications")(pathname) || under("/settings/notifications")(pathname),
  },
];

export interface ResolvedNavItem extends NavItem {
  /** Where it sits for this visitor. */
  placement: NavInline;
  active: boolean;
}

/**
 * The destinations this visitor may see, in display order, with their placement and whether
 * the current page belongs to them. `role` is null for a signed-out visitor.
 */
export function navigationFor(
  role: PlatformRole | null,
  pathname: string,
  items: readonly NavItem[] = NAV_ITEMS
): ResolvedNavItem[] {
  const signedIn = role !== null;
  return items
    .filter((item) => (signedIn ? !item.roles || item.roles.includes(role) : Boolean(item.public)))
    .map((item) => ({
      ...item,
      placement: signedIn ? item.inline : (item.inlineSignedOut ?? "menu"),
      active: item.matches(pathname),
    }));
}

/** The groups of the "More" menu with their destinations, in display order, empty groups left out. */
export function menuGroups(items: readonly ResolvedNavItem[]): { group: NavGroup; items: ResolvedNavItem[] }[] {
  const order: NavGroup[] = ["start", "discover", "research", "people", "admin"];
  return order
    .map((group) => ({ group, items: items.filter((item) => item.group === group && item.placement !== "always") }))
    .filter((entry) => entry.items.length > 0);
}
