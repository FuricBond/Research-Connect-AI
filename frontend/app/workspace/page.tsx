"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import "../../styles/workspace.css";
import type {
  WorkspaceFilterParams,
  WorkspaceItem,
  WorkspacePriority,
  WorkspaceStatus,
  WorkspaceSummaryResponse,
} from "../../types/workspace";
import {
  archiveWorkspaceItem,
  fetchWorkspaceItems,
  fetchWorkspaceSummary,
  removeWorkspaceItem,
  transitionWorkspaceStatus,
  unarchiveWorkspaceItem,
  updateWorkspaceItem,
} from "../../services/api";
import {
  AlertCircle,
  Archive,
  ArrowRight,
  Briefcase,
  Calendar,
  Clock,
  ExternalLink,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Tag,
  Trash2,
  X,
} from "lucide-react";

type FilterTab = "ALL" | WorkspaceStatus;

const PIPELINE_TABS: { label: string; value: FilterTab }[] = [
  { label: "All Items", value: "ALL" },
  { label: "Saved", value: "SAVED" },
  { label: "Considering", value: "CONSIDERING" },
  { label: "Planning", value: "PLANNING" },
  { label: "Applied", value: "APPLIED" },
  { label: "Accepted", value: "ACCEPTED" },
  { label: "Rejected", value: "REJECTED" },
  { label: "Archived", value: "ARCHIVED" },
];

