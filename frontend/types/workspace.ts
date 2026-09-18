import type { OpportunityDeadline, RiskExplanation } from "./opportunity";

export type WorkspaceStatus =
  | "SAVED"
  | "CONSIDERING"
  | "PLANNING"
  | "APPLIED"
  | "ACCEPTED"
  | "REJECTED"
  | "ARCHIVED";

export type WorkspacePriority = "LOW" | "MEDIUM" | "HIGH" | "URGENT";

export interface WorkspaceOpportunitySummary {
  id: string;
  title: string;
  opportunity_type: string;
  delivery_mode: string;
  publisher?: string | null;
  organizer?: string | null;
  submission_deadline?: string | null;
  notification_date?: string | null;
  camera_ready_deadline?: string | null;
  event_start_date?: string | null;
  location?: string | null;
  website_url?: string | null;
  status: string;
  risk_score?: number | null;
  is_predatory_flag: boolean;
  deadline_intelligence?: OpportunityDeadline | null;
  risk_explanation?: RiskExplanation | null;
}

export interface WorkspaceItem {
  id: string;
  user_id: string;
  opportunity_id: string;
  status: WorkspaceStatus;
  priority: WorkspacePriority;
  tags: string[];
  notes?: string | null;
  created_at: string;
  updated_at: string;
  status_updated_at: string;
  archived_at?: string | null;
  allowed_transitions: WorkspaceStatus[];
  opportunity: WorkspaceOpportunitySummary;
}

export interface WorkspaceListResponse {
  items: WorkspaceItem[];
  total_count: number;
  active_count: number;
  archived_count: number;
  counts_by_status: Record<string, number>;
  counts_by_priority: Record<string, number>;
}

export interface WorkspaceSummaryResponse {
  total_count: number;
  active_count: number;
  archived_count: number;
  counts_by_status: Record<string, number>;
  counts_by_priority: Record<string, number>;
}

export interface WorkspaceItemCreatePayload {
  opportunity_id: string;
  status?: WorkspaceStatus;
  priority?: WorkspacePriority;
  tags?: string[];
  notes?: string;
}

export interface WorkspaceItemUpdatePayload {
  priority?: WorkspacePriority;
  tags?: string[];
  notes?: string;
}

export interface WorkspaceStatusTransitionPayload {
  target_status: WorkspaceStatus;
  notes?: string;
}

export interface WorkspaceFilterParams {
  status?: WorkspaceStatus;
  priority?: WorkspacePriority;
  tag?: string;
  search?: string;
  include_archived?: boolean;
  sort_by?: "updated_at" | "created_at" | "deadline" | "priority" | "status";
  sort_order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}
