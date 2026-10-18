"use client";

import { useRef, useState, type FormEvent } from "react";
import { Trash2, UserPlus } from "lucide-react";
import { useApiResource, type ApiResource } from "../../../hooks/useApiResource";
import { createWorkspaceInvitation, getWorkspaceInvitations, removeWorkspaceMember, revokeWorkspaceInvitation, updateWorkspaceMemberRole } from "../../../services/api";
import type { WorkspaceInvitation, WorkspaceMember, WorkspaceMemberListResponse, WorkspaceRole } from "../../../types/collaboration";
import { invitationStatusMeta, workspaceRoleMeta } from "../../../utils/status";
import { StatusBadge } from "../../ui/Badge/Badge";
import { Button, IconButton } from "../../ui/Button/Button";
import { Dialog } from "../../ui/Dialog/Dialog";
import { Select, TextInput } from "../../ui/Field/Field";
import { Alert, EmptyState, ErrorState, SkeletonList } from "../../ui/State/State";
import { actionError, shortDate, type Abilities } from "../workflow";
import { useKept } from "./useWorkspaceItem";
import styles from "./Item.module.css";

const INVITE_ROLES: WorkspaceRole[] = ["CONTRIBUTOR", "EDITOR", "VIEWER"];
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface MembersPanelProps {
  workspaceId: string;
  can: Abilities;
  userId: string | null;
  members: ApiResource<WorkspaceMemberListResponse>;
  onChanged: () => void;
}

type Confirm = { kind: "remove"; member: WorkspaceMember } | { kind: "revoke"; invitation: WorkspaceInvitation };

const memberName = (member: WorkspaceMember) => member.user?.full_name || member.user?.email || "A member";

/**
 * Members and invitations. Everyone on the item sees who is on it; only the owner invites,
 * changes roles, removes members and withdraws invitations (backend: OWNER only), each removal
 * after a confirmation that names the person and what they lose.
 */