export default function WorkspacePage() {
  const [items, setItems] = useState<WorkspaceItem[]>([]);
  const [summary, setSummary] = useState<WorkspaceSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & Search
  const [activeTab, setActiveTab] = useState<FilterTab>("ALL");
  const [priorityFilter, setPriorityFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [tagFilter, setTagFilter] = useState<string>("");

  // Per-item mutation states
  const [mutatingId, setMutatingId] = useState<string | null>(null);
  const [editingNotesId, setEditingNotesId] = useState<string | null>(null);
  const [notesDraft, setNotesDraft] = useState<Record<string, string>>({});
  const [newTagInput, setNewTagInput] = useState<Record<string, string>>({});

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const filters: WorkspaceFilterParams = {
        status: activeTab === "ALL" ? undefined : activeTab,
        priority: priorityFilter ? (priorityFilter as WorkspacePriority) : undefined,
        tag: tagFilter.trim() || undefined,
        search: searchQuery.trim() || undefined,
        include_archived: activeTab === "ALL" || activeTab === "ARCHIVED",
      };

      const [itemsRes, summaryRes] = await Promise.all([
        fetchWorkspaceItems(filters),
        fetchWorkspaceSummary(),
      ]);

      setItems(itemsRes.items);
      setSummary(summaryRes);

      // Prepopulate notes draft
      const drafts: Record<string, string> = {};
      itemsRes.items.forEach((item: WorkspaceItem) => {
        drafts[item.id] = item.notes || "";
      });
      setNotesDraft(drafts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load workspace opportunities");
    } finally {
      setLoading(false);
    }
  }, [activeTab, priorityFilter, tagFilter, searchQuery]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle Transition
  const handleTransition = async (itemId: string, newStatus: WorkspaceStatus) => {
    setMutatingId(itemId);
    try {
      await transitionWorkspaceStatus(itemId, newStatus);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update status");
    } finally {
      setMutatingId(null);
    }
  };

  // Handle Priority Change
  const handlePriorityChange = async (itemId: string, newPriority: WorkspacePriority) => {
    setMutatingId(itemId);
    try {
      await updateWorkspaceItem(itemId, { priority: newPriority });
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update priority");
    } finally {
      setMutatingId(null);
    }
  };

  // Handle Notes Save
  const handleSaveNotes = async (itemId: string) => {
    setMutatingId(itemId);
    try {
      const notes = notesDraft[itemId] ?? "";
      await updateWorkspaceItem(itemId, { notes });
      setEditingNotesId(null);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save notes");
    } finally {
      setMutatingId(null);
    }
  };

  // Handle Tag Add
  const handleAddTag = async (item: WorkspaceItem) => {
    const rawTag = (newTagInput[item.id] || "").trim();
    if (!rawTag) return;
    if (item.tags.includes(rawTag)) {
      setNewTagInput((prev) => ({ ...prev, [item.id]: "" }));
      return;
    }
    const updatedTags = [...item.tags, rawTag];
    setMutatingId(item.id);
    try {
      await updateWorkspaceItem(item.id, { tags: updatedTags });
      setNewTagInput((prev) => ({ ...prev, [item.id]: "" }));
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add tag");
    } finally {
      setMutatingId(null);
    }
  };

  // Handle Tag Remove
  const handleRemoveTag = async (item: WorkspaceItem, tagToRemove: string) => {
    const updatedTags = item.tags.filter((t: string) => t !== tagToRemove);
    setMutatingId(item.id);
    try {
      await updateWorkspaceItem(item.id, { tags: updatedTags });
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove tag");
    } finally {
      setMutatingId(null);
    }
  };

  // Handle Archive
  const handleArchive = async (itemId: string) => {
    setMutatingId(itemId);
    try {
      await archiveWorkspaceItem(itemId);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive item");
    } finally {
      setMutatingId(null);
    }
  };

  // Handle Unarchive
  const handleUnarchive = async (itemId: string) => {
    setMutatingId(itemId);
    try {
      await unarchiveWorkspaceItem(itemId, "SAVED");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to unarchive item");
    } finally {
      setMutatingId(null);
    }
  };

  // Handle Remove Item
  const handleRemove = async (itemId: string) => {
    if (!window.confirm("Remove this opportunity from your workspace?")) return;
    setMutatingId(itemId);
    try {
      await removeWorkspaceItem(itemId);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove opportunity");
    } finally {
      setMutatingId(null);
    }
  };

  const getStatusBadgeClass = (status: WorkspaceStatus) => {
    switch (status) {
      case "SAVED":
        return "status-badge-saved";
      case "CONSIDERING":
        return "status-badge-considering";
      case "PLANNING":
        return "status-badge-planning";
      case "APPLIED":
        return "status-badge-applied";
      case "ACCEPTED":
        return "status-badge-accepted";
      case "REJECTED":
        return "status-badge-rejected";
      case "ARCHIVED":
        return "status-badge-archived";
      default:
        return "";
    }
  };

  const getPriorityBadgeClass = (priority: WorkspacePriority) => {
    switch (priority) {
      case "URGENT":
        return "priority-urgent";
      case "HIGH":
        return "priority-high";
      case "MEDIUM":
        return "priority-medium";
      case "LOW":
        return "priority-low";
      default:
        return "";
    }
  };

  return (
    <div className="workspace-container">
      {/* ── Header ────────────────────────────────────────── */}
      <div className="workspace-header">
        <div className="workspace-header-top">
          <div className="workspace-title-wrap">
            <h1>Opportunity Workspace</h1>
            <p className="workspace-tagline">
              Organize, prioritize, and track your saved academic opportunities through structured research workflows.
            </p>
          </div>
          <button
            onClick={() => loadData()}
            className="workspace-action-btn"
            title="Refresh Workspace"
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>

        {/* ── Summary Stats Strip ───────────────────────────── */}
        {summary && (
          <div className="workspace-stats-strip">
            <div className="workspace-stat-card">
              <span className="workspace-stat-label">Active Pipeline</span>
              <span className="workspace-stat-value">{summary.active_count}</span>
            </div>
            <div className="workspace-stat-card">
              <span className="workspace-stat-label">Considering / Planning</span>
              <span className="workspace-stat-value">
                {(summary.counts_by_status["CONSIDERING"] || 0) +
                  (summary.counts_by_status["PLANNING"] || 0)}
              </span>
            </div>
            <div className="workspace-stat-card">
              <span className="workspace-stat-label">Applied</span>
              <span className="workspace-stat-value">
                {summary.counts_by_status["APPLIED"] || 0}
              </span>
            </div>
            <div className="workspace-stat-card">
              <span className="workspace-stat-label">Accepted</span>
              <span className="workspace-stat-value">
                {summary.counts_by_status["ACCEPTED"] || 0}
              </span>
            </div>
            <div className="workspace-stat-card">
              <span className="workspace-stat-label">Archived</span>
              <span className="workspace-stat-value">{summary.archived_count}</span>
            </div>
          </div>
        )}
      </div>

      {/* ── Error Banner ──────────────────────────────────── */}
      {error && (
        <div className="workspace-error-banner">
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
          <button
            onClick={() => setError(null)}
            className="workspace-action-btn"
            style={{ background: "transparent", border: "none", color: "#991b1b" }}
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* ── Controls & Filter Bar ─────────────────────────── */}
      <div className="workspace-controls">
        {/* Pipeline Tabs */}
        <div className="workspace-pipeline-tabs">
          {PIPELINE_TABS.map((tab) => {
            const count =
              tab.value === "ALL"
                ? summary?.total_count ?? 0
                : tab.value === "ARCHIVED"
                ? summary?.archived_count ?? 0
                : summary?.counts_by_status[tab.value] ?? 0;

            return (
              <button
                key={tab.value}
                onClick={() => setActiveTab(tab.value)}
                className={`workspace-pipeline-tab ${activeTab === tab.value ? "active" : ""}`}
              >
                <span>{tab.label}</span>
                <span className="workspace-tab-count">{count}</span>
              </button>
            );
          })}
        </div>

        {/* Filter Inputs Row */}
        <div className="workspace-filter-row">
          <div className="workspace-search-box">
            <Search size={15} className="workspace-search-icon" />
            <input
              type="text"
              placeholder="Search opportunity title, venue, or notes..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="workspace-search-input"
            />
          </div>

          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            className="workspace-select"
          >
            <option value="">All Priorities</option>
            <option value="URGENT">Urgent Priority</option>
            <option value="HIGH">High Priority</option>
            <option value="MEDIUM">Medium Priority</option>
            <option value="LOW">Low Priority</option>
          </select>

          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <Tag size={15} style={{ color: "var(--text-muted)" }} />
            <input
              type="text"
              placeholder="Filter by tag..."
              value={tagFilter}
              onChange={(e) => setTagFilter(e.target.value)}
              className="workspace-search-input"
              style={{ width: "150px", padding: "8px 12px" }}
            />
          </div>
        </div>
      </div>

      {/* ── Content List / States ─────────────────────────── */}
      {loading && items.length === 0 ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "64px 0" }}>
          <Loader2 size={32} className="animate-spin" style={{ color: "var(--primary)" }} />
        </div>
      ) : items.length === 0 ? (
        <div className="workspace-empty-state">
          <Briefcase className="workspace-empty-icon" />
          <h2 className="workspace-empty-title">
            {activeTab === "ALL" ? "Your workspace is empty" : `No opportunities in ${activeTab}`}
          </h2>
          <p className="workspace-empty-desc">
            Discover conferences, journals, and funding calls matching your research profile, then save them to organize your submission workflow.
          </p>
          <Link href="/opportunities" className="workspace-action-btn primary" style={{ textDecoration: "none" }}>
            <span>Explore Opportunities</span>
            <ArrowRight size={14} />
          </Link>
        </div>
      ) : (
        <div className="workspace-list">
          {items.map((item: WorkspaceItem) => {
            const isMutating = mutatingId === item.id;
            const opp = item.opportunity;
            const venueOrOrg = opp?.publisher || opp?.organizer;
            const deadlineInfo = opp?.deadline_intelligence;
            const primaryDeadline =
              opp?.submission_deadline ||
              deadlineInfo?.primary_view?.canonical_deadline?.utc_deadline ||
              deadlineInfo?.primary_view?.canonical_deadline?.local_date;
            const daysRemaining = deadlineInfo?.primary_view?.canonical_assessment?.days_remaining;
            const urgency = deadlineInfo?.overall_urgency_tier || "UNKNOWN";
            const riskLevel =
              opp?.risk_explanation?.risk_level ||
              (opp?.risk_score !== null && opp?.risk_score !== undefined
                ? opp.risk_score > 0.6
                  ? "HIGH_RISK"
                  : opp.risk_score > 0.3
                  ? "MODERATE_RISK"
                  : "LOW_RISK"
                : null);

            return (
              <div key={item.id} className="workspace-card">
                <div className="workspace-card-top">
                  <div className="workspace-card-title-area">
                    <div className="workspace-card-badges">
                      <span className={`workspace-status-badge ${getStatusBadgeClass(item.status)}`}>
                        {item.status}
                      </span>
                      <span className={`workspace-priority-badge ${getPriorityBadgeClass(item.priority)}`}>
                        {item.priority}
                      </span>
                      {item.archived_at && (
                        <span className="workspace-status-badge status-badge-archived">
                          ARCHIVED
                        </span>
                      )}
                    </div>

                    <h2 className="workspace-card-title">
                      {opp?.title || "Academic Opportunity"}
                    </h2>

                    <div className="workspace-card-meta">
                      {venueOrOrg && (
                        <span className="workspace-meta-item">
                          <strong>Publisher/Organizer:</strong> {venueOrOrg}
                        </span>
                      )}
                      {opp?.opportunity_type && (
                        <span className="workspace-meta-item">
                          <strong>Type:</strong> {opp.opportunity_type}
                        </span>
                      )}
                      <span className="workspace-meta-item">
                        <Clock size={13} />
                        Updated {new Date(item.updated_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>

                  {opp?.website_url && (
                    <a
                      href={opp.website_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="workspace-action-btn"
                      title="Open source call page"
                    >
                      <ExternalLink size={13} />
                      View Call
                    </a>
                  )}
                </div>

                {/* ── Canonical Deadline & Risk Intelligence Strip ── */}
                {opp && (
                  <div className="workspace-intel-strip">
                    <div className="workspace-intel-left">
                      {primaryDeadline ? (
                        <span
                          className={`workspace-deadline-pill ${
                            urgency === "CRITICAL"
                              ? "deadline-pill-critical"
                              : urgency === "URGENT"
                              ? "deadline-pill-urgent"
                              : "deadline-pill-normal"
                          }`}
                        >
                          <Calendar size={13} />
                          Deadline: {new Date(primaryDeadline).toLocaleDateString()}
                          {daysRemaining !== null && daysRemaining !== undefined && (
                            <span>({daysRemaining}d remaining)</span>
                          )}
                        </span>
                      ) : (
                        <span className="workspace-meta-item">
                          <Calendar size={13} /> No deadline specified
                        </span>
                      )}

                      {riskLevel && riskLevel !== "UNKNOWN" && (
                        <span className="workspace-risk-pill">
                          Risk: {riskLevel}
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {/* ── Notes Section ── */}
                <div className="workspace-notes-section">
                  <div className="workspace-notes-header">
                    <span>Researcher Notes & Submission Notes</span>
                    {editingNotesId !== item.id ? (
                      <button
                        onClick={() => setEditingNotesId(item.id)}
                        className="workspace-action-btn"
                        style={{ padding: "2px 8px", fontSize: "11px" }}
                        disabled={isMutating}
                      >
                        Edit Notes
                      </button>
                    ) : (
                      <button
                        onClick={() => handleSaveNotes(item.id)}
                        className="workspace-action-btn primary"
                        style={{ padding: "2px 8px", fontSize: "11px" }}
                        disabled={isMutating}
                      >
                        {isMutating ? <Loader2 size={11} className="animate-spin" /> : "Save"}
                      </button>
                    )}
                  </div>

                  {editingNotesId === item.id ? (
                    <textarea
                      value={notesDraft[item.id] ?? ""}
                      onChange={(e) =>
                        setNotesDraft((prev) => ({ ...prev, [item.id]: e.target.value }))
                      }
                      className="workspace-notes-textarea"
                      placeholder="Add submission track, manuscript title, co-author tasks, or reminders..."
                    />
                  ) : (
                    <p style={{ margin: 0, fontSize: "13px", color: item.notes ? "var(--text-body)" : "var(--text-subtle)", fontStyle: item.notes ? "normal" : "italic" }}>
                      {item.notes || "No notes added yet."}
                    </p>
                  )}

                  {/* ── Tag Chips & Tag Input ── */}
                  <div className="workspace-tags-row">
                    {item.tags.map((tag: string) => (
                      <span key={tag} className="workspace-tag-chip">
                        #{tag}
                        <button
                          onClick={() => handleRemoveTag(item, tag)}
                          className="workspace-tag-remove"
                          title="Remove tag"
                          disabled={isMutating}
                        >
                          <X size={12} />
                        </button>
                      </span>
                    ))}

                    <div style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
                      <input
                        type="text"
                        placeholder="+ Add tag"
                        value={newTagInput[item.id] || ""}
                        onChange={(e) =>
                          setNewTagInput((prev) => ({ ...prev, [item.id]: e.target.value }))
                        }
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            handleAddTag(item);
                          }
                        }}
                        className="workspace-tag-input"
                        disabled={isMutating}
                      />
                      {newTagInput[item.id] && (
                        <button
                          onClick={() => handleAddTag(item)}
                          className="workspace-action-btn"
                          style={{ padding: "2px 6px", fontSize: "11px" }}
                          disabled={isMutating}
                        >
                          <Plus size={11} />
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                {/* ── Workflow Action Controls ── */}
                <div className="workspace-card-actions">
                  <div className="workspace-transition-group">
                    <span className="workspace-transition-label">Move to:</span>
                    {item.allowed_transitions.length > 0 ? (
                      item.allowed_transitions.map((nextStatus: WorkspaceStatus) => (
                        <button
                          key={nextStatus}
                          onClick={() => handleTransition(item.id, nextStatus)}
                          disabled={isMutating}
                          className="workspace-action-btn"
                        >
                          {isMutating ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            <ArrowRight size={12} />
                          )}
                          {nextStatus}
                        </button>
                      ))
                    ) : (
                      <span style={{ fontSize: "12px", color: "var(--text-subtle)" }}>
                        Terminal state
                      </span>
                    )}
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    {/* Priority Selector */}
                    <select
                      value={item.priority}
                      onChange={(e) =>
                        handlePriorityChange(item.id, e.target.value as WorkspacePriority)
                      }
                      disabled={isMutating}
                      className="workspace-select"
                      style={{ padding: "4px 8px", fontSize: "12px" }}
                    >
                      <option value="LOW">Low</option>
                      <option value="MEDIUM">Medium</option>
                      <option value="HIGH">High</option>
                      <option value="URGENT">Urgent</option>
                    </select>

                    {/* Submissions Management Link */}
                    <Link
                      href={`/workspace/${item.id}/submission`}
                      className="workspace-action-btn primary"
                      title="Manage research submissions"
                      style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "6px" }}
                    >
                      <FileText size={12} />
                      Submissions
                    </Link>

                    {/* Archive / Unarchive Button */}
                    {item.status === "ARCHIVED" ? (
                      <button
                        onClick={() => handleUnarchive(item.id)}
                        disabled={isMutating}
                        className="workspace-action-btn"
                        title="Restore to active workflow"
                      >
                        <RotateCcw size={12} />
                        Restore
                      </button>
                    ) : (
                      <button
                        onClick={() => handleArchive(item.id)}
                        disabled={isMutating}
                        className="workspace-action-btn"
                        title="Archive opportunity"
                      >
                        <Archive size={12} />
                        Archive
                      </button>
                    )}

                    {/* Remove from Workspace */}
                    <button
                      onClick={() => handleRemove(item.id)}
                      disabled={isMutating}
                      className="workspace-action-btn danger"
                      title="Remove from workspace"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
