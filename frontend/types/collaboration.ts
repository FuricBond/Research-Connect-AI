export type WorkspaceRole = "OWNER" | "EDITOR" | "CONTRIBUTOR" | "VIEWER";

export type MemberStatus = "ACTIVE" | "INVITED" | "REMOVED" | "LEFT";

export type InvitationStatus =
  | "PENDING"
  | "ACCEPTED"
  | "DECLINED"
  | "EXPIRED"
  | "REVOKED";

export type TaskStatus =
  | "TODO"
  | "IN_PROGRESS"
  | "IN_REVIEW"
  | "COMPLETED"
  | "CANCELLED";

export type TaskPriority = "LOW" | "MEDIUM" | "HIGH" | "URGENT";

export type ActivityType =
  | "MEMBER_INVITED"
  | "MEMBER_JOINED"
  | "MEMBER_ROLE_CHANGED"
  | "MEMBER_REMOVED"
  | "TASK_CREATED"
  | "TASK_ASSIGNED"
  | "TASK_COMPLETED"
  | "TASK_REOPENED"
  | "DOCUMENT_UPDATED"
  | "SUBMISSION_UPDATED"
  | "COMMENT_ADDED";

export interface WorkspaceMemberUserSummary {
  id: string;
  email: string;
  full_name: string;
  role: string;
  academic_status?: string | null;
}

export interface WorkspaceMember {
  id: string;
  workspace_id: string;
  user_id: string;
  role: WorkspaceRole;
  status: MemberStatus;
  invited_at?: string | null;
  joined_at?: string | null;
  removed_at?: string | null;
  created_at: string;
  updated_at: string;
  user?: WorkspaceMemberUserSummary | null;
}

export interface WorkspaceMemberAddPayload {
  user_id: string;
  role?: WorkspaceRole;
}

export interface WorkspaceMemberRoleUpdatePayload {
  role: WorkspaceRole;
}

export interface WorkspaceMemberListResponse {
  items: WorkspaceMember[];
  total_count: number;
}

export interface WorkspaceInvitation {
  id: string;
  workspace_id: string;
  inviter_id: string;
  inviter_name?: string | null;
  invitee_email: string;
  invitee_user_id?: string | null;
  role: WorkspaceRole;
  status: InvitationStatus;
  created_at: string;
  expires_at: string;
  accepted_at?: string | null;
  revoked_at?: string | null;
}

export interface WorkspaceInvitationCreatePayload {
  invitee_email: string;
  role?: WorkspaceRole;
}

export interface WorkspaceInvitationCreateResponse {
  invitation: WorkspaceInvitation;
  token: string;
}

export interface WorkspaceInvitationListResponse {
  items: WorkspaceInvitation[];
  total_count: number;
}

export interface WorkspaceTask {
  id: string;
  workspace_id: string;
  title: string;
  description?: string | null;
  creator_id: string;
  creator_name?: string | null;
  assignee_id?: string | null;
  assignee_name?: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_at?: string | null;
  submission_id?: string | null;
  document_id?: string | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface WorkspaceTaskCreatePayload {
  title: string;
  description?: string;
  assignee_id?: string;
  priority?: TaskPriority;
  due_at?: string;
  submission_id?: string;
  document_id?: string;
}

export interface WorkspaceTaskUpdatePayload {
  title?: string;
  description?: string;
  assignee_id?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  due_at?: string;
  submission_id?: string;
  document_id?: string;
}

export interface WorkspaceTaskAssignPayload {
  assignee_id?: string | null;
}

export interface WorkspaceTaskListResponse {
  items: WorkspaceTask[];
  total_count: number;
}

export interface WorkspaceActivity {
  id: string;
  workspace_id: string;
  actor_id: string;
  actor_name?: string | null;
  activity_type: ActivityType;
  target_type?: string | null;
  target_id?: string | null;
  description: string;
  comment?: string | null;
  old_state?: Record<string, unknown> | null;
  new_state?: Record<string, unknown> | null;
  created_at: string;
}

export interface WorkspaceCommentCreatePayload {
  comment: string;
  target_type?: string;
  target_id?: string;
}

export interface WorkspaceActivityListResponse {
  items: WorkspaceActivity[];
  total_count: number;
}

export interface TaskFilterParams {
  assignee_id?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  due_before?: string;
  limit?: number;
  offset?: number;
}
