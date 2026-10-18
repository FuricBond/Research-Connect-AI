"use client";

import { useRef, useState, type FormEvent } from "react";
import { Plus, Trash2 } from "lucide-react";
import { useApiResource, type ApiResource } from "../../../hooks/useApiResource";
import { completeWorkspaceTask, createWorkspaceTask, deleteWorkspaceTask, getWorkspaceTasks, reopenWorkspaceTask } from "../../../services/api";
import type { TaskPriority, TaskStatus, WorkspaceMemberListResponse, WorkspaceTask } from "../../../types/collaboration";
import { taskStatusMeta } from "../../../utils/status";
import { PriorityLabel, StatusBadge } from "../../ui/Badge/Badge";
import { Button, IconButton } from "../../ui/Button/Button";
import { Dialog } from "../../ui/Dialog/Dialog";
import { Select, TextArea, TextInput } from "../../ui/Field/Field";
import { Alert, EmptyState, ErrorState, SkeletonList } from "../../ui/State/State";
import { actionError, shortDate, type Abilities } from "../workflow";
import { useKept } from "./useWorkspaceItem";
import styles from "./Item.module.css";

const STATUSES: TaskStatus[] = ["TODO", "IN_PROGRESS", "IN_REVIEW", "COMPLETED", "CANCELLED"];
const PRIORITIES: { value: TaskPriority; label: string }[] = [
  { value: "LOW", label: "Low" },
  { value: "MEDIUM", label: "Medium" },
  { value: "HIGH", label: "High" },
  { value: "URGENT", label: "Urgent" },
];

interface TasksPanelProps {
  workspaceId: string;
  can: Abilities;
  userId: string | null;
  members: ApiResource<WorkspaceMemberListResponse>;
  onChanged: () => void;
}

interface TaskDraft {
  title: string;
  description: string;
  assignee: string;
  priority: TaskPriority;
  due: string;
}

const EMPTY_DRAFT: TaskDraft = { title: "", description: "", assignee: "", priority: "MEDIUM", due: "" };

/**
 * Tasks: filtered by status and priority (each filter one request), done or reopened with the
 * checkbox, added in a dialog, deleted after a confirmation that names the task. Contributors and
 * up add and tick tasks; a task's creator, editors and the owner delete it (the server decides).
 */
