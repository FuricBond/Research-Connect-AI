"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import "@/styles/submission.css";
import type {
  DocumentStatus,
  DocumentType,
  ResearchSubmission,
  ResearchSubmissionCreate,
  ResearchSubmissionDocument,
  ResearchSubmissionUpdate,
  SubmissionDocumentCreate,
  SubmissionDocumentUpdate,
  SubmissionDocumentVersion,
  SubmissionHistoryEvent,
  SubmissionReadinessResponse,
  SubmissionStatus,
  SubmissionType,
} from "@/types/submission";
import type { WorkspaceItem } from "@/types/workspace";
import {
  createSubmission,
  createSubmissionDocument,
  deleteSubmission,
  deleteSubmissionDocument,
  fetchDocumentVersions,
  fetchSubmissionDocuments,
  fetchSubmissionHistory,
  fetchSubmissionReadiness,
  fetchWorkspaceItems,
  fetchWorkspaceSubmissions,
  transitionSubmissionStatus,
  updateSubmission,
  updateSubmissionDocument,
} from "@/services/api";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Calendar,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileCheck,
  FileText,
  Globe,
  History,
  Info,
  Layers,
  ListChecks,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Send,
  ShieldAlert,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { RequireAuth } from "../../../../components/auth/RequireAuth";

interface PageProps {
  params: Promise<{ id: string }>;
}

const SUBMISSION_TYPES: { label: string; value: SubmissionType }[] = [
  { label: "Full Paper", value: "FULL_PAPER" },
  { label: "Short Paper", value: "SHORT_PAPER" },
  { label: "Extended Abstract", value: "EXTENDED_ABSTRACT" },
  { label: "Poster", value: "POSTER" },
  { label: "Workshop Paper", value: "WORKSHOP_PAPER" },
  { label: "Grant Proposal", value: "GRANT_PROPOSAL" },
  { label: "Other", value: "OTHER" },
];

const DOCUMENT_TYPES: { label: string; value: DocumentType }[] = [
  { label: "Full Paper", value: "FULL_PAPER" },
  { label: "Abstract", value: "ABSTRACT" },
  { label: "Cover Letter", value: "COVER_LETTER" },
  { label: "Author Bio", value: "AUTHOR_BIO" },
  { label: "CV / Resume", value: "CV" },
  { label: "Supplementary Materials", value: "SUPPLEMENTARY" },
  { label: "Figures & Tables", value: "FIGURES" },
  { label: "Dataset / Artifact", value: "DATASET" },
  { label: "Source Code / Notebooks", value: "CODE" },
  { label: "Conflict / Disclosure", value: "DISCLOSURE" },
  { label: "Other Document", value: "OTHER" },
];

const LIFECYCLE_STEPS: { status: SubmissionStatus; label: string; stepNumber: number }[] = [
  { status: "DRAFT", label: "Draft", stepNumber: 1 },
  { status: "READY", label: "Ready", stepNumber: 2 },
  { status: "SUBMITTED", label: "Submitted", stepNumber: 3 },
  { status: "UNDER_REVIEW", label: "Under Review", stepNumber: 4 },
  { status: "ACCEPTED", label: "Decision", stepNumber: 5 },
];

function getStepState(
  stepStatus: SubmissionStatus,
  currentStatus: SubmissionStatus
): "completed" | "active" | "future" | "rejected" | "withdrawn" {
  if (currentStatus === "WITHDRAWN") return "withdrawn";

  const order: Record<SubmissionStatus, number> = {
    DRAFT: 1,
    READY: 2,
    SUBMITTED: 3,
    UNDER_REVIEW: 4,
    ACCEPTED: 5,
    REJECTED: 5,
    WITHDRAWN: 0,
  };

  const currentIdx = order[currentStatus] ?? 1;
  const stepIdx = order[stepStatus] ?? 1;

  if (stepStatus === "ACCEPTED") {
    if (currentStatus === "ACCEPTED") return "active";
    if (currentStatus === "REJECTED") return "rejected";
    return "future";
  }

  if (currentIdx > stepIdx) return "completed";
  if (currentIdx === stepIdx) return "active";
  return "future";
}

type TabKey = "overview" | "documents" | "readiness" | "history";

