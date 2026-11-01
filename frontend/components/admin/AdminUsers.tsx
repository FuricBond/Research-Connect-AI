"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { Ban, CheckCircle2, ChevronDown } from "lucide-react";
import { useAddressSearch } from "../../hooks/useAddressSearch";
import type { AdminUserListResponse, AdminUserRead, PlatformRole } from "../../types/auth";
import { ROLE_LABELS } from "../../types/auth";
import { readUsersQuery, ROLE_PLURALS, ROLES, USER_STATUS_FILTERS, USERS_PAGE_SIZE, usersHref, type UsersQuery } from "../../utils/adminUsers";
import { useSession } from "../auth/SessionProvider";
import { StatusBadge } from "../ui/Badge/Badge";
import { Button, ButtonLink } from "../ui/Button/Button";
import { SearchInput } from "../ui/Field/Field";
import { Menu } from "../ui/Menu/Menu";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { Toast } from "../ui/Toast/Toast";
import { Pagination } from "../ui/Pagination/Pagination";
import { Alert, EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import { useKeptFor, usersKey, useUsersPage } from "./resources";
import { useAccountChanges } from "./useAccountChanges";
import styles from "./Admin.module.css";

type Confirming = { kind: "role"; user: AdminUserRead; to: PlatformRole } | { kind: "deactivate-self"; user: AdminUserRead } | null;

// Asked only when a change needs confirming.
const RoleChangeDialog = dynamic(() => import("./AdminDialogs").then((loaded) => loaded.RoleChangeDialog), { ssr: false });
const DeactivateSelfDialog = dynamic(() => import("./AdminDialogs").then((loaded) => loaded.DeactivateSelfDialog), { ssr: false });

function nameOf(user: AdminUserRead): string {
  return user.full_name.trim() || user.email;
}

function joined(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/**
 * P10 — Users (`/admin/users`, plan §15): every account, 25 a page, searched by name or email and
 * filtered by role and status, all in the address (`?role=&status=&q=&page=`), so back, forward and a shared link
 * open the same page. From 1024px a table; below, each account stacks as a card with its labels.
 *
 * A role change goes through the row's role menu and a confirmation naming the person, the old and
 * new role and what changes; dismissing it sends nothing, confirming sends one request, and the
 * row shows the role the server answers with. Activation and verification apply at once with Undo
 * (deactivating one's own account asks first). The server refuses to demote or deactivate the last
 * active administrator, and the page says so. The page's guard is a convenience: every request is
 * authorised by the backend.
 */
export function AdminUsers() {
  const { user: me, refresh } = useSession();
  const [params, go] = useAddressSearch();
  const query = readUsersQuery(params);
  const key = usersKey(query);
  const list = useUsersPage(query);
  // Try again keeps the rows; another page, filter or search never shows this one's.
  const data = useKeptFor(key, list);
  const changes = useAccountChanges(async () => {
    // One's own role or activity changed what this session may do: read the account again.
    await refresh();
  }, me?.id ?? null);
  const [confirming, setConfirming] = useState<Confirming>(null);
  const [search, setSearch] = useState(query.q);
  const [announcement, setAnnouncement] = useState("");

  // Back and forward change the address: the field follows it.
  useEffect(() => setSearch(query.q), [query.q]);

  const rows = data ? data.users.map(changes.current) : null;
  const loading = data === undefined && (list.status === "loading" || list.status === "idle");
  const filtered = query.role !== null || query.status !== null || query.q !== "";
  const failure = changes.failure && !confirming ? changes.failure : null;
  const visit = (next: Partial<UsersQuery>) => go(usersHref({ ...query, ...next }));

  const describe = (user: AdminUserRead, active: boolean | null, verified: boolean | null): string => {
    const name = nameOf(user);
    if (active === true) return `${name} can sign in again. Sessions ended by the deactivation stay ended.`;
    if (active === false) return `${name} is deactivated: signed out everywhere and unable to sign in.`;
    if (verified === true) return `${name} is marked as verified.`;
    return `${name} is no longer marked as verified.`;
  };

  const setActive = (user: AdminUserRead, active: boolean) => {
    if (!active && user.id === me?.id) {
      changes.dismissFailure();
      setConfirming({ kind: "deactivate-self", user });
      return;
    }
    void changes.change(user, { is_active: active }, (updated) => ({ user: updated, text: describe(updated, active, null), undo: { is_active: !active } }));
  };

  const setVerified = (user: AdminUserRead, verified: boolean) => {
    void changes.change(user, { is_verified: verified }, (updated) => ({ user: updated, text: describe(updated, null, verified), undo: { is_verified: !verified } }));
  };

  const undo = () => {
    const notice = changes.notice;
    if (!notice?.undo) return;
    const { undo: payload } = notice;
    void changes.change(notice.user, payload, (updated) => ({
      user: updated,
      text: `Undone: ${describe(updated, payload.is_active ?? null, payload.is_verified ?? null)}`,
      undo: null,
    }));
  };

  const statusWord = USER_STATUS_FILTERS.find((filter) => filter.value === query.status)?.label;
  const heading = [
    query.q ? `Accounts matching “${query.q}”` : query.role ? ROLE_PLURALS[query.role] : statusWord ? "Accounts" : "All accounts",
    query.q && query.role ? ROLE_PLURALS[query.role].toLowerCase() : null,
    statusWord?.toLowerCase(),
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <>
      <PageHeader
        title="Users"
        description="Every account on the platform: its role, whether it can sign in, and whether it is verified. Role changes take effect on the account's next request."
      />

      <div className={styles.toolbar}>
        <form
          role="search"
          aria-label="Accounts"
          className={styles.searchForm}
          onSubmit={(event) => {
            event.preventDefault();
            visit({ q: search.trim(), page: 1 });
          }}
        >
          <SearchInput
            label="Search by name or email"
            value={search}
            maxLength={255}
            onChange={(event) => setSearch(event.target.value)}
            onClear={() => {
              setSearch("");
              visit({ q: "", page: 1 });
            }}
            className={styles.searchField}
          />
          <Button type="submit" variant="secondary">
            Search
          </Button>
        </form>
        <div className={styles.chips} role="group" aria-label="Filter by role">
          {[null, ...ROLES].map((role) => (
            <button key={role ?? "ALL"} type="button" className={styles.chip} aria-pressed={query.role === role} onClick={() => visit({ role, page: 1 })}>
              {role ? ROLE_PLURALS[role] : "All roles"}
            </button>
          ))}
        </div>
        <div className={styles.chips} role="group" aria-label="Filter by status">
          {[null, ...USER_STATUS_FILTERS].map((filter) => (
            <button key={filter?.value ?? "ANY"} type="button" className={styles.chip} aria-pressed={query.status === (filter?.value ?? null)} onClick={() => visit({ status: filter?.value ?? null, page: 1 })}>
              {filter?.label ?? "Any status"}
            </button>
          ))}
        </div>
      </div>

      <Toast
        message={changes.notice?.text ?? null}
        onDismiss={changes.dismissNotice}
        action={
          changes.notice?.undo ? (
            <Button size="sm" variant="secondary" onClick={undo} disabled={changes.pending.has(changes.notice.user.id)}>
              Undo
            </Button>
          ) : undefined
        }
      />
      <section className={styles.results} aria-labelledby="users-heading" aria-busy={list.status === "loading" || undefined}>
        <div className={styles.resultsHead}>
          <h2 id="users-heading" className={styles.resultsTitle}>
            {heading}
          </h2>
          {data && (
            <p className={styles.secondary}>
              {data.total.toLocaleString("en")} {data.total === 1 ? "account" : "accounts"}
            </p>
          )}
        </div>
        <p role="status" className="rc-visually-hidden">
          {announcement}
        </p>
        {failure && (
          <Alert
            tone="danger"
            announce
            action={
              <Button size="sm" variant="ghost" onClick={changes.dismissFailure}>
                Dismiss
              </Button>
            }
          >
            {failure.message} Nothing about {nameOf(failure.user)} was changed.
          </Alert>
        )}

        {loading ? (
          <SkeletonList rows={5} lines={1} label="Loading the accounts" />
        ) : rows === null || data === undefined ? (
          <UsersError resource={list} />
        ) : rows.length === 0 ? (
          <NoUsers data={data} query={query} filtered={filtered} visit={visit} />
        ) : (
          <>
            <table className={styles.table} role="table">
              <caption className="rc-visually-hidden">{heading}</caption>
              <thead role="rowgroup">
                <tr role="row">
                  <th role="columnheader" scope="col">
                    Account
                  </th>
                  <th role="columnheader" scope="col">
                    Role
                  </th>
                  <th role="columnheader" scope="col">
                    Status
                  </th>
                  <th role="columnheader" scope="col">
                    Joined
                  </th>
                  <th role="columnheader" scope="col">
                    <span className="rc-visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody role="rowgroup">
                {rows.map((user) => (
                  <UserRow
                    key={user.id}
                    user={user}
                    own={user.id === me?.id}
                    pending={changes.pending.has(user.id)}
                    onRole={(to) => {
                      changes.dismissFailure();
                      changes.dismissNotice();
                      setConfirming({ kind: "role", user, to });
                    }}
                    onActive={(active) => setActive(user, active)}
                    onVerified={(verified) => setVerified(user, verified)}
                  />
                ))}
              </tbody>
            </table>
            {data.total > USERS_PAGE_SIZE && (
              <Pagination page={query.page} total={data.total} pageSize={USERS_PAGE_SIZE} noun="accounts" label="Account pages" onPage={(page) => visit({ page })} />
            )}
          </>
        )}
      </section>

      {confirming?.kind === "role" && (
        <RoleChangeDialog
          user={confirming.user}
          to={confirming.to}
          ownAccount={confirming.user.id === me?.id}
          failure={changes.failure?.user.id === confirming.user.id ? changes.failure.message : null}
          onClose={() => setConfirming(null)}
          onConfirm={async () => {
            const updated = await changes.change(confirming.user, { role: confirming.to });
            if (updated) setAnnouncement(`${nameOf(updated)} is now ${ROLE_LABELS[updated.role].toLowerCase()}.`);
            return updated !== null;
          }}
        />
      )}
      {confirming?.kind === "deactivate-self" && (
        <DeactivateSelfDialog
          user={confirming.user}
          failure={changes.failure?.user.id === confirming.user.id ? changes.failure.message : null}
          onClose={() => setConfirming(null)}
          onConfirm={async () => (await changes.change(confirming.user, { is_active: false })) !== null}
        />
      )}
    </>
  );
}

function UsersError({ resource }: { resource: ReturnType<typeof useUsersPage> }) {
  const kind = resource.error?.kind;
  if (kind === "forbidden" || kind === "unauthorized") {
    return <ErrorState kind="permission" title="Only administrators can see the accounts." description="The server refused to list them for this account." />;
  }
  return (
    <ErrorState
      kind={kind === "network" ? "offline" : "failed"}
      title="The accounts could not be loaded."
      onRetry={resource.retry}
      announce={resource.retries > 0}
    />
  );
}

function NoUsers({ data, query, filtered, visit }: { data: AdminUserListResponse; query: UsersQuery; filtered: boolean; visit: (next: Partial<UsersQuery>) => void }) {
  if (data.total > 0) {
    // A page past the last one (an old link, accounts removed since).
    const last = Math.max(1, Math.ceil(data.total / USERS_PAGE_SIZE));
    return (
      <EmptyState
        variant="no-results"
        title={`There is no page ${query.page} of these accounts.`}
        description={`They fill ${last} ${last === 1 ? "page" : "pages"}.`}
        actions={
          <Button variant="secondary" onClick={() => visit({ page: last })}>
            Go to page {last}
          </Button>
        }
      />
    );
  }
  if (filtered) {
    return (
      <EmptyState
        variant="no-results"
        title={query.q ? `No accounts match “${query.q}”${query.role ? ` among ${ROLE_PLURALS[query.role].toLowerCase()}` : ""}.` : `There are no ${ROLE_PLURALS[query.role!].toLowerCase()} accounts.`}
        description="Search matches part of a name or an email address."
        actions={<ButtonLink href={usersHref({})}>Show all accounts</ButtonLink>}
      />
    );
  }
  return <EmptyState title="There are no accounts yet." />;
}

function UserRow({
  user,
  own,
  pending,
  onRole,
  onActive,
  onVerified,
}: {
  user: AdminUserRead;
  own: boolean;
  pending: boolean;
  onRole: (to: PlatformRole) => void;
  onActive: (active: boolean) => void;
  onVerified: (verified: boolean) => void;
}) {
  const name = nameOf(user);
  const roleItems = ROLES.filter((role) => role !== user.role).map((role) => ({ id: role, label: ROLE_LABELS[role], onSelect: () => onRole(role) }));
  const actions = [
    user.is_active
      ? { id: "deactivate", label: own ? "Deactivate my account" : "Deactivate account", danger: true, onSelect: () => onActive(false) }
      : { id: "reactivate", label: "Reactivate account", onSelect: () => onActive(true) },
    user.is_verified ? { id: "unverify", label: "Mark as not verified", onSelect: () => onVerified(false) } : { id: "verify", label: "Mark as verified", onSelect: () => onVerified(true) },
  ];

  return (
    <tr role="row" className={styles.row}>
      <td role="cell" className={styles.accountCell}>
        <span className={styles.accountName}>
          {name}
          {own && <span className={styles.you}> (you)</span>}
        </span>
        <span className={styles.secondary}>{user.email}</span>
      </td>
      <td role="cell" data-label="Role">
        <Menu
          trigger={
            <>
              {ROLE_LABELS[user.role]} <ChevronDown size={14} aria-hidden="true" />
            </>
          }
          triggerLabel={`Role of ${name}: ${ROLE_LABELS[user.role]}. Change the role`}
          triggerClassName={styles.roleTrigger}
          items={roleItems}
          disabled={pending}
        />
      </td>
      <td role="cell" data-label="Status">
        <span className={styles.statusCell}>
          <StatusBadge meta={user.is_active ? { label: "Active", tone: "success", icon: CheckCircle2 } : { label: "Deactivated", tone: "muted", icon: Ban }} />
          <span className={styles.secondary}>{user.is_verified ? "Verified" : "Not verified"}</span>
        </span>
      </td>
      <td role="cell" data-label="Joined">
        {joined(user.created_at)}
      </td>
      <td role="cell" className={styles.actionsCell}>
        <Menu trigger="Actions" triggerLabel={`Actions for ${name}`} items={actions} align="end" disabled={pending} />
        {pending && (
          <span className={styles.saving} role="status">
            Saving…
          </span>
        )}
      </td>
    </tr>
  );
}
