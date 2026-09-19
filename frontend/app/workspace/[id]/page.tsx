"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import "@/styles/collaboration.css";
import type { WorkspaceItem } from "@/types/workspace";
import type {
  ActivityType,
  InvitationStatus,
  TaskPriority,
  TaskStatus,
  WorkspaceActivity,
  WorkspaceInvitation,
  WorkspaceMember,
  WorkspaceRole,
  WorkspaceTask,
} from "@/types/collaboration";
import {
  acceptWorkspaceInvitation,
  addWorkspaceComment,
  completeWorkspaceTask,
  createWorkspaceInvitation,
  createWorkspaceTask,
  deleteWorkspaceTask,
  fetchWorkspaceItems,
  getWorkspaceActivity,
  getWorkspaceInvitations,
  getWorkspaceMembers,
  getWorkspaceTasks,
  removeWorkspaceMember,
  reopenWorkspaceTask,
  revokeWorkspaceInvitation,
  updateWorkspaceMemberRole,
} from "@/services/api";
import {
  AlertCircle,
  ArrowLeft,
  Calendar,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  FileText,
  Layers,
  ListChecks,
  Loader2,
  Mail,
  MessageSquare,
  Plus,
  RefreshCw,
  Send,
  Shield,
  Trash2,
  UserCheck,
  UserPlus,
  Users,
  X,
} from "lucide-react";

interface PageProps {
  params: Promise<{ id: string }>;
}

type TabKey = "overview" | "tasks" | "members" | "invitations" | "activity";