function SubmissionManagementPage({ params }: PageProps) {
  const { id: workspaceItemId } = React.use(params);

  const [workspaceItem, setWorkspaceItem] = useState<WorkspaceItem | null>(null);
  const [submissions, setSubmissions] = useState<ResearchSubmission[]>([]);
  const [selectedSubId, setSelectedSubId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Workflow & Document State
  const [documents, setDocuments] = useState<ResearchSubmissionDocument[]>([]);
  const [readiness, setReadiness] = useState<SubmissionReadinessResponse | null>(null);
  const [historyEvents, setHistoryEvents] = useState<SubmissionHistoryEvent[]>([]);
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);

  // Modals & Drawers
  const [showAddDocModal, setShowAddDocModal] = useState(false);
  const [showVersionModal, setShowVersionModal] = useState<ResearchSubmissionDocument | null>(null);
  const [versionHistoryList, setVersionHistoryList] = useState<SubmissionDocumentVersion[]>([]);
  const [loadingVersions, setLoadingVersions] = useState(false);

  // Document Forms
  const [newDocType, setNewDocType] = useState<DocumentType>("FULL_PAPER");
  const [newDocTitle, setNewDocTitle] = useState("");
  const [newDocDesc, setNewDocDesc] = useState("");
  const [newDocRequired, setNewDocRequired] = useState(true);
  const [newDocStorageRef, setNewDocStorageRef] = useState("");
  const [newDocMime, setNewDocMime] = useState("application/pdf");
  const [newDocStatus, setNewDocStatus] = useState<DocumentStatus>("DRAFT");

  // Version Update Form
  const [versionUpdateDoc, setVersionUpdateDoc] = useState<ResearchSubmissionDocument | null>(null);
  const [updateDocStatus, setUpdateDocStatus] = useState<DocumentStatus>("READY");
  const [updateDocStorageRef, setUpdateDocStorageRef] = useState("");
  const [updateDocMime, setUpdateDocMime] = useState("");
  const [updateDocChecksum, setUpdateDocChecksum] = useState("");
  const [updateDocNotes, setUpdateDocNotes] = useState("");

  // Submission Edit Form
  const [isSaving, setIsSaving] = useState(false);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [editForm, setEditForm] = useState<ResearchSubmissionUpdate>({});
  const [transitionNotes, setTransitionNotes] = useState("");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newSubmissionTitle, setNewSubmissionTitle] = useState("");
  const [newSubmissionType, setNewSubmissionType] = useState<SubmissionType>("FULL_PAPER");

  // Load parent workspace and submissions
  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const wsRes = await fetchWorkspaceItems({ limit: 100, include_archived: true });
      const parent = wsRes.items.find((it: WorkspaceItem) => it.id === workspaceItemId) || null;
      setWorkspaceItem(parent);

      const subsRes = await fetchWorkspaceSubmissions(workspaceItemId);
      setSubmissions(subsRes.items);

      if (subsRes.items.length > 0) {
        const targetId =
          selectedSubId && subsRes.items.some((s: ResearchSubmission) => s.id === selectedSubId)
            ? selectedSubId
            : subsRes.items[0].id;
        setSelectedSubId(targetId);

        const currentSub = subsRes.items.find((s: ResearchSubmission) => s.id === targetId);
        if (currentSub) {
          setEditForm({
            title: currentSub.title,
            abstract: currentSub.abstract || "",
            submission_type: currentSub.submission_type,
            venue: currentSub.venue || "",
            external_submission_id: currentSub.external_submission_id || "",
            submission_url: currentSub.submission_url || "",
            notes: currentSub.notes || "",
          });
        }
      } else {
        setShowCreateForm(true);
        if (parent) {
          setNewSubmissionTitle(`Submission: ${parent.opportunity.title}`);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load submission tracking");
    } finally {
      setLoading(false);
    }
  }, [workspaceItemId, selectedSubId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const activeSubmission = submissions.find((s) => s.id === selectedSubId) || null;

  // Load documents, readiness, and history for active submission
  const loadSubmissionDetails = useCallback(async (subId: string) => {
    setIsLoadingDetails(true);
    try {
      const [docsRes, readyRes, histRes] = await Promise.all([
        fetchSubmissionDocuments(subId),
        fetchSubmissionReadiness(subId),
        fetchSubmissionHistory(subId, { limit: 50 }),
      ]);
      setDocuments(docsRes.items);
      setReadiness(readyRes);
      setHistoryEvents(histRes.items);
    } catch (err) {
      console.error("Failed to load submission details:", err);
    } finally {
      setIsLoadingDetails(false);
    }
  }, []);

  useEffect(() => {
    if (activeSubmission) {
      loadSubmissionDetails(activeSubmission.id);
    }
  }, [activeSubmission?.id, loadSubmissionDetails]);

  // Switch selected submission
  const handleSelectSubmission = (sub: ResearchSubmission) => {
    setSelectedSubId(sub.id);
    setShowCreateForm(false);
    setEditForm({
      title: sub.title,
      abstract: sub.abstract || "",
      submission_type: sub.submission_type,
      venue: sub.venue || "",
      external_submission_id: sub.external_submission_id || "",
      submission_url: sub.submission_url || "",
      notes: sub.notes || "",
    });
  };

  // Save metadata
  const handleSaveMetadata = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeSubmission) return;

    setIsSaving(true);
    setError(null);
    setActionSuccess(null);
    try {
      const updated = await updateSubmission(activeSubmission.id, editForm);
      setSubmissions((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      setActionSuccess("Submission details saved successfully.");
      await loadSubmissionDetails(activeSubmission.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save submission metadata");
    } finally {
      setIsSaving(false);
    }
  };

  // State Transition
  const handleTransition = async (targetStatus: SubmissionStatus) => {
    if (!activeSubmission) return;

    setIsTransitioning(true);
    setError(null);
    setActionSuccess(null);
    try {
      const transitioned = await transitionSubmissionStatus(activeSubmission.id, {
        target_status: targetStatus,
        notes: transitionNotes.trim() || undefined,
      });
      setSubmissions((prev) => prev.map((s) => (s.id === transitioned.id ? transitioned : s)));
      setTransitionNotes("");
      setActionSuccess(`Status successfully transitioned to ${targetStatus}.`);
      await loadSubmissionDetails(activeSubmission.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Status transition failed");
    } finally {
      setIsTransitioning(false);
    }
  };

  // Create new submission draft
  const handleCreateSubmission = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSubmissionTitle.trim()) return;

    setIsSaving(true);
    setError(null);
    try {
      const payload: ResearchSubmissionCreate = {
        workspace_item_id: workspaceItemId,
        title: newSubmissionTitle.trim(),
        submission_type: newSubmissionType,
      };
      const created = await createSubmission(payload);
      setSubmissions((prev) => [created, ...prev]);
      setSelectedSubId(created.id);
      setShowCreateForm(false);
      setEditForm({
        title: created.title,
        abstract: "",
        submission_type: created.submission_type,
        venue: "",
        external_submission_id: "",
        submission_url: "",
        notes: "",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create submission draft");
    } finally {
      setIsSaving(false);
    }
  };

  // Delete submission
  const handleDeleteSubmission = async () => {
    if (!activeSubmission) return;
    if (!confirm(`Are you sure you want to delete "${activeSubmission.title}"?`)) return;

    setIsSaving(true);
    setError(null);
    try {
      await deleteSubmission(activeSubmission.id);
      const remaining = submissions.filter((s) => s.id !== activeSubmission.id);
      setSubmissions(remaining);
      if (remaining.length > 0) {
        handleSelectSubmission(remaining[0]);
      } else {
        setSelectedSubId(null);
        setShowCreateForm(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete submission");
    } finally {
      setIsSaving(false);
    }
  };

  // Add Document
  const handleCreateDocument = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeSubmission || !newDocTitle.trim()) return;

    setIsSaving(true);
    setError(null);
    try {
      const payload: SubmissionDocumentCreate = {
        document_type: newDocType,
        title: newDocTitle.trim(),
        description: newDocDesc.trim() || undefined,
        is_required: newDocRequired,
        status: newDocStatus,
        storage_reference: newDocStorageRef.trim() || undefined,
        file_metadata: {
          mime_type: newDocMime.trim() || "application/pdf",
        },
      };
      await createSubmissionDocument(activeSubmission.id, payload);
      setShowAddDocModal(false);
      setNewDocTitle("");
      setNewDocDesc("");
      setNewDocStorageRef("");
      await loadSubmissionDetails(activeSubmission.id);
      setActionSuccess("Document artifact created successfully.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create document artifact");
    } finally {
      setIsSaving(false);
    }
  };

  // Quick mark document ready
  const handleQuickMarkReady = async (doc: ResearchSubmissionDocument) => {
    if (!activeSubmission) return;
    try {
      await updateSubmissionDocument(activeSubmission.id, doc.id, {
        status: "READY",
      });
      await loadSubmissionDetails(activeSubmission.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update document status");
    }
  };

  // Open Version Update Dialog
  const handleOpenVersionModal = (doc: ResearchSubmissionDocument) => {
    setVersionUpdateDoc(doc);
    setUpdateDocStatus(doc.status);
    setUpdateDocStorageRef(doc.storage_reference || "");
    setUpdateDocMime(doc.file_metadata?.mime_type || "application/pdf");
    setUpdateDocChecksum("");
    setUpdateDocNotes("");
  };

  // Submit Version Update
  const handleSaveDocVersion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeSubmission || !versionUpdateDoc) return;

    setIsSaving(true);
    setError(null);
    try {
      const payload: SubmissionDocumentUpdate = {
        status: updateDocStatus,
        storage_reference: updateDocStorageRef.trim() || undefined,
        file_metadata: {
          mime_type: updateDocMime.trim() || undefined,
          checksum_sha256: updateDocChecksum.trim() || undefined,
          version_notes: updateDocNotes.trim() || undefined,
        },
        create_new_version: true,
      };
      await updateSubmissionDocument(activeSubmission.id, versionUpdateDoc.id, payload);
      setVersionUpdateDoc(null);
      await loadSubmissionDetails(activeSubmission.id);
      setActionSuccess("Document version snapshot recorded successfully.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update document version");
    } finally {
      setIsSaving(false);
    }
  };

  // View Version History
  const handleViewVersions = async (doc: ResearchSubmissionDocument) => {
    if (!activeSubmission) return;
    setShowVersionModal(doc);
    setLoadingVersions(true);
    try {
      const versions = await fetchDocumentVersions(activeSubmission.id, doc.id);
      setVersionHistoryList(versions);
    } catch (err) {
      console.error("Failed to load versions:", err);
    } finally {
      setLoadingVersions(false);
    }
  };

  // Archive Document
  const handleArchiveDoc = async (doc: ResearchSubmissionDocument) => {
    if (!activeSubmission) return;
    try {
      await updateSubmissionDocument(activeSubmission.id, doc.id, {
        status: "ARCHIVED",
      });
      await loadSubmissionDetails(activeSubmission.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive document");
    }
  };

  // Delete Document
  const handleDeleteDoc = async (doc: ResearchSubmissionDocument) => {
    if (!activeSubmission) return;
    if (!confirm(`Delete document "${doc.title}"? This cannot be undone.`)) return;

    try {
      await deleteSubmissionDocument(activeSubmission.id, doc.id);
      await loadSubmissionDetails(activeSubmission.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete document");
    }
  };

  if (loading) {
    return (
      <div className="submission-container">
        <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--text-muted)", padding: "40px 0" }}>
          <Loader2 className="animate-spin" size={18} /> Loading submission tracking...
        </div>
      </div>
    );
  }

  const opp = workspaceItem?.opportunity;
  const deadlineCtx = activeSubmission?.deadline_context;

  return (
    <div className="submission-container">
      {/* ── Top Navigation ── */}
      <Link href="/workspace" className="submission-back-link">
        <ArrowLeft size={14} /> Back to Opportunity Workspace
      </Link>

      {/* ── Alerts ── */}
      {error && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            background: "#fee2e2",
            border: "1px solid #fca5a5",
            color: "#b91c1c",
            borderRadius: "var(--radius-md)",
            padding: "12px 16px",
            marginBottom: "20px",
            fontSize: "13px",
          }}
        >
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {actionSuccess && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            background: "#dcfce7",
            border: "1px solid #86efac",
            color: "#15803d",
            borderRadius: "var(--radius-md)",
            padding: "12px 16px",
            marginBottom: "20px",
            fontSize: "13px",
          }}
        >
          <CheckCircle2 size={16} />
          {actionSuccess}
        </div>
      )}

      {/* ── Opportunity Workspace Context Header ── */}
      <div className="submission-header">
        <div className="submission-header-top">
          <div>
            <h1 className="submission-opp-title">{opp?.title || "Opportunity Workspace Item"}</h1>
            <div className="submission-opp-meta">
              <span className="submission-opp-meta-item">
                <Globe size={13} /> {opp?.publisher || opp?.organizer || "Independent Venue"}
              </span>
              <span className="submission-opp-meta-item">
                <FileText size={13} /> {opp?.opportunity_type || "CONFERENCE"}
              </span>
              <span className="submission-opp-meta-item">
                Workspace Status: <strong>{workspaceItem?.status || "PLANNING"}</strong>
              </span>
            </div>
          </div>

          <button
            onClick={() => setShowCreateForm(true)}
            className="btn-save"
            style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
          >
            <Plus size={14} /> New Submission Attempt
          </button>
        </div>
      </div>

      {/* ── Phase 2.7 Deadline Intelligence Banner ── */}
      {deadlineCtx && deadlineCtx.submission_deadline && (
        <div
          className={`submission-deadline-alert ${
            deadlineCtx.urgency_tier === "CRITICAL"
              ? "critical"
              : deadlineCtx.urgency_tier === "URGENT" || deadlineCtx.urgency_tier === "APPROACHING"
              ? "approaching"
              : ""
          }`}
        >
          <div className="deadline-left">
            <Clock className="deadline-icon" />
            <div className="deadline-details">
              <h4>
                Official Submission Deadline:{" "}
                {new Date(deadlineCtx.submission_deadline).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                  timeZoneName: "short",
                })}
              </h4>
              <p>
                {deadlineCtx.days_remaining !== null && deadlineCtx.days_remaining !== undefined
                  ? `${Math.round(deadlineCtx.days_remaining)} days remaining until manuscript cutoff.`
                  : "Deadline date confirmed from official CFPs."}
                {deadlineCtx.summary && ` ${deadlineCtx.summary}`}
              </p>
            </div>
          </div>

          <div className="deadline-badges">
            {deadlineCtx.is_aoe && <span className="badge-aoe">AoE Anywhere on Earth</span>}
            {deadlineCtx.has_extension && <span className="badge-extension">Deadline Extended</span>}
            {deadlineCtx.urgency_tier && (
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  padding: "3px 8px",
                  borderRadius: "4px",
                  background: "var(--bg-main)",
                  border: "1px solid var(--border-color)",
                }}
              >
                {deadlineCtx.urgency_tier}
              </span>
            )}
          </div>
        </div>
      )}

      {/* ── Phase 4.3 Readiness Summary Banner ── */}
      {readiness && activeSubmission && !showCreateForm && (
        <div
          className={`readiness-banner ${readiness.overall_readiness.toLowerCase()}`}
        >
          <div className="readiness-header-left">
            <div
              className={`readiness-status-pill ${readiness.overall_readiness.toLowerCase()}`}
            >
              {readiness.overall_readiness === "READY" && <CheckCircle2 size={14} />}
              {readiness.overall_readiness === "BLOCKED" && <ShieldAlert size={14} />}
              {readiness.overall_readiness === "NOT_READY" && <AlertTriangle size={14} />}
              Readiness: {readiness.overall_readiness.replace("_", " ")}
            </div>

            <div>
              <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-main)" }}>
                {readiness.readiness_explanation}
              </div>
              <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                {readiness.completed_document_count} of {readiness.required_document_count} required documents ready •{" "}
                {readiness.readiness_percentage}% completed
              </div>
            </div>
          </div>

          <div>
            <div className="readiness-score-bar-container">
              <div
                className={`readiness-score-bar-fill ${
                  readiness.readiness_percentage >= 80
                    ? "high"
                    : readiness.readiness_percentage >= 50
                    ? "medium"
                    : "low"
                }`}
                style={{ width: `${readiness.readiness_percentage}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* ── Create Submission Attempt Form ── */}
      {showCreateForm && (
        <div className="submission-card" style={{ border: "2px solid var(--color-primary)" }}>
          <h2 className="submission-card-title">Create New Research Submission Draft</h2>
          <form onSubmit={handleCreateSubmission}>
            <div className="form-group">
              <label className="form-label">Manuscript / Proposal Title *</label>
              <input
                type="text"
                required
                value={newSubmissionTitle}
                onChange={(e) => setNewSubmissionTitle(e.target.value)}
                placeholder="e.g. Robust Representation Learning via Contrastive Masking"
                className="form-input"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Submission Format</label>
              <select
                value={newSubmissionType}
                onChange={(e) => setNewSubmissionType(e.target.value as SubmissionType)}
                className="form-select"
              >
                {SUBMISSION_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="btn-action-row">
              <button type="submit" disabled={isSaving} className="btn-save">
                {isSaving ? <Loader2 size={13} className="animate-spin" /> : "Create Draft"}
              </button>
              {submissions.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowCreateForm(false)}
                  className="doc-action-btn"
                >
                  Cancel
                </button>
              )}
            </div>
          </form>
        </div>
      )}

      {/* ── Active Submission View ── */}
      {activeSubmission && !showCreateForm && (
        <>
          {/* ── Pipeline Stepper ── */}
          <div className="submission-pipeline-card">
            <div className="pipeline-title">
              Submission Lifecycle Pipeline — Status:{" "}
              <span className={`status-badge ${activeSubmission.status.toLowerCase()}`}>
                {activeSubmission.status}
              </span>
            </div>

            <div className="submission-stepper">
              {LIFECYCLE_STEPS.map((step) => {
                const state = getStepState(step.status, activeSubmission.status);
                return (
                  <div key={step.status} className={`stepper-step ${state}`}>
                    <div className="stepper-circle">
                      {state === "completed" ? (
                        <CheckCircle2 size={16} />
                      ) : state === "rejected" ? (
                        <XCircle size={16} />
                      ) : (
                        step.stepNumber
                      )}
                    </div>
                    <span className="stepper-label">
                      {step.status === "ACCEPTED" && activeSubmission.status === "REJECTED"
                        ? "Rejected"
                        : step.label}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* ── Navigation Tabs ── */}
          <div className="submission-tabs">
            <button
              onClick={() => setActiveTab("overview")}
              className={`submission-tab-btn ${activeTab === "overview" ? "active" : ""}`}
            >
              <FileText size={15} /> Overview & Lifecycle
            </button>
            <button
              onClick={() => setActiveTab("documents")}
              className={`submission-tab-btn ${activeTab === "documents" ? "active" : ""}`}
            >
              <Layers size={15} /> Documents & Checklist
              <span className="submission-tab-badge">{documents.length}</span>
            </button>
            <button
              onClick={() => setActiveTab("readiness")}
              className={`submission-tab-btn ${activeTab === "readiness" ? "active" : ""}`}
            >
              <ListChecks size={15} /> Readiness Evaluation
              {readiness && readiness.blocking_issues.length > 0 && (
                <span
                  className="submission-tab-badge"
                  style={{ background: "#fee2e2", color: "#b91c1c" }}
                >
                  {readiness.blocking_issues.length}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveTab("history")}
              className={`submission-tab-btn ${activeTab === "history" ? "active" : ""}`}
            >
              <History size={15} /> Audit History
              <span className="submission-tab-badge">{historyEvents.length}</span>
            </button>
          </div>

          {/* ── TAB 1: Overview & Metadata ── */}
          {activeTab === "overview" && (
            <div className="submission-content-grid">
              {/* Left Column: Metadata & Form */}
              <div>
                <div className="submission-card">
                  <h3 className="submission-card-title">
                    <span>Manuscript & Submission Details</span>
                    <span className={`status-badge ${activeSubmission.status.toLowerCase()}`}>
                      {activeSubmission.status}
                    </span>
                  </h3>

                  <form onSubmit={handleSaveMetadata}>
                    <div className="form-group">
                      <label className="form-label">Manuscript Title</label>
                      <input
                        type="text"
                        required
                        value={editForm.title || ""}
                        onChange={(e) =>
                          setEditForm((prev) => ({ ...prev, title: e.target.value }))
                        }
                        className="form-input"
                      />
                    </div>

                    <div className="form-row">
                      <div className="form-group">
                        <label className="form-label">Submission Type</label>
                        <select
                          value={editForm.submission_type || "FULL_PAPER"}
                          onChange={(e) =>
                            setEditForm((prev) => ({
                              ...prev,
                              submission_type: e.target.value as SubmissionType,
                            }))
                          }
                          className="form-select"
                        >
                          {SUBMISSION_TYPES.map((t) => (
                            <option key={t.value} value={t.value}>
                              {t.label}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="form-group">
                        <label className="form-label">Venue / Track Name</label>
                        <input
                          type="text"
                          value={editForm.venue || ""}
                          onChange={(e) =>
                            setEditForm((prev) => ({ ...prev, venue: e.target.value }))
                          }
                          placeholder={opp?.title || "e.g. Main Track / Oral"}
                          className="form-input"
                        />
                      </div>
                    </div>

                    <div className="form-row">
                      <div className="form-group">
                        <label className="form-label">External Submission / Paper ID</label>
                        <input
                          type="text"
                          value={editForm.external_submission_id || ""}
                          onChange={(e) =>
                            setEditForm((prev) => ({
                              ...prev,
                              external_submission_id: e.target.value,
                            }))
                          }
                          placeholder="e.g. OPENREVIEW-9811, CMT #45"
                          className="form-input"
                        />
                      </div>

                      <div className="form-group">
                        <label className="form-label">Portal / Tracking URL</label>
                        <div style={{ display: "flex", gap: "6px" }}>
                          <input
                            type="url"
                            value={editForm.submission_url || ""}
                            onChange={(e) =>
                              setEditForm((prev) => ({
                                ...prev,
                                submission_url: e.target.value,
                              }))
                            }
                            placeholder="https://openreview.net/forum?id=..."
                            className="form-input"
                          />
                          {editForm.submission_url && (
                            <a
                              href={editForm.submission_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="doc-action-btn"
                              title="Open submission portal"
                              style={{ display: "inline-flex", alignItems: "center", padding: "0 10px" }}
                            >
                              <ExternalLink size={14} />
                            </a>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="form-group">
                      <label className="form-label">Abstract</label>
                      <textarea
                        value={editForm.abstract || ""}
                        onChange={(e) =>
                          setEditForm((prev) => ({ ...prev, abstract: e.target.value }))
                        }
                        placeholder="Paste manuscript abstract or proposal summary..."
                        className="form-textarea"
                      />
                    </div>

                    <div className="form-group">
                      <label className="form-label">Notes & Rebuttal Strategy</label>
                      <textarea
                        value={editForm.notes || ""}
                        onChange={(e) =>
                          setEditForm((prev) => ({ ...prev, notes: e.target.value }))
                        }
                        placeholder="Notes on co-author tasks, rebuttal timeline, or reviewer feedback..."
                        className="form-textarea"
                        style={{ minHeight: "80px" }}
                      />
                    </div>

                    <div className="btn-action-row">
                      <button
                        type="submit"
                        disabled={isSaving}
                        className="btn-save"
                        style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
                      >
                        {isSaving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                        Save Metadata
                      </button>

                      {(activeSubmission.status === "DRAFT" ||
                        activeSubmission.status === "WITHDRAWN") && (
                        <button
                          type="button"
                          onClick={handleDeleteSubmission}
                          disabled={isSaving}
                          className="btn-delete-sub"
                          style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
                        >
                          <Trash2 size={13} /> Delete Submission
                        </button>
                      )}
                    </div>
                  </form>
                </div>
              </div>

              {/* Right Column: Workflow Actions & Attempts */}
              <div>
                <div className="submission-card">
                  <h3 className="submission-card-title">Lifecycle Actions</h3>

                  <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: "0 0 14px 0" }}>
                    Deterministic state transitions available from{" "}
                    <strong>{activeSubmission.status}</strong>:
                  </p>

                  {/* If moving to READY is blocked by readiness issues */}
                  {activeSubmission.status === "DRAFT" &&
                    readiness &&
                    readiness.overall_readiness !== "READY" && (
                      <div
                        style={{
                          marginBottom: "14px",
                          padding: "10px",
                          background: "#fffbeb",
                          border: "1px solid #fde68a",
                          borderRadius: "var(--radius-md)",
                          fontSize: "12px",
                          color: "#92400e",
                        }}
                      >
                        <div style={{ fontWeight: 600, display: "flex", alignItems: "center", gap: "5px" }}>
                          <AlertTriangle size={13} /> Gated Transition:
                        </div>
                        Resolving {readiness.blocking_issues.length} blocking issues is required before marking this submission READY.
                      </div>
                    )}

                  {activeSubmission.allowed_transitions.length > 0 ? (
                    <div className="transition-actions-panel">
                      <div className="form-group" style={{ marginBottom: "12px" }}>
                        <label className="form-label" style={{ fontSize: "12px" }}>
                          Transition Notes (optional)
                        </label>
                        <input
                          type="text"
                          value={transitionNotes}
                          onChange={(e) => setTransitionNotes(e.target.value)}
                          placeholder="e.g. All co-author signoffs received"
                          className="form-input"
                          style={{ fontSize: "12px", padding: "6px 10px" }}
                        />
                      </div>

                      {activeSubmission.allowed_transitions.map((nextStatus: SubmissionStatus) => {
                        const isPromote = nextStatus === "SUBMITTED" || nextStatus === "ACCEPTED";
                        const isReject = nextStatus === "REJECTED";
                        const isWithdraw = nextStatus === "WITHDRAWN";
                        const isReadyTransition = nextStatus === "READY";
                        const isBlocked =
                          isReadyTransition &&
                          readiness &&
                          readiness.overall_readiness !== "READY";

                        return (
                          <button
                            key={nextStatus}
                            onClick={() => handleTransition(nextStatus)}
                            disabled={isTransitioning || Boolean(isBlocked)}
                            title={isBlocked ? "Blocked by incomplete requirements" : undefined}
                            className={`btn-transition ${
                              isPromote
                                ? "primary"
                                : isReject
                                ? "danger"
                                : isWithdraw
                                ? ""
                                : "success"
                            }`}
                          >
                            <span>Move to {nextStatus}</span>
                            {isTransitioning ? (
                              <Loader2 size={13} className="animate-spin" />
                            ) : (
                              <Send size={13} />
                            )}
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                      No valid forward transitions available from this state.
                    </p>
                  )}

                  {activeSubmission.status === "SUBMITTED" && activeSubmission.submitted_at && (
                    <div
                      style={{
                        marginTop: "16px",
                        padding: "10px",
                        background: "rgba(16, 185, 129, 0.08)",
                        borderRadius: "var(--radius-md)",
                        fontSize: "12px",
                        color: "#065f46",
                      }}
                    >
                      Officially submitted on:{" "}
                      <strong>{new Date(activeSubmission.submitted_at).toLocaleDateString()}</strong>
                    </div>
                  )}

                  {activeSubmission.decision_at && (
                    <div
                      style={{
                        marginTop: "10px",
                        padding: "10px",
                        background: "rgba(59, 130, 246, 0.08)",
                        borderRadius: "var(--radius-md)",
                        fontSize: "12px",
                        color: "#1e40af",
                      }}
                    >
                      Decision recorded on:{" "}
                      <strong>{new Date(activeSubmission.decision_at).toLocaleDateString()}</strong>
                    </div>
                  )}
                </div>

                {/* Submissions List */}
                {submissions.length > 1 && (
                  <div className="submission-card">
                    <h3 className="submission-card-title">All Attempts for Opportunity</h3>
                    <div className="submission-attempts-list">
                      {submissions.map((sub) => (
                        <div
                          key={sub.id}
                          onClick={() => handleSelectSubmission(sub)}
                          className={`submission-attempt-card ${
                            sub.id === activeSubmission.id ? "selected" : ""
                          }`}
                        >
                          <div className="attempt-header">
                            <h4 className="attempt-title">{sub.title}</h4>
                            <span className={`status-badge ${sub.status.toLowerCase()}`}>
                              {sub.status}
                            </span>
                          </div>
                          <div className="attempt-meta">
                            {sub.submission_type} • Updated{" "}
                            {new Date(sub.updated_at).toLocaleDateString()}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── TAB 2: Documents & Checklist ── */}
          {activeTab === "documents" && (
            <div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "20px",
                }}
              >
                <div>
                  <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700 }}>
                    Submission Artifacts & Manuscript Documents
                  </h3>
                  <p style={{ margin: "4px 0 0 0", fontSize: "13px", color: "var(--text-muted)" }}>
                    Manage required manuscripts, disclosures, source code repositories, and version history.
                  </p>
                </div>

                <button
                  onClick={() => setShowAddDocModal(true)}
                  className="btn-save"
                  style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
                >
                  <Plus size={14} /> Add Document Artifact
                </button>
              </div>

              {documents.length === 0 ? (
                <div
                  className="submission-card"
                  style={{ textAlign: "center", padding: "48px 24px", color: "var(--text-muted)" }}
                >
                  <FileText size={36} style={{ margin: "0 auto 12px auto", opacity: 0.4 }} />
                  <h4 style={{ margin: "0 0 6px 0", color: "var(--text-main)" }}>No documents added yet</h4>
                  <p style={{ fontSize: "13px", maxWidth: "420px", margin: "0 auto 16px auto" }}>
                    Attach your manuscript PDF, abstract text, author bio, or disclosures to track versioning and readiness.
                  </p>
                  <button onClick={() => setShowAddDocModal(true)} className="btn-save">
                    Add First Document
                  </button>
                </div>
              ) : (
                <div className="documents-grid">
                  {documents.map((doc) => (
                    <div
                      key={doc.id}
                      className={`document-card ${
                        doc.is_required ? "required-card" : "optional-card"
                      }`}
                    >
                      <div className="document-top-row">
                        <div className="document-main-info">
                          <div className="document-type-icon">
                            <FileText size={18} />
                          </div>

                          <div className="document-title-wrap">
                            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                              <h4 className="document-title">{doc.title}</h4>
                              <span
                                className={`doc-status-badge ${doc.status.toLowerCase()}`}
                              >
                                {doc.status}
                              </span>
                              {doc.is_required ? (
                                <span className="doc-badge-req">Required</span>
                              ) : (
                                <span className="doc-badge-opt">Optional</span>
                              )}
                            </div>

                            <div className="document-meta-line">
                              <span>Type: <strong>{doc.document_type}</strong></span>
                              <span>Version: <strong>v{doc.current_version}</strong></span>
                              {doc.file_metadata?.mime_type && <span>Format: {doc.file_metadata.mime_type}</span>}
                              {doc.storage_reference && (
                                <span>Ref: <code>{doc.storage_reference}</code></span>
                              )}
                              {doc.file_metadata?.checksum_sha256 && (
                                <span title={doc.file_metadata.checksum_sha256}>
                                  SHA: <code>{String(doc.file_metadata.checksum_sha256).substring(0, 8)}...</code>
                                </span>
                              )}
                            </div>

                            {doc.description && (
                              <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: "6px 0 0 0" }}>
                                {doc.description}
                              </p>
                            )}
                          </div>
                        </div>

                        <div style={{ display: "flex", gap: "6px" }}>
                          {doc.status !== "READY" && doc.status !== "ARCHIVED" && (
                            <button
                              onClick={() => handleQuickMarkReady(doc)}
                              className="doc-action-btn success"
                              title="Mark document READY"
                            >
                              <CheckCircle2 size={12} /> Mark Ready
                            </button>
                          )}
                          <button
                            onClick={() => handleOpenVersionModal(doc)}
                            className="doc-action-btn primary"
                            title="Record new version"
                          >
                            New Version
                          </button>
                        </div>
                      </div>

                      <div className="document-actions-row">
                        <button
                          onClick={() => handleViewVersions(doc)}
                          className="doc-action-btn"
                        >
                          <History size={12} /> Version History ({doc.versions_count})
                        </button>
                        {doc.status !== "ARCHIVED" && (
                          <button
                            onClick={() => handleArchiveDoc(doc)}
                            className="doc-action-btn"
                          >
                            Archive
                          </button>
                        )}
                        <button
                          onClick={() => handleDeleteDoc(doc)}
                          className="doc-action-btn danger"
                        >
                          <Trash2 size={12} /> Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── TAB 3: Readiness Evaluation ── */}
          {activeTab === "readiness" && (
            <div>
              {readiness ? (
                <div>
                  <div className="submission-card">
                    <h3 className="submission-card-title">
                      <span>Readiness Assessment</span>
                      <span
                        className={`readiness-status-pill ${readiness.overall_readiness.toLowerCase()}`}
                      >
                        {readiness.overall_readiness}
                      </span>
                    </h3>

                    <p style={{ fontSize: "14px", margin: "0 0 16px 0" }}>
                      {readiness.readiness_explanation}
                    </p>

                    <div style={{ marginBottom: "20px" }}>
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          fontSize: "12px",
                          fontWeight: 600,
                          marginBottom: "4px",
                        }}
                      >
                        <span>Preparation Completion Score</span>
                        <span>{readiness.readiness_percentage}%</span>
                      </div>
                      <div className="readiness-score-bar-container" style={{ width: "100%", height: "10px" }}>
                        <div
                          className={`readiness-score-bar-fill ${
                            readiness.readiness_percentage >= 80
                              ? "high"
                              : readiness.readiness_percentage >= 50
                              ? "medium"
                              : "low"
                          }`}
                          style={{ width: `${readiness.readiness_percentage}%` }}
                        />
                      </div>
                    </div>

                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                        gap: "12px",
                        marginTop: "16px",
                        padding: "16px",
                        background: "var(--bg-main)",
                        borderRadius: "var(--radius-md)",
                      }}
                    >
                      <div>
                        <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>Required Docs</div>
                        <div style={{ fontSize: "18px", fontWeight: 700 }}>
                          {readiness.required_document_count}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>Completed Docs</div>
                        <div style={{ fontSize: "18px", fontWeight: 700, color: "#10b981" }}>
                          {readiness.completed_document_count}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>Missing Docs</div>
                        <div style={{ fontSize: "18px", fontWeight: 700, color: "#ef4444" }}>
                          {readiness.missing_document_count}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>Metadata Complete</div>
                        <div style={{ fontSize: "18px", fontWeight: 700 }}>
                          {readiness.metadata_completeness >= 1 ? "100%" : `${Math.round(readiness.metadata_completeness * 100)}%`}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Blocking Issues */}
                  {readiness.blocking_issues.length > 0 && (
                    <div className="submission-card" style={{ borderLeft: "4px solid #ef4444" }}>
                      <h4 style={{ margin: "0 0 10px 0", color: "#b91c1c", display: "flex", alignItems: "center", gap: "6px" }}>
                        <ShieldAlert size={16} /> Blocking Issues ({readiness.blocking_issues.length})
                      </h4>
                      <p style={{ fontSize: "13px", color: "var(--text-muted)", margin: "0 0 12px 0" }}>
                        The submission cannot be transitioned to READY while these blockers remain unresolved.
                      </p>
                      <div className="readiness-issues-list">
                        {readiness.blocking_issues.map((issue, idx) => (
                          <div key={idx} className="readiness-issue-item blocker">
                            <XCircle className="issue-icon" size={16} />
                            <div className="issue-body">
                              <div className="issue-message">{issue.message}</div>
                              <div className="issue-meta">
                                Code: <code>{issue.code}</code>
                                {issue.field && ` • Field: ${issue.field}`}
                                {issue.document_id && ` • Document ID: ${issue.document_id}`}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Warnings */}
                  {readiness.warnings.length > 0 && (
                    <div className="submission-card" style={{ borderLeft: "4px solid #f59e0b" }}>
                      <h4 style={{ margin: "0 0 10px 0", color: "#b45309", display: "flex", alignItems: "center", gap: "6px" }}>
                        <AlertTriangle size={16} /> Warnings & Recommendations ({readiness.warnings.length})
                      </h4>
                      <div className="readiness-issues-list">
                        {readiness.warnings.map((warn, idx) => (
                          <div key={idx} className="readiness-issue-item warning">
                            <Info className="issue-icon" size={16} />
                            <div className="issue-body">
                              <div className="issue-message">{warn.message}</div>
                              <div className="issue-meta">
                                Code: <code>{warn.code}</code>
                                {warn.field && ` • Field: ${warn.field}`}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--text-muted)" }}>
                  <Loader2 size={16} className="animate-spin" /> Evaluating submission readiness...
                </div>
              )}
            </div>
          )}

          {/* ── TAB 4: Audit History ── */}
          {activeTab === "history" && (
            <div>
              <div className="submission-card">
                <h3 className="submission-card-title">
                  <span>Submission Workflow Audit Trail</span>
                  <button
                    onClick={() => activeSubmission && loadSubmissionDetails(activeSubmission.id)}
                    className="doc-action-btn"
                    style={{ fontSize: "11px" }}
                  >
                    <RefreshCw size={11} /> Refresh
                  </button>
                </h3>

                <p style={{ fontSize: "13px", color: "var(--text-muted)", margin: "0 0 20px 0" }}>
                  Deterministic history of all lifecycle transitions, document attachments, version increments, and metadata updates.
                </p>

                {historyEvents.length === 0 ? (
                  <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                    No audit events recorded yet.
                  </p>
                ) : (
                  <div className="audit-timeline">
                    {historyEvents.map((evt) => (
                      <div key={evt.id} className="audit-event-row">
                        <div className="audit-event-dot" />
                        <div className="audit-event-content">
                          <div className="audit-event-header">
                            <div className="audit-event-title">
                              {evt.event_type.replace(/_/g, " ")}
                            </div>
                            <div className="audit-event-time">
                              {new Date(evt.created_at).toLocaleString()}
                            </div>
                          </div>

                          <div className="audit-event-actor">
                            Actor: {evt.created_by_id ? `User ${evt.created_by_id.substring(0, 8)}...` : "System / Researcher"}
                            {evt.document_id && ` • Document Artifact: ${evt.document_id.substring(0, 8)}...`}
                          </div>

                          {evt.description && <div className="audit-event-notes">{evt.description}</div>}

                          {evt.new_state && Object.keys(evt.new_state).length > 0 && (
                            <div
                              style={{
                                marginTop: "6px",
                                fontSize: "11px",
                                color: "var(--text-muted)",
                                background: "rgba(0,0,0,0.02)",
                                padding: "4px 8px",
                                borderRadius: "4px",
                              }}
                            >
                              <code>{JSON.stringify(evt.new_state)}</code>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* ── MODAL: Add Document Artifact ── */}
      {showAddDocModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
            padding: "20px",
          }}
        >
          <div
            className="submission-card"
            style={{
              maxWidth: "520px",
              width: "100%",
              maxHeight: "90vh",
              overflowY: "auto",
              margin: 0,
              boxShadow: "var(--shadow-lg)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: "16px",
              }}
            >
              <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>
                Add Document Artifact
              </h3>
              <button
                onClick={() => setShowAddDocModal(false)}
                style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCreateDocument}>
              <div className="form-group">
                <label className="form-label">Document Category *</label>
                <select
                  value={newDocType}
                  onChange={(e) => setNewDocType(e.target.value as DocumentType)}
                  className="form-select"
                >
                  {DOCUMENT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Artifact Name / Title *</label>
                <input
                  type="text"
                  required
                  value={newDocTitle}
                  onChange={(e) => setNewDocTitle(e.target.value)}
                  placeholder="e.g. NeurIPS 2026 Camera-Ready Draft"
                  className="form-input"
                />
              </div>

              <div className="form-group">
                <label className="form-label">Description (optional)</label>
                <input
                  type="text"
                  value={newDocDesc}
                  onChange={(e) => setNewDocDesc(e.target.value)}
                  placeholder="e.g. Main 8-page paper with appendix"
                  className="form-input"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Initial Status</label>
                  <select
                    value={newDocStatus}
                    onChange={(e) => setNewDocStatus(e.target.value as DocumentStatus)}
                    className="form-select"
                  >
                    <option value="DRAFT">DRAFT</option>
                    <option value="REQUIRED">REQUIRED</option>
                    <option value="READY">READY</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Requirement Rule</label>
                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      fontSize: "13px",
                      marginTop: "8px",
                      cursor: "pointer",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={newDocRequired}
                      onChange={(e) => setNewDocRequired(e.target.checked)}
                    />
                    Required for submission
                  </label>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">MIME Content Type</label>
                  <input
                    type="text"
                    value={newDocMime}
                    onChange={(e) => setNewDocMime(e.target.value)}
                    placeholder="application/pdf"
                    className="form-input"
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Storage / Reference URI</label>
                  <input
                    type="text"
                    value={newDocStorageRef}
                    onChange={(e) => setNewDocStorageRef(e.target.value)}
                    placeholder="s3://... or drive://..."
                    className="form-input"
                  />
                </div>
              </div>

              <div className="btn-action-row" style={{ justifyContent: "flex-end" }}>
                <button
                  type="button"
                  onClick={() => setShowAddDocModal(false)}
                  className="doc-action-btn"
                >
                  Cancel
                </button>
                <button type="submit" disabled={isSaving} className="btn-save">
                  {isSaving ? <Loader2 size={13} className="animate-spin" /> : "Save Document"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: Update Document Version ── */}
      {versionUpdateDoc && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
            padding: "20px",
          }}
        >
          <div
            className="submission-card"
            style={{
              maxWidth: "500px",
              width: "100%",
              maxHeight: "90vh",
              overflowY: "auto",
              margin: 0,
              boxShadow: "var(--shadow-lg)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: "16px",
              }}
            >
              <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>
                Record New Version: {versionUpdateDoc.title}
              </h3>
              <button
                onClick={() => setVersionUpdateDoc(null)}
                style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}
              >
                <X size={18} />
              </button>
            </div>

            <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: "0 0 16px 0" }}>
              Current version is <strong>v{versionUpdateDoc.current_version}</strong>. Submitting will snapshot the existing version and advance to <strong>v{versionUpdateDoc.current_version + 1}</strong>.
            </p>

            <form onSubmit={handleSaveDocVersion}>
              <div className="form-group">
                <label className="form-label">Document Status</label>
                <select
                  value={updateDocStatus}
                  onChange={(e) => setUpdateDocStatus(e.target.value as DocumentStatus)}
                  className="form-select"
                >
                  <option value="READY">READY</option>
                  <option value="DRAFT">DRAFT</option>
                  <option value="REQUIRED">REQUIRED</option>
                  <option value="REJECTED">REJECTED</option>
                  <option value="ARCHIVED">ARCHIVED</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Storage / Reference URI</label>
                <input
                  type="text"
                  value={updateDocStorageRef}
                  onChange={(e) => setUpdateDocStorageRef(e.target.value)}
                  placeholder="s3://... or drive://..."
                  className="form-input"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">MIME Type</label>
                  <input
                    type="text"
                    value={updateDocMime}
                    onChange={(e) => setUpdateDocMime(e.target.value)}
                    placeholder="application/pdf"
                    className="form-input"
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">SHA-256 Checksum (optional)</label>
                  <input
                    type="text"
                    value={updateDocChecksum}
                    onChange={(e) => setUpdateDocChecksum(e.target.value)}
                    placeholder="e3b0c44298fc1c149afbf4c8..."
                    className="form-input"
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Version Changelog / Notes</label>
                <textarea
                  value={updateDocNotes}
                  onChange={(e) => setUpdateDocNotes(e.target.value)}
                  placeholder="e.g. Addressed reviewer comments on Figure 3; updated bibliography"
                  className="form-textarea"
                  style={{ minHeight: "70px" }}
                />
              </div>

              <div className="btn-action-row" style={{ justifyContent: "flex-end" }}>
                <button
                  type="button"
                  onClick={() => setVersionUpdateDoc(null)}
                  className="doc-action-btn"
                >
                  Cancel
                </button>
                <button type="submit" disabled={isSaving} className="btn-save">
                  {isSaving ? <Loader2 size={13} className="animate-spin" /> : "Save New Version"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── DRAWER / MODAL: Version History ── */}
      {showVersionModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
            padding: "20px",
          }}
        >
          <div
            className="submission-card"
            style={{
              maxWidth: "540px",
              width: "100%",
              maxHeight: "80vh",
              overflowY: "auto",
              margin: 0,
              boxShadow: "var(--shadow-lg)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: "16px",
              }}
            >
              <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>
                Version History: {showVersionModal.title}
              </h3>
              <button
                onClick={() => setShowVersionModal(null)}
                style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}
              >
                <X size={18} />
              </button>
            </div>

            {loadingVersions ? (
              <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--text-muted)" }}>
                <Loader2 size={16} className="animate-spin" /> Loading version history...
              </div>
            ) : versionHistoryList.length === 0 ? (
              <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                No previous version snapshots found. Current version is v{showVersionModal.current_version}.
              </p>
            ) : (
              <div>
                {versionHistoryList.map((ver) => (
                  <div key={ver.id} className="version-item">
                    <div className="version-item-header">
                      <span className="version-num">Version v{ver.version_number}</span>
                      <span className={`doc-status-badge ${ver.status.toLowerCase()}`}>
                        {ver.status}
                      </span>
                    </div>
                    <div className="version-meta">
                      Recorded on {new Date(ver.created_at).toLocaleString()}
                      {ver.file_metadata?.file_size_bytes && ` • ${(ver.file_metadata.file_size_bytes / 1024).toFixed(1)} KB`}
                      {ver.file_metadata?.mime_type && ` • ${ver.file_metadata.mime_type}`}
                    </div>
                    {ver.storage_reference && (
                      <div style={{ fontSize: "11px", marginTop: "4px" }}>
                        Ref: <code>{ver.storage_reference}</code>
                      </div>
                    )}
                    {ver.checksum && (
                      <div style={{ fontSize: "11px", marginTop: "2px" }}>
                        SHA-256: <code>{ver.checksum}</code>
                      </div>
                    )}
                    {ver.file_metadata?.version_notes && (
                      <div style={{ fontSize: "12px", marginTop: "6px", fontStyle: "italic" }}>
                        &ldquo;{ver.file_metadata.version_notes}&rdquo;
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div className="btn-action-row" style={{ justifyContent: "flex-end", marginTop: "16px" }}>
              <button
                type="button"
                onClick={() => setShowVersionModal(null)}
                className="doc-action-btn"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


export default function SubmissionManagementPageRoute(props: PageProps) {
  return (
    <RequireAuth>
      <SubmissionManagementPage {...props} />
    </RequireAuth>
  );
}
