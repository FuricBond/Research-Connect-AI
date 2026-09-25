"use client";

/**
 * Phase 6.2 — Platform administration.
 *
 * Consumes the existing ADMIN-only endpoints (`GET /api/v1/admin/users`,
 * `PATCH /api/v1/admin/users/{id}`). The role gate on this page only decides what is
 * worth rendering; the backend rejects a non-administrator regardless, which is why the
 * table surfaces a 403 rather than hiding it.
 */

import React, { useCallback, useEffect, useState } from "react";
import { AlertCircle, Loader2, RefreshCw, Search, ShieldCheck } from "lucide-react";
import type { AdminUserRead, PlatformRole } from "../../types/auth";
import { ROLE_LABELS } from "../../types/auth";
import { ApiError, fetchAdminUsers, updateAdminUser } from "../../services/api";
import { RequireAuth } from "../../components/auth/RequireAuth";
import { useSession } from "../../components/auth/SessionProvider";

const ROLE_FILTERS: (PlatformRole | "")[] = ["", "STUDENT", "FACULTY", "ADMIN"];
const ASSIGNABLE_ROLES: PlatformRole[] = ["STUDENT", "FACULTY", "ADMIN"];

function AdminConsole() {
  const { user, refresh } = useSession();
  const [users, setUsers] = useState<AdminUserRead[]>([]);
  const [total, setTotal] = useState(0);
  const [roleFilter, setRoleFilter] = useState<PlatformRole | "">("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchAdminUsers({
        role: roleFilter || undefined,
        search: search.trim() || undefined,
      });
      setUsers(response.users);
      setTotal(response.total);
    } catch (err: unknown) {
      setError(
        err instanceof ApiError && err.status < 500
          ? err.detail ?? err.message
          : "Could not load accounts."
      );
    } finally {
      setLoading(false);
    }
  }, [roleFilter, search]);

  useEffect(() => {
    load();
  }, [load]);

  const applyChange = async (
    target: AdminUserRead,
    change: { role?: PlatformRole; is_active?: boolean; is_verified?: boolean }
  ) => {
    setPendingId(target.id);
    setError(null);
    try {
      const updated = await updateAdminUser(target.id, change);
      setUsers((current) => current.map((row) => (row.id === updated.id ? updated : row)));
      // Changing your own account changes what this session may do, so re-read it.
      if (user !== null && updated.id === user.id) await refresh();
    } catch (err: unknown) {
      setError(
        err instanceof ApiError && err.status < 500
          ? err.detail ?? err.message
          : "Could not update the account."
      );
    } finally {
      setPendingId(null);
    }
  };

  return (
    <div className="auth-admin">
      <header className="auth-admin-head">
        <div>
          <h1>Platform administration</h1>
          <p className="auth-admin-subtitle">
            {total} {total === 1 ? "account" : "accounts"}. Role changes take effect on the
            account&apos;s next request.
          </p>
        </div>
        <button type="button" className="auth-menu-btn" onClick={load} disabled={loading}>
          <RefreshCw size={13} aria-hidden="true" />
          Refresh
        </button>
      </header>

      <div className="auth-admin-filters">
        <div className="auth-admin-search">
          <Search size={14} aria-hidden="true" />
          <input
            type="search"
            placeholder="Search by email or name"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search accounts"
          />
        </div>
        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value as PlatformRole | "")}
          aria-label="Filter by role"
        >
          {ROLE_FILTERS.map((value) => (
            <option key={value || "ALL"} value={value}>
              {value === "" ? "All roles" : ROLE_LABELS[value]}
            </option>
          ))}
        </select>
      </div>

      {error !== null && (
        <div className="auth-error" role="alert">
          <AlertCircle size={15} aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="auth-pending" role="status">
          <Loader2 size={18} className="auth-spinner" aria-hidden="true" />
          <span>Loading accounts…</span>
        </div>
      ) : users.length === 0 ? (
        <div className="auth-admin-empty">No accounts match this filter.</div>
      ) : (
        <table className="auth-admin-table">
          <thead>
            <tr>
              <th scope="col">Account</th>
              <th scope="col">Role</th>
              <th scope="col">Active</th>
              <th scope="col">Verified</th>
            </tr>
          </thead>
          <tbody>
            {users.map((row) => (
              <tr key={row.id} className={pendingId === row.id ? "auth-admin-row-pending" : ""}>
                <td>
                  <span className="auth-admin-name">{row.full_name}</span>
                  <span className="auth-admin-email">{row.email}</span>
                </td>
                <td>
                  <select
                    value={row.role}
                    disabled={pendingId === row.id}
                    onChange={(e) => applyChange(row, { role: e.target.value as PlatformRole })}
                    aria-label={`Role for ${row.email}`}
                  >
                    {ASSIGNABLE_ROLES.map((value) => (
                      <option key={value} value={value}>
                        {ROLE_LABELS[value]}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <label className="auth-admin-toggle">
                    <input
                      type="checkbox"
                      checked={row.is_active}
                      disabled={pendingId === row.id}
                      onChange={(e) => applyChange(row, { is_active: e.target.checked })}
                      aria-label={`Active for ${row.email}`}
                    />
                    <span>{row.is_active ? "Active" : "Disabled"}</span>
                  </label>
                </td>
                <td>
                  <label className="auth-admin-toggle">
                    <input
                      type="checkbox"
                      checked={row.is_verified}
                      disabled={pendingId === row.id}
                      onChange={(e) => applyChange(row, { is_verified: e.target.checked })}
                      aria-label={`Verified for ${row.email}`}
                    />
                    <span>
                      {row.is_verified ? (
                        <>
                          <ShieldCheck size={12} aria-hidden="true" /> Verified
                        </>
                      ) : (
                        "Unverified"
                      )}
                    </span>
                  </label>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function AdminPage() {
  return (
    <RequireAuth roles={["ADMIN"]}>
      <AdminConsole />
    </RequireAuth>
  );
}