export default function WorkspaceCollaborationPage({ params }: PageProps) {
  const { id: workspaceId } = React.use(params);

  const [workspaceItem, setWorkspaceItem] = useState<WorkspaceItem | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Collaboration State
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [invitations, setInvitations] = useState<WorkspaceInvitation[]>([]);
  const [tasks, setTasks] = useState<WorkspaceTask[]>([]);
  const [activities, setActivities] = useState<WorkspaceActivity[]>([]);

  // Task Filters
  const [taskStatusFilter, setTaskStatusFilter] = useState<string>("");
  const [taskPriorityFilter, setTaskPriorityFilter] = useState<string>("");

  // Modals & Forms
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<WorkspaceRole>("CONTRIBUTOR");
  const [isInviting, setIsInviting] = useState(false);
  const [createdInviteToken, setCreatedInviteToken] = useState<string | null>(null);

  const [showTaskModal, setShowTaskModal] = useState(false);
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDesc, setTaskDesc] = useState("");
  const [taskAssignee, setTaskAssignee] = useState<string>("");
  const [taskPriority, setTaskPriority] = useState<TaskPriority>("MEDIUM");
  const [taskDueDate, setTaskDueDate] = useState("");
  const [isCreatingTask, setIsCreatingTask] = useState(false);

  // Comment Form
  const [commentText, setCommentText] = useState("");
  const [isPostingComment, setIsPostingComment] = useState(false);

  // Load initial workspace data
  const loadWorkspace = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const wsRes = await fetchWorkspaceItems({ limit: 100, include_archived: true });
      const current = wsRes.items.find((it: WorkspaceItem) => it.id === workspaceId) || null;
      setWorkspaceItem(current);

      const [mRes, iRes, tRes, aRes] = await Promise.all([
        getWorkspaceMembers(workspaceId),
        getWorkspaceInvitations(workspaceId),
        getWorkspaceTasks(workspaceId),
        getWorkspaceActivity(workspaceId),
      ]);

      setMembers(mRes.items);
      setInvitations(iRes.items);
      setTasks(tRes.items);
      setActivities(aRes.items);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to load workspace data";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  // Refresh sub-data for tabs
  const refreshTasks = async () => {
    try {
      const tRes = await getWorkspaceTasks(workspaceId, {
        status: (taskStatusFilter as TaskStatus) || undefined,
        priority: (taskPriorityFilter as TaskPriority) || undefined,
      });
      setTasks(tRes.items);
    } catch (err: unknown) {
      console.error("Failed to refresh tasks:", err);
    }
  };

  const refreshMembersAndInvites = async () => {
    try {
      const [mRes, iRes] = await Promise.all([
        getWorkspaceMembers(workspaceId),
        getWorkspaceInvitations(workspaceId),
      ]);
      setMembers(mRes.items);
      setInvitations(iRes.items);
    } catch (err: unknown) {
      console.error("Failed to refresh members/invitations:", err);
    }
  };

  const refreshActivity = async () => {
    try {
      const aRes = await getWorkspaceActivity(workspaceId);
      setActivities(aRes.items);
    } catch (err: unknown) {
      console.error("Failed to refresh activity:", err);
    }
  };

  // ── Handlers ──

  const handleCreateInvitation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setIsInviting(true);
    setError(null);
    try {
      const res = await createWorkspaceInvitation(workspaceId, {
        invitee_email: inviteEmail.trim(),
        role: inviteRole,
      });
      setCreatedInviteToken(res.token);
      setActionSuccess(`Invitation sent to ${res.invitation.invitee_email}`);
      await refreshMembersAndInvites();
      await refreshActivity();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create invitation");
    } finally {
      setIsInviting(false);
    }
  };

  const handleRevokeInvitation = async (invId: string) => {
    if (!confirm("Are you sure you want to revoke this invitation?")) return;
    try {
      await revokeWorkspaceInvitation(workspaceId, invId);
      setActionSuccess("Invitation revoked");
      await refreshMembersAndInvites();
      await refreshActivity();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to revoke invitation");
    }
  };

  const handleRoleChange = async (memberId: string, newRole: WorkspaceRole) => {
    try {
      await updateWorkspaceMemberRole(workspaceId, memberId, { role: newRole });
      setActionSuccess("Member role updated");
      await refreshMembersAndInvites();
      await refreshActivity();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to update member role");
    }
  };

  const handleRemoveMember = async (memberId: string) => {
    if (!confirm("Are you sure you want to remove this member from the workspace?")) return;
    try {
      await removeWorkspaceMember(workspaceId, memberId);
      setActionSuccess("Member removed from workspace");
      await refreshMembersAndInvites();
      await refreshActivity();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to remove member");
    }
  };

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!taskTitle.trim()) return;
    setIsCreatingTask(true);
    setError(null);
    try {
      await createWorkspaceTask(workspaceId, {
        title: taskTitle.trim(),
        description: taskDesc.trim() || undefined,
        assignee_id: taskAssignee || undefined,
        priority: taskPriority,
        due_at: taskDueDate ? new Date(taskDueDate).toISOString() : undefined,
      });
      setShowTaskModal(false);
      setTaskTitle("");
      setTaskDesc("");
      setTaskAssignee("");
      setTaskDueDate("");
      setActionSuccess("Task created successfully");
      await refreshTasks();
      await refreshActivity();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create task");
    } finally {
      setIsCreatingTask(false);
    }
  };

  const handleToggleTaskStatus = async (task: WorkspaceTask) => {
    try {
      if (task.status === "COMPLETED") {
        await reopenWorkspaceTask(workspaceId, task.id);
        setActionSuccess(`Task reopened: ${task.title}`);
      } else {
        await completeWorkspaceTask(workspaceId, task.id);
        setActionSuccess(`Task completed: ${task.title}`);
      }
      await refreshTasks();
      await refreshActivity();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to update task status");
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    if (!confirm("Are you sure you want to delete this task?")) return;
    try {
      await deleteWorkspaceTask(workspaceId, taskId);
      setActionSuccess("Task deleted");
      await refreshTasks();
      await refreshActivity();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to delete task");
    }
  };

  const handlePostComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!commentText.trim()) return;
    setIsPostingComment(true);
    setError(null);
    try {
      await addWorkspaceComment(workspaceId, {
        comment: commentText.trim(),
      });
      setCommentText("");
      setActionSuccess("Note posted to activity feed");
      await refreshActivity();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to post comment");
    } finally {
      setIsPostingComment(false);
    }
  };

  if (loading) {
    return (
      <div className="collab-container" style={{ textAlign: "center", paddingTop: 80 }}>
        <Loader2 className="animate-spin" size={36} style={{ margin: "0 auto 16px" }} />
        <p style={{ color: "var(--text-muted)" }}>Loading workspace collaboration...</p>
      </div>
    );
  }

  return (
    <div className="collab-container">
      {/* Back Link */}
      <Link href="/workspace" className="collab-back-link">
        <ArrowLeft size={16} />
        Back to Workspace Opportunities
      </Link>

      {/* Notifications / Alerts */}
      {error && (
        <div style={{ background: "#fee2e2", color: "#991b1b", padding: "12px 16px", borderRadius: 8, marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} style={{ background: "transparent", border: "none", cursor: "pointer", color: "inherit" }}><X size={16} /></button>
        </div>
      )}

      {actionSuccess && (
        <div style={{ background: "#dcfce7", color: "#166534", padding: "12px 16px", borderRadius: 8, marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <CheckCircle2 size={18} />
            <span>{actionSuccess}</span>
          </div>
          <button onClick={() => setActionSuccess(null)} style={{ background: "transparent", border: "none", cursor: "pointer", color: "inherit" }}><X size={16} /></button>
        </div>
      )}

      {/* Header */}
      <div className="collab-header">
        <div className="collab-header-top">
          <div>
            <h1 className="collab-title">
              {workspaceItem?.opportunity?.title || "Research Workspace"}
            </h1>
            <div className="collab-meta-row">
              {workspaceItem?.opportunity?.publisher && (
                <span className="collab-meta-item">
                  <Shield size={14} />
                  {workspaceItem.opportunity.publisher}
                </span>
              )}
              {workspaceItem?.opportunity?.submission_deadline && (
                <span className="collab-meta-item">
                  <Calendar size={14} />
                  Deadline: {new Date(workspaceItem.opportunity.submission_deadline).toLocaleDateString()}
                </span>
              )}
              <span className={`status-badge ${(workspaceItem?.status || "").toLowerCase()}`}>
                {workspaceItem?.status || "SAVED"}
              </span>
              <span className={`priority-badge ${(workspaceItem?.priority || "").toLowerCase()}`}>
                {workspaceItem?.priority || "MEDIUM"}
              </span>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Link
              href={`/workspace/${workspaceId}/submission`}
              className="collab-btn collab-btn-primary"
            >
              <FileText size={14} />
              Submission Workflow
              <ExternalLink size={12} />
            </Link>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="collab-tabs">
        <button
          className={`collab-tab-btn ${activeTab === "overview" ? "active" : ""}`}
          onClick={() => setActiveTab("overview")}
        >
          <Layers size={16} />
          Overview
        </button>
        <button
          className={`collab-tab-btn ${activeTab === "tasks" ? "active" : ""}`}
          onClick={() => setActiveTab("tasks")}
        >
          <ListChecks size={16} />
          Tasks
          <span className="collab-tab-badge">{tasks.length}</span>
        </button>
        <button
          className={`collab-tab-btn ${activeTab === "members" ? "active" : ""}`}
          onClick={() => setActiveTab("members")}
        >
          <Users size={16} />
          Members
          <span className="collab-tab-badge">{members.length}</span>
        </button>
        <button
          className={`collab-tab-btn ${activeTab === "invitations" ? "active" : ""}`}
          onClick={() => setActiveTab("invitations")}
        >
          <UserPlus size={16} />
          Invitations
          {invitations.filter((i) => i.status === "PENDING").length > 0 && (
            <span className="collab-tab-badge">
              {invitations.filter((i) => i.status === "PENDING").length}
            </span>
          )}
        </button>
        <button
          className={`collab-tab-btn ${activeTab === "activity" ? "active" : ""}`}
          onClick={() => setActiveTab("activity")}
        >
          <MessageSquare size={16} />
          Activity & Notes
          <span className="collab-tab-badge">{activities.length}</span>
        </button>
      </div>

      {/* ── Tab Panels ── */}

      {/* TAB 1: OVERVIEW */}
      {activeTab === "overview" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="collab-card">
            <div className="collab-card-header">
              <h3 className="collab-card-title">
                <Shield size={18} />
                Opportunity Summary
              </h3>
            </div>
            <p style={{ fontSize: 14, color: "var(--text-main)", lineHeight: 1.6 }}>
              {workspaceItem?.opportunity?.delivery_mode && (
                <span><strong>Delivery Mode:</strong> {workspaceItem.opportunity.delivery_mode} &bull; </span>
              )}
              {workspaceItem?.opportunity?.location && (
                <span><strong>Location:</strong> {workspaceItem.opportunity.location} &bull; </span>
              )}
              {workspaceItem?.opportunity?.opportunity_type && (
                <span><strong>Type:</strong> {workspaceItem.opportunity.opportunity_type}</span>
              )}
            </p>
            {workspaceItem?.notes && (
              <div style={{ marginTop: 16, padding: 12, background: "var(--bg-hover, #f9fafb)", borderRadius: 6, border: "1px solid var(--border-color)" }}>
                <strong style={{ fontSize: 12, textTransform: "uppercase", color: "var(--text-muted)" }}>Workspace Notes:</strong>
                <p style={{ margin: "4px 0 0 0", fontSize: 13 }}>{workspaceItem.notes}</p>
              </div>
            )}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
            <div className="collab-card" style={{ marginBottom: 0 }}>
              <h4 style={{ margin: "0 0 8px 0", fontSize: 13, color: "var(--text-muted)" }}>Team Members</h4>
              <div style={{ fontSize: 24, fontWeight: 700, color: "var(--text-main)" }}>{members.length}</div>
              <p style={{ margin: "4px 0 0 0", fontSize: 12, color: "var(--text-muted)" }}>Collaborators active</p>
            </div>
            <div className="collab-card" style={{ marginBottom: 0 }}>
              <h4 style={{ margin: "0 0 8px 0", fontSize: 13, color: "var(--text-muted)" }}>Open Tasks</h4>
              <div style={{ fontSize: 24, fontWeight: 700, color: "var(--color-primary)" }}>
                {tasks.filter((t) => t.status !== "COMPLETED" && t.status !== "CANCELLED").length}
              </div>
              <p style={{ margin: "4px 0 0 0", fontSize: 12, color: "var(--text-muted)" }}>Of {tasks.length} total tasks</p>
            </div>
            <div className="collab-card" style={{ marginBottom: 0 }}>
              <h4 style={{ margin: "0 0 8px 0", fontSize: 13, color: "var(--text-muted)" }}>Pending Invitations</h4>
              <div style={{ fontSize: 24, fontWeight: 700, color: "#d97706" }}>
                {invitations.filter((i) => i.status === "PENDING").length}
              </div>
              <p style={{ margin: "4px 0 0 0", fontSize: 12, color: "var(--text-muted)" }}>Awaiting response</p>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: TASKS */}
      {activeTab === "tasks" && (
        <div className="collab-card">
          <div className="collab-card-header">
            <h3 className="collab-card-title">
              <ListChecks size={18} />
              Collaborative Tasks
            </h3>
            <button
              className="collab-btn collab-btn-primary"
              onClick={() => setShowTaskModal(true)}
            >
              <Plus size={14} />
              Create Task
            </button>
          </div>

          <div className="tasks-toolbar">
            <div className="task-filters">
              <select
                className="collab-select"
                value={taskStatusFilter}
                onChange={(e) => setTaskStatusFilter(e.target.value)}
              >
                <option value="">All Statuses</option>
                <option value="TODO">To Do</option>
                <option value="IN_PROGRESS">In Progress</option>
                <option value="IN_REVIEW">In Review</option>
                <option value="COMPLETED">Completed</option>
                <option value="CANCELLED">Cancelled</option>
              </select>

              <select
                className="collab-select"
                value={taskPriorityFilter}
                onChange={(e) => setTaskPriorityFilter(e.target.value)}
              >
                <option value="">All Priorities</option>
                <option value="LOW">Low</option>
                <option value="MEDIUM">Medium</option>
                <option value="HIGH">High</option>
                <option value="URGENT">Urgent</option>
              </select>

              <button
                className="collab-btn collab-btn-outline collab-btn-sm"
                onClick={refreshTasks}
              >
                <RefreshCw size={12} />
                Filter
              </button>
            </div>
          </div>

          {tasks.length === 0 ? (
            <div className="collab-empty-state">
              <ListChecks size={36} style={{ margin: "0 auto 12px", opacity: 0.4 }} />
              <p>No tasks created yet for this research workspace.</p>
              <button
                className="collab-btn collab-btn-outline collab-btn-sm"
                onClick={() => setShowTaskModal(true)}
              >
                Create the first task
              </button>
            </div>
          ) : (
            <div className="tasks-list">
              {tasks.map((task) => (
                <div
                  key={task.id}
                  className={`task-item ${task.status === "COMPLETED" ? "completed" : ""}`}
                >
                  <div className="task-main">
                    <input
                      type="checkbox"
                      className="task-checkbox"
                      checked={task.status === "COMPLETED"}
                      onChange={() => handleToggleTaskStatus(task)}
                    />
                    <div className="task-info">
                      <div className="task-title-row" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span className={`task-title ${task.status === "COMPLETED" ? "completed" : ""}`}>
                          {task.title}
                        </span>
                        <span className={`status-badge ${task.status.toLowerCase()}`}>
                          {task.status.replace("_", " ")}
                        </span>
                        <span className={`priority-badge ${task.priority.toLowerCase()}`}>
                          {task.priority}
                        </span>
                      </div>
                      {task.description && (
                        <p className="task-desc">{task.description}</p>
                      )}
                      <div className="task-meta">
                        {task.assignee_name && (
                          <span>Assigned: <strong>{task.assignee_name}</strong></span>
                        )}
                        {task.due_at && (
                          <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                            <Clock size={11} />
                            Due: {new Date(task.due_at).toLocaleDateString()}
                          </span>
                        )}
                        <span>Created by: {task.creator_name || "Owner"}</span>
                      </div>
                    </div>
                  </div>
                  <div className="task-actions">
                    <button
                      className="collab-btn collab-btn-danger collab-btn-sm"
                      onClick={() => handleDeleteTask(task.id)}
                      title="Delete task"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: MEMBERS */}
      {activeTab === "members" && (
        <div className="collab-card">
          <div className="collab-card-header">
            <h3 className="collab-card-title">
              <Users size={18} />
              Workspace Members
            </h3>
            <button
              className="collab-btn collab-btn-primary"
              onClick={() => setShowInviteModal(true)}
            >
              <UserPlus size={14} />
              Invite Member
            </button>
          </div>

          <div className="members-grid">
            {members.map((member) => (
              <div key={member.id} className="member-card">
                <div className="member-card-top">
                  <div className="member-avatar">
                    {(member.user?.full_name || "M").charAt(0).toUpperCase()}
                  </div>
                  <div className="member-details">
                    <h4 className="member-name">{member.user?.full_name || "Researcher"}</h4>
                    <p className="member-email">{member.user?.email || "Email undisclosed"}</p>
                  </div>
                  <span className={`role-badge ${member.role.toLowerCase()}`}>
                    {member.role}
                  </span>
                </div>
                <div className="member-actions">
                  <span style={{ color: "var(--text-muted)" }}>
                    Joined: {new Date(member.joined_at || member.created_at).toLocaleDateString()}
                  </span>
                  {member.role !== "OWNER" && (
                    <div style={{ display: "flex", gap: 6 }}>
                      <select
                        className="collab-select"
                        style={{ padding: "2px 6px", fontSize: 11 }}
                        value={member.role}
                        onChange={(e) => handleRoleChange(member.id, e.target.value as WorkspaceRole)}
                      >
                        <option value="EDITOR">Editor</option>
                        <option value="CONTRIBUTOR">Contributor</option>
                        <option value="VIEWER">Viewer</option>
                      </select>
                      <button
                        className="collab-btn collab-btn-danger collab-btn-sm"
                        onClick={() => handleRemoveMember(member.id)}
                        title="Remove member"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 4: INVITATIONS */}
      {activeTab === "invitations" && (
        <div className="collab-card">
          <div className="collab-card-header">
            <h3 className="collab-card-title">
              <Mail size={18} />
              Invitations & Access
            </h3>
            <button
              className="collab-btn collab-btn-primary"
              onClick={() => setShowInviteModal(true)}
            >
              <Plus size={14} />
              Create Invitation
            </button>
          </div>

          {invitations.length === 0 ? (
            <div className="collab-empty-state">
              <Mail size={36} style={{ margin: "0 auto 12px", opacity: 0.4 }} />
              <p>No invitations created yet for this research workspace.</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {invitations.map((inv) => (
                <div
                  key={inv.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "12px 16px",
                    background: "var(--bg-hover, #fafafa)",
                    border: "1px solid var(--border-color)",
                    borderRadius: 8,
                  }}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <strong style={{ fontSize: 14 }}>{inv.invitee_email}</strong>
                      <span className={`role-badge ${inv.role.toLowerCase()}`}>{inv.role}</span>
                      <span className={`status-badge ${inv.status.toLowerCase()}`}>{inv.status}</span>
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", gap: 12 }}>
                      <span>Invited by: {inv.inviter_name || "Owner"}</span>
                      <span>Expires: {new Date(inv.expires_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                  <div>
                    {inv.status === "PENDING" && (
                      <button
                        className="collab-btn collab-btn-danger collab-btn-sm"
                        onClick={() => handleRevokeInvitation(inv.id)}
                      >
                        Revoke
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 5: ACTIVITY & NOTES */}
      {activeTab === "activity" && (
        <div className="collab-card">
          <div className="collab-card-header">
            <h3 className="collab-card-title">
              <MessageSquare size={18} />
              Collaboration Activity & Notes
            </h3>
          </div>

          {/* Post Comment Form */}
          <form onSubmit={handlePostComment} className="comment-form">
            <textarea
              className="comment-textarea"
              placeholder="Post a collaborative note or update for the team..."
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              disabled={isPostingComment}
            />
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                type="submit"
                className="collab-btn collab-btn-primary"
                disabled={isPostingComment || !commentText.trim()}
              >
                {isPostingComment ? <Loader2 className="animate-spin" size={14} /> : <Send size={14} />}
                Post Note
              </button>
            </div>
          </form>

          {/* Activity Feed */}
          {activities.length === 0 ? (
            <div className="collab-empty-state">
              <MessageSquare size={36} style={{ margin: "0 auto 12px", opacity: 0.4 }} />
              <p>No activity recorded yet for this workspace.</p>
            </div>
          ) : (
            <div className="activity-feed">
              {activities.map((act) => (
                <div key={act.id} className="activity-item">
                  <div className="activity-dot">
                    {act.activity_type.includes("TASK") ? (
                      <ListChecks size={12} />
                    ) : act.activity_type.includes("MEMBER") ? (
                      <UserCheck size={12} />
                    ) : (
                      <MessageSquare size={12} />
                    )}
                  </div>
                  <div className="activity-header">
                    <span className="activity-actor">{act.actor_name || "Collaborator"}</span>
                    <span> &bull; {act.description}</span>
                    <span className="activity-time">
                      {new Date(act.created_at).toLocaleString()}
                    </span>
                  </div>
                  {act.comment && (
                    <div className="activity-comment-box">
                      {act.comment}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── MODALS ── */}

      {/* Invite Modal */}
      {showInviteModal && (
        <div className="collab-modal-backdrop">
          <div className="collab-modal">
            <div className="collab-modal-header">
              <h3 className="collab-modal-title">Invite Collaborator</h3>
              <button onClick={() => setShowInviteModal(false)} style={{ background: "transparent", border: "none", cursor: "pointer" }}>
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleCreateInvitation}>
              <div className="collab-modal-body">
                <div className="collab-form-group">
                  <label className="collab-label">Invitee Email Address</label>
                  <input
                    type="email"
                    className="collab-input"
                    placeholder="researcher@university.edu"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    required
                  />
                </div>
                <div className="collab-form-group">
                  <label className="collab-label">Role & Permissions</label>
                  <select
                    className="collab-select"
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value as WorkspaceRole)}
                  >
                    <option value="CONTRIBUTOR">Contributor (Tasks, Docs, Notes)</option>
                    <option value="EDITOR">Editor (Manage Submissions & Documents)</option>
                    <option value="VIEWER">Viewer (Read-only access)</option>
                  </select>
                </div>

                {createdInviteToken && (
                  <div style={{ padding: 12, background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 6 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "#166534", marginBottom: 4 }}>
                      Invitation Generated Successfully!
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", wordBreak: "break-all" }}>
                      Token: <code>{createdInviteToken}</code>
                    </div>
                  </div>
                )}
              </div>
              <div className="collab-modal-footer">
                <button
                  type="button"
                  className="collab-btn collab-btn-outline"
                  onClick={() => setShowInviteModal(false)}
                >
                  Close
                </button>
                <button
                  type="submit"
                  className="collab-btn collab-btn-primary"
                  disabled={isInviting || !inviteEmail.trim()}
                >
                  {isInviting ? <Loader2 className="animate-spin" size={14} /> : <Mail size={14} />}
                  Send Invitation
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Create Task Modal */}
      {showTaskModal && (
        <div className="collab-modal-backdrop">
          <div className="collab-modal">
            <div className="collab-modal-header">
              <h3 className="collab-modal-title">Create Workspace Task</h3>
              <button onClick={() => setShowTaskModal(false)} style={{ background: "transparent", border: "none", cursor: "pointer" }}>
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleCreateTask}>
              <div className="collab-modal-body">
                <div className="collab-form-group">
                  <label className="collab-label">Task Title</label>
                  <input
                    type="text"
                    className="collab-input"
                    placeholder="e.g. Draft Introduction Section"
                    value={taskTitle}
                    onChange={(e) => setTaskTitle(e.target.value)}
                    required
                  />
                </div>
                <div className="collab-form-group">
                  <label className="collab-label">Description (Optional)</label>
                  <textarea
                    className="collab-input"
                    placeholder="Add details, instructions, or resources..."
                    value={taskDesc}
                    onChange={(e) => setTaskDesc(e.target.value)}
                    style={{ minHeight: 60 }}
                  />
                </div>
                <div className="collab-form-group">
                  <label className="collab-label">Assignee</label>
                  <select
                    className="collab-select"
                    value={taskAssignee}
                    onChange={(e) => setTaskAssignee(e.target.value)}
                  >
                    <option value="">Unassigned</option>
                    {members.map((m) => (
                      <option key={m.user_id} value={m.user_id}>
                        {m.user?.full_name || m.user?.email || "Member"} ({m.role})
                      </option>
                    ))}
                  </select>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div className="collab-form-group">
                    <label className="collab-label">Priority</label>
                    <select
                      className="collab-select"
                      value={taskPriority}
                      onChange={(e) => setTaskPriority(e.target.value as TaskPriority)}
                    >
                      <option value="LOW">Low</option>
                      <option value="MEDIUM">Medium</option>
                      <option value="HIGH">High</option>
                      <option value="URGENT">Urgent</option>
                    </select>
                  </div>
                  <div className="collab-form-group">
                    <label className="collab-label">Due Date</label>
                    <input
                      type="date"
                      className="collab-input"
                      value={taskDueDate}
                      onChange={(e) => setTaskDueDate(e.target.value)}
                    />
                  </div>
                </div>
              </div>
              <div className="collab-modal-footer">
                <button
                  type="button"
                  className="collab-btn collab-btn-outline"
                  onClick={() => setShowTaskModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="collab-btn collab-btn-primary"
                  disabled={isCreatingTask || !taskTitle.trim()}
                >
                  {isCreatingTask ? <Loader2 className="animate-spin" size={14} /> : <Plus size={14} />}
                  Create Task
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