export function MembersPanel({ workspaceId, can, userId, members, onChanged }: MembersPanelProps) {
  const invitations = useApiResource(`workspace:${workspaceId}:invitations`, (signal) => getWorkspaceInvitations(workspaceId, undefined, undefined, signal));
  const shownMembers = useKept(members);
  const shownInvitations = useKept(invitations);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [inviting, setInviting] = useState(false);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<WorkspaceRole>("CONTRIBUTOR");
  const [emailError, setEmailError] = useState<string | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState<{ email: string; token: string } | null>(null);
  const submitting = useRef(false);
  const emailRef = useRef<HTMLInputElement>(null);

  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  const changeRole = async (member: WorkspaceMember, next: WorkspaceRole) => {
    setBusy(member.id);
    setError(null);
    try {
      await updateWorkspaceMemberRole(workspaceId, member.id, { role: next });
      setMessage(`${memberName(member)} is now ${workspaceRoleMeta(next).label.toLowerCase()}.`);
      members.retry();
      onChanged();
    } catch (err) {
      setError(actionError(err, `The role of ${memberName(member)} could not be changed.`));
    } finally {
      setBusy(null);
    }
  };

  const confirmAction = async () => {
    if (!confirm) return;
    const id = confirm.kind === "remove" ? confirm.member.id : confirm.invitation.id;
    setBusy(id);
    setConfirmError(null);
    try {
      if (confirm.kind === "remove") {
        await removeWorkspaceMember(workspaceId, confirm.member.id);
        setMessage(`Removed ${memberName(confirm.member)}.`);
        members.retry();
      } else {
        await revokeWorkspaceInvitation(workspaceId, confirm.invitation.id);
        setMessage(`Withdrew the invitation to ${confirm.invitation.invitee_email}.`);
        invitations.retry();
      }
      setConfirm(null);
      onChanged();
    } catch (err) {
      setConfirmError(actionError(err, confirm.kind === "remove" ? "The member could not be removed." : "The invitation could not be withdrawn."));
    } finally {
      setBusy(null);
    }
  };

  const invite = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting.current) return;
    const address = email.trim();
    if (!EMAIL.test(address)) {
      setEmailError(address ? "Enter an email address like name@university.edu." : "Enter their email address.");
      emailRef.current?.focus();
      return;
    }
    submitting.current = true;
    setSending(true);
    setEmailError(null);
    setInviteError(null);
    try {
      const created = await createWorkspaceInvitation(workspaceId, { invitee_email: address, role });
      setSent({ email: created.invitation.invitee_email, token: created.token });
      setEmail("");
      setMessage(`Invitation sent to ${created.invitation.invitee_email}.`);
      invitations.retry();
      onChanged();
    } catch (err) {
      setInviteError(actionError(err, "The invitation could not be sent."));
    } finally {
      submitting.current = false;
      setSending(false);
    }
  };

  const openInvite = () => {
    setSent(null);
    setInviteError(null);
    setEmailError(null);
    setInviting(true);
  };

  const memberList = shownMembers?.items ?? [];
  const invitationList = shownInvitations?.items ?? [];

  return (
    <div className={styles.stack}>
      <p role="status" className="rc-visually-hidden">
        {message}
      </p>
      {error && (
        <Alert tone="danger" announce>
          {error}
        </Alert>
      )}

      <section className={styles.section} aria-labelledby="item-members-heading">
        <div className={styles.sectionHead}>
          <h2 id="item-members-heading" className={styles.sectionTitle}>
            Members
          </h2>
          {can.manage && (
            <Button leadingIcon={<UserPlus size={16} aria-hidden="true" />} onClick={openInvite}>
              Invite someone
            </Button>
          )}
        </div>
        {shownMembers === undefined ? (
          members.status === "error" ? (
            <ErrorState title="The members could not be loaded" kind={members.error?.kind === "network" ? "offline" : "failed"} onRetry={members.retry} />
          ) : (
            <SkeletonList rows={2} label="Loading members" />
          )
        ) : memberList.length === 0 ? (
          <EmptyState title="Only you work on this call." description={can.manage ? "Invite co-authors to share its tasks, submission and notes." : undefined} />
        ) : (
          <ul className={styles.list}>
            {memberList.map((member) => {
              const isYou = member.user_id === userId;
              const joined = shortDate(member.joined_at || member.created_at);
              const editable = can.manage && member.role !== "OWNER" && !isYou;
              return (
                <li key={member.id} className={styles.row}>
                  <div className={styles.rowMain}>
                    <h3 className={styles.rowTitle}>
                      {memberName(member)}
                      {isYou && " (you)"}
                    </h3>
                    <p className={styles.meta}>
                      {member.user?.email && member.user.full_name && <span>{member.user.email}</span>}
                      {!editable && <span>{workspaceRoleMeta(member.role).label}</span>}
                      {joined && <span>Joined {joined}</span>}
                    </p>
                  </div>
                  {editable && (
                    <div className={styles.rowActions}>
                      <Select
                        label={`Role of ${memberName(member)}`}
                        value={member.role}
                        disabled={busy === member.id}
                        onChange={(event) => void changeRole(member, event.target.value as WorkspaceRole)}
                      >
                        {INVITE_ROLES.map((value) => (
                          <option key={value} value={value}>
                            {workspaceRoleMeta(value).label}
                          </option>
                        ))}
                      </Select>
                      <IconButton
                        variant="ghost"
                        label={`Remove ${memberName(member)}`}
                        icon={<Trash2 size={16} aria-hidden="true" />}
                        disabled={busy === member.id}
                        onClick={() => {
                          setConfirmError(null);
                          setConfirm({ kind: "remove", member });
                        }}
                      />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className={styles.section} aria-labelledby="item-invitations-heading">
        <h2 id="item-invitations-heading" className={styles.sectionTitle}>
          Invitations
        </h2>
        {shownInvitations === undefined ? (
          invitations.status === "error" ? (
            <ErrorState title="The invitations could not be loaded" kind={invitations.error?.kind === "network" ? "offline" : "failed"} onRetry={invitations.retry} />
          ) : (
            <SkeletonList rows={1} label="Loading invitations" />
          )
        ) : invitationList.length === 0 ? (
          <p className={styles.text}>No invitations sent.</p>
        ) : (
          <ul className={styles.list}>
            {invitationList.map((invitation) => {
              const expires = shortDate(invitation.expires_at);
              return (
                <li key={invitation.id} className={styles.row}>
                  <div className={styles.rowMain}>
                    <h3 className={styles.rowTitle}>{invitation.invitee_email}</h3>
                    <p className={styles.meta}>
                      <StatusBadge meta={invitationStatusMeta(invitation.status)} />
                      <span>As {workspaceRoleMeta(invitation.role).label.toLowerCase()}</span>
                      {invitation.inviter_name && <span>Sent by {invitation.inviter_name}</span>}
                      {invitation.status === "PENDING" && expires && <span>Expires {expires}</span>}
                    </p>
                  </div>
                  {can.manage && invitation.status === "PENDING" && (
                    <div className={styles.rowActions}>
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={busy === invitation.id}
                        onClick={() => {
                          setConfirmError(null);
                          setConfirm({ kind: "revoke", invitation });
                        }}
                      >
                        Withdraw<span className="rc-visually-hidden"> the invitation to {invitation.invitee_email}</span>
                      </Button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <Dialog
        open={inviting}
        onClose={() => setInviting(false)}
        title="Invite someone to this call"
        description="If they have an account here, they get a notification and join when they accept."
        initialFocusRef={emailRef}
        footer={
          <>
            <Button variant="secondary" onClick={() => setInviting(false)}>
              {sent ? "Done" : "Cancel"}
            </Button>
            <Button type="submit" form="item-invite-form" loading={sending}>
              Send invitation
            </Button>
          </>
        }
      >
        <form id="item-invite-form" className={styles.form} onSubmit={invite} noValidate>
          {sent && (
            <Alert tone="success" announce title={`Invitation sent to ${sent.email}.`}>
              If they have an account, they can accept it from their notifications. Its code, if they need it: <span className={styles.code}>{sent.token}</span>
            </Alert>
          )}
          {inviteError && (
            <Alert tone="danger" announce>
              {inviteError}
            </Alert>
          )}
          <TextInput
            ref={emailRef}
            label="Email address"
            type="email"
            autoComplete="off"
            required
            maxLength={255}
            value={email}
            error={emailError}
            onChange={(event) => {
              setEmail(event.target.value);
              if (emailError) setEmailError(null);
            }}
          />
          <Select label="Role" value={role} onChange={(event) => setRole(event.target.value as WorkspaceRole)} hint={workspaceRoleMeta(role).description}>
            {INVITE_ROLES.map((value) => (
              <option key={value} value={value}>
                {workspaceRoleMeta(value).label}
              </option>
            ))}
          </Select>
        </form>
      </Dialog>

      <Dialog
        open={confirm !== null}
        onClose={() => setConfirm(null)}
        size="sm"
        title={
          confirm?.kind === "remove" ? `Remove ${memberName(confirm.member)} from this call?` : confirm ? `Withdraw the invitation to ${confirm.invitation.invitee_email}?` : ""
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirm(null)}>
              Cancel
            </Button>
            <Button variant="danger" loading={busy !== null} onClick={() => void confirmAction()}>
              {confirm?.kind === "remove" ? "Remove" : "Withdraw"}
            </Button>
          </>
        }
      >
        <p>
          {confirm?.kind === "remove"
            ? "They lose access to its tasks, submission, documents and activity. You can invite them again later."
            : "The invitation stops working. You can send a new one later."}
        </p>
        {confirmError && (
          <Alert tone="danger" announce>
            {confirmError}
          </Alert>
        )}
      </Dialog>
    </div>
  );
}