export function TasksPanel({ workspaceId, can, userId, members, onChanged }: TasksPanelProps) {
  const [status, setStatus] = useState<TaskStatus | "">("");
  const [priority, setPriority] = useState<TaskPriority | "">("");
  const tasks = useApiResource(`workspace:${workspaceId}:tasks:${status}:${priority}`, (signal) =>
    getWorkspaceTasks(workspaceId, { status: status || undefined, priority: priority || undefined }, undefined, signal)
  );
  const shown = useKept(tasks);
  const [busy, setBusy] = useState<Set<string>>(() => new Set());
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);

  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<TaskDraft>(EMPTY_DRAFT);
  const [titleError, setTitleError] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const submitting = useRef(false);
  const titleRef = useRef<HTMLInputElement>(null);

  const [deleting, setDeleting] = useState<WorkspaceTask | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const mark = (id: string, on: boolean) =>
    setBusy((current) => {
      const next = new Set(current);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const toggle = async (task: WorkspaceTask) => {
    const done = task.status === "COMPLETED";
    mark(task.id, true);
    setError(null);
    try {
      if (done) await reopenWorkspaceTask(workspaceId, task.id);
      else await completeWorkspaceTask(workspaceId, task.id);
      setMessage(done ? `Reopened ${task.title}.` : `Marked ${task.title} done.`);
      tasks.retry();
      onChanged();
    } catch (err) {
      setError(actionError(err, done ? `${task.title} could not be reopened.` : `${task.title} could not be marked done.`));
    } finally {
      mark(task.id, false);
    }
  };

  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting.current) return;
    const title = draft.title.trim();
    if (!title) {
      setTitleError("Give the task a title.");
      titleRef.current?.focus();
      return;
    }
    submitting.current = true;
    setSaving(true);
    setTitleError(null);
    setCreateError(null);
    try {
      await createWorkspaceTask(workspaceId, {
        title,
        description: draft.description.trim() || undefined,
        assignee_id: draft.assignee || undefined,
        priority: draft.priority,
        due_at: draft.due ? new Date(`${draft.due}T23:59:00`).toISOString() : undefined,
      });
      setCreating(false);
      setDraft(EMPTY_DRAFT);
      setMessage(`Added the task ${title}.`);
      tasks.retry();
      onChanged();
    } catch (err) {
      // What was typed stays, so "Create task" can simply be pressed again.
      setCreateError(actionError(err, "The task could not be created."));
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!deleting) return;
    mark(deleting.id, true);
    setDeleteError(null);
    try {
      await deleteWorkspaceTask(workspaceId, deleting.id);
      setMessage(`Deleted the task ${deleting.title}.`);
      setDeleting(null);
      tasks.retry();
      onChanged();
    } catch (err) {
      setDeleteError(actionError(err, "The task could not be deleted."));
    } finally {
      mark(deleting.id, false);
    }
  };

  const filtered = status !== "" || priority !== "";
  const list = shown?.items ?? [];
  const canDelete = (task: WorkspaceTask) => can.edit || (can.contribute && task.creator_id === userId);

  return (
    <section className={styles.section} aria-labelledby="item-tasks-heading">
      <div className={styles.sectionHead}>
        <h2 id="item-tasks-heading" className={styles.sectionTitle}>
          Tasks
        </h2>
        {can.contribute && (
          <Button
            leadingIcon={<Plus size={16} aria-hidden="true" />}
            onClick={() => {
              setCreateError(null);
              setTitleError(null);
              setCreating(true);
            }}
          >
            New task
          </Button>
        )}
      </div>
      <div className={styles.filters}>
        <Select label="Status" value={status} onChange={(event) => setStatus(event.target.value as TaskStatus | "")}>
          <option value="">All statuses</option>
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {taskStatusMeta(value).label}
            </option>
          ))}
        </Select>
        <Select label="Priority" value={priority} onChange={(event) => setPriority(event.target.value as TaskPriority | "")}>
          <option value="">All priorities</option>
          {PRIORITIES.map((entry) => (
            <option key={entry.value} value={entry.value}>
              {entry.label}
            </option>
          ))}
        </Select>
      </div>
      <p role="status" className="rc-visually-hidden">
        {message}
      </p>
      {error && (
        <Alert tone="danger" announce>
          {error}
        </Alert>
      )}

      {shown === undefined ? (
        tasks.status === "error" ? (
          <ErrorState title="The tasks could not be loaded" kind={tasks.error?.kind === "network" ? "offline" : "failed"} onRetry={tasks.retry} />
        ) : (
          <SkeletonList rows={3} label="Loading tasks" />
        )
      ) : list.length === 0 ? (
        filtered ? (
          <EmptyState
            variant="no-results"
            title="No tasks match."
            actions={
              <Button
                variant="secondary"
                onClick={() => {
                  setStatus("");
                  setPriority("");
                }}
              >
                Show all tasks
              </Button>
            }
          />
        ) : (
          <EmptyState title="No tasks yet." description="Split the submission into tasks: sections to draft, figures, co-author sign-offs." />
        )
      ) : (
        <ul className={styles.list} aria-busy={tasks.status === "loading" || undefined}>
          {list.map((task) => {
            const done = task.status === "COMPLETED";
            const due = shortDate(task.due_at);
            return (
              <li key={task.id} className={styles.row}>
                {can.contribute && (
                  <span className={styles.check}>
                    <input
                      type="checkbox"
                      checked={done}
                      disabled={busy.has(task.id) || task.status === "CANCELLED"}
                      aria-label={done ? `Reopen ${task.title}` : `Mark ${task.title} done`}
                      onChange={() => void toggle(task)}
                    />
                  </span>
                )}
                <div className={styles.rowMain}>
                  <h3 className={`${styles.rowTitle} ${done ? styles.done : ""}`}>{task.title}</h3>
                  {task.description && <p className={styles.text}>{task.description}</p>}
                  <p className={styles.meta}>
                    <StatusBadge meta={taskStatusMeta(task.status)} />
                    <PriorityLabel priority={task.priority} />
                    <span>{task.assignee_name ? `Assigned to ${task.assignee_name}` : "Unassigned"}</span>
                    {due && <span>Due {due}</span>}
                    {task.creator_name && <span>Added by {task.creator_name}</span>}
                  </p>
                </div>
                {canDelete(task) && (
                  <div className={styles.rowActions}>
                    <IconButton
                      variant="ghost"
                      label={`Delete ${task.title}`}
                      icon={<Trash2 size={16} aria-hidden="true" />}
                      disabled={busy.has(task.id)}
                      onClick={() => {
                        setDeleteError(null);
                        setDeleting(task);
                      }}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <Dialog
        open={creating}
        onClose={() => setCreating(false)}
        title="New task"
        initialFocusRef={titleRef}
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button type="submit" form="item-task-form" loading={saving}>
              Create task
            </Button>
          </>
        }
      >
        <form id="item-task-form" className={styles.form} onSubmit={create} noValidate>
          {createError && (
            <Alert tone="danger" announce>
              {createError}
            </Alert>
          )}
          <TextInput
            ref={titleRef}
            label="Title"
            required
            maxLength={255}
            value={draft.title}
            error={titleError}
            onChange={(event) => {
              setDraft({ ...draft, title: event.target.value });
              if (titleError && event.target.value.trim()) setTitleError(null);
            }}
          />
          <TextArea label="Description" rows={3} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} />
          <Select label="Assigned to" value={draft.assignee} onChange={(event) => setDraft({ ...draft, assignee: event.target.value })}>
            <option value="">Nobody yet</option>
            {(members.data?.items ?? [])
              .filter((member) => member.status === "ACTIVE")
              .map((member) => (
                <option key={member.user_id} value={member.user_id}>
                  {member.user?.full_name || member.user?.email || "Member"}
                </option>
              ))}
          </Select>
          <div className={styles.formRow}>
            <Select label="Priority" value={draft.priority} onChange={(event) => setDraft({ ...draft, priority: event.target.value as TaskPriority })}>
              {PRIORITIES.map((entry) => (
                <option key={entry.value} value={entry.value}>
                  {entry.label}
                </option>
              ))}
            </Select>
            <TextInput label="Due date" type="date" value={draft.due} onChange={(event) => setDraft({ ...draft, due: event.target.value })} />
          </div>
        </form>
      </Dialog>

      <Dialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        size="sm"
        title={`Delete the task "${deleting?.title ?? ""}"?`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button variant="danger" loading={deleting !== null && busy.has(deleting.id)} onClick={() => void remove()}>
              Delete task
            </Button>
          </>
        }
      >
        <p>It is removed for everyone on this item. This cannot be undone.</p>
        {deleteError && (
          <Alert tone="danger" announce>
            {deleteError}
          </Alert>
        )}
      </Dialog>
    </section>
  );
}
