import type { PlatformRole } from "../types/auth";

/** The user list's address and words. On its own: that page needs none of the monitor's rules. */
export const ROLES: readonly PlatformRole[] = ["STUDENT", "FACULTY", "ADMIN"];

export const ROLE_PLURALS: Record<PlatformRole, string> = {
  STUDENT: "Student researchers",
  FACULTY: "Faculty",
  ADMIN: "Administrators",
};

export const USERS_HREF = "/admin/users";
export const RESEARCH_DATA_HREF = "/admin/research-data";

/** Accounts per page on the users page (plan §15). */
export const USERS_PAGE_SIZE = 25;
/** The most accounts one answer holds (backend limit): the overview reads one such page. */
export const ACCOUNT_SCAN_LIMIT = 200;

export type UserStatusFilter = "active" | "inactive" | "unverified";

export const USER_STATUS_FILTERS: readonly { value: UserStatusFilter; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Deactivated" },
  { value: "unverified", label: "Not yet verified" },
];

export interface UsersQuery {
  role: PlatformRole | null;
  /** Which accounts by state: can they sign in, have they been verified. */
  status: UserStatusFilter | null;
  q: string;
  page: number;
}

export function readUsersQuery(params: URLSearchParams): UsersQuery {
  const role = params.get("role");
  const page = Number.parseInt(params.get("page") ?? "1", 10);
  return {
    role: role !== null && (ROLES as readonly string[]).includes(role) ? (role as PlatformRole) : null,
    status: USER_STATUS_FILTERS.find((filter) => filter.value === params.get("status"))?.value ?? null,
    q: (params.get("q") ?? "").trim().slice(0, 255),
    page: Number.isFinite(page) && page >= 1 ? page : 1,
  };
}

export function usersHref(query: Partial<UsersQuery>): string {
  const params = new URLSearchParams();
  if (query.role) params.set("role", query.role);
  if (query.status) params.set("status", query.status);
  if (query.q) params.set("q", query.q);
  if (query.page && query.page > 1) params.set("page", String(query.page));
  const search = params.toString();
  return search ? `${USERS_HREF}?${search}` : USERS_HREF;
}

/** What a role change does, as the backend applies it (the role is read on every request). */
export function roleChangeConsequence(to: PlatformRole, ownAccount: boolean): string {
  const effect = "It takes effect on their next request; nothing else about the account changes.";
  if (ownAccount && to !== "ADMIN") return "This is your own account: you lose access to administration as soon as the change is made, and another administrator would have to give it back.";
  if (to === "ADMIN") return `Administrators can see and change every account, including roles, and see the platform's data. ${effect}`;
  if (to === "FACULTY") return `Faculty can write research postings and decide on applications once the account is verified (from its actions menu). ${effect}`;
  return `Student researchers apply to postings and can find a supervisor; they cannot write or manage research postings or administer the platform. ${effect}`;
}
