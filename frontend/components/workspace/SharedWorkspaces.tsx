"use client";

import Link from "next/link";
import { useApiResource } from "../../hooks/useApiResource";
import { fetchMyWorkspaceInvitations } from "../../services/api";
import { INVITATIONS_HREF } from "../../utils/invitations";
import { workspaceRoleMeta } from "../../utils/status";
import styles from "./Workspace.module.css";

/**
 * Workspaces someone else owns that this account joined (audit FUNC-01), and a way to any waiting
 * invitation. Below the page's own list, so it never moves that list; nothing at all when there is
 * neither, or when the answer does not come: the page's own list is what matters here.
 */
export function SharedWorkspaces() {
  const { data } = useApiResource("workspace-invitations:mine", (signal) => fetchMyWorkspaceInvitations(signal));
  const shared = data?.shared_workspaces ?? [];
  const waiting = data?.invitations?.length ?? 0;
  if (shared.length === 0 && waiting === 0) return null;
  return (
    <section className={styles.shared} aria-labelledby="workspace-shared">
      <h2 id="workspace-shared" className={styles.sharedTitle}>
        Shared with you
      </h2>
      {waiting > 0 && (
        <p className={styles.sharedNote}>
          <Link href={INVITATIONS_HREF}>{waiting === 1 ? "1 invitation is waiting for your answer." : `${waiting} invitations are waiting for your answer.`}</Link>
        </p>
      )}
      {shared.length > 0 && (
        <ul className={styles.sharedList}>
          {shared.map((workspace) => (
            <li key={workspace.workspace_id}>
              <Link href={`/workspace/${workspace.workspace_id}`}>{workspace.workspace_title ?? "A research workspace"}</Link>
              <span className={styles.sharedNote}>
                {" "}
                · {workspaceRoleMeta(workspace.role).label}
                {workspace.owner_name ? `, with ${workspace.owner_name}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
