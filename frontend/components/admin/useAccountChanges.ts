"use client";

import { useCallback, useRef, useState } from "react";
import { updateAdminUser } from "../../services/api";
import type { AdminUserRead, AdminUserUpdate } from "../../types/auth";
import { accountChangeError } from "./errors";

export interface ChangeNotice {
  user: AdminUserRead;
  text: string;
  /** The change that puts it back, offered as Undo. */
  undo: AdminUserUpdate | null;
}

/**
 * P10 — account changes from the users page (`PATCH /admin/users/{id}`): one request per account
 * at a time; nothing is shown before the server agrees, and what it answers is what the row shows
 * from then on — unless a newer answer about the account arrives (rows are compared by
 * `updated_at`, so a list answer requested before the change never puts the old values back). A
 * refusal leaves the server's account as it was and says why, in plain words.
 */
export function useAccountChanges(onOwnAccount: (updated: AdminUserRead) => Promise<void>, ownId: string | null) {
  const [confirmed, setConfirmed] = useState<ReadonlyMap<string, AdminUserRead>>(new Map());
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());
  const inFlight = useRef(new Set<string>());
  const [notice, setNotice] = useState<ChangeNotice | null>(null);
  const [failure, setFailure] = useState<{ user: AdminUserRead; message: string } | null>(null);

  const current = useCallback(
    (row: AdminUserRead): AdminUserRead => {
      const answer = confirmed.get(row.id);
      return answer && Date.parse(answer.updated_at) >= Date.parse(row.updated_at) ? answer : row;
    },
    [confirmed]
  );

  /** Sends one change; the server's account when it agreed, null otherwise (or when one is already on its way). */
  const change = useCallback(
    async (user: AdminUserRead, payload: AdminUserUpdate, describe?: (updated: AdminUserRead) => ChangeNotice | null): Promise<AdminUserRead | null> => {
      if (inFlight.current.has(user.id)) return null;
      inFlight.current.add(user.id);
      setPending(new Set(inFlight.current));
      setFailure(null);
      setNotice(null);
      try {
        const updated = await updateAdminUser(user.id, payload);
        setConfirmed((map) => new Map(map).set(updated.id, updated));
        setNotice(describe?.(updated) ?? null);
        if (ownId !== null && updated.id === ownId) await onOwnAccount(updated);
        return updated;
      } catch (error) {
        setFailure({ user, message: accountChangeError(error) });
        return null;
      } finally {
        inFlight.current.delete(user.id);
        setPending(new Set(inFlight.current));
      }
    },
    [onOwnAccount, ownId]
  );

  return {
    current,
    change,
    pending,
    notice,
    failure,
    dismissNotice: () => setNotice(null),
    dismissFailure: () => setFailure(null),
  };
}
