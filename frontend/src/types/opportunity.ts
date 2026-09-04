export type OpportunityType =
  | "CONFERENCE"
  | "JOURNAL"
  | "WORKSHOP"
  | "CALL_FOR_PAPERS"
  | "SPECIAL_ISSUE";

export type OpportunityStatus =
  | "ACTIVE"
  | "EXPIRED"
  | "ARCHIVED"
  | "DRAFT"
  | "UNVERIFIED";

export type DeliveryMode = "ONLINE" | "OFFLINE" | "HYBRID";

export type RiskLevel =
  | "LOW_RISK"
  | "MODERATE_RISK"
  | "HIGH_RISK"
  | "INSUFFICIENT_EVIDENCE";

export type EvidenceCategory =
  | "POSITIVE_TRUST"
  | "NEGATIVE_SUSPICIOUS"
  | "NEUTRAL_UNKNOWN";

export interface RiskEvidenceItem {
  signal: string;
  category: EvidenceCategory | string;
  strength: "NONE" | "WEAK" | "MODERATE" | "STRONG" | string;
  confidence: "LOW" | "MEDIUM" | "HIGH" | string;
  provenance: string;
  source_field: string;
  matched_value?: string | null;
  explanation: string;
  is_present: boolean;
  contribution: number;
  severity: "HIGH" | "MODERATE" | "LOW" | "NEUTRAL" | "TRUST" | string;
  evidence_type: "DIRECT_METADATA" | "VENUE_INTELLIGENCE" | "GRAPH_ANALYSIS" | string;
  metadata?: Record<string, unknown>;
}

export interface RiskExplanation {
  opportunity_id?: string | null;
  risk_score: number;
  risk_level: RiskLevel | string;
  risk_confidence: number;
  evidence_sufficiency: "SUFFICIENT" | "INSUFFICIENT" | "MINIMAL" | string;
  is_predatory_flag: boolean;
  summary: string;
  positive_trust_signals: RiskEvidenceItem[];
  suspicious_signals: RiskEvidenceItem[];
  neutral_signals: RiskEvidenceItem[];
  graph_signals: RiskEvidenceItem[];
  venue_signals: RiskEvidenceItem[];
  publisher_signals: RiskEvidenceItem[];
  evidence_items: RiskEvidenceItem[];
  risk_reasons: string[];
  provenance_summary: Record<string, number>;
  limitations: string[];
  gross_negative_score: number;
  trust_mitigation_score: number;
  resolved_entity?: Record<string, unknown> | null;
}

// ── Deadline Intelligence Types (Phase 2.7F) ────────────────────────────────

export type DeadlineType =
  | "SUBMISSION"
  | "ABSTRACT"
  | "NOTIFICATION"
  | "CAMERA_READY"
  | "REGISTRATION"
  | "EVENT_START"
  | "EVENT_END"
  | "UNKNOWN";

export type DeadlineTemporalStatus =
  | "UPCOMING"
  | "DUE_TODAY"
  | "EXPIRED"
  | "MISSING"
  | "INVALID"
  | "AMBIGUOUS";

export type UrgencyTier =
  | "CRITICAL"
  | "URGENT"
  | "APPROACHING"
  | "DISTANT"
  | "DUE_TODAY"
  | "EXPIRED"
  | "UNKNOWN";

export type ConflictState =
  | "NO_CONFLICT"
  | "EQUIVALENT_SOURCES"
  | "SOURCE_CONFLICT"
  | "SUPERSEDED"
  | "INSUFFICIENT_EVIDENCE";

export type RevisionClassification =
  | "INITIAL"
  | "UNCHANGED"
  | "EXTENDED"
  | "MOVED_EARLIER"
  | "REPLACED"
  | "RETRACTED"
  | "CONFLICTING"
  | "EQUIVALENT";

export interface DeadlineEvidence {
  deadline_type: DeadlineType | string;
  raw_value?: string | null;
  raw_text?: string | null;
  source: string;
  source_url?: string | null;
  source_field: string;
  extraction_method: string;
  confidence: number;
  provenance: string;
  is_present: boolean;
  precision: string;
  timezone_indicator: string;
  parsed_year?: number | null;
  parsed_month?: number | null;
  parsed_day?: number | null;
  parsed_time_str?: string | null;
  is_ambiguous: boolean;
  metadata?: Record<string, unknown>;
}

export interface NormalizedDeadline {
  deadline_type: DeadlineType | string;
  local_date?: string | null;
  local_time?: string | null;
  timezone_name?: string | null;
  timezone_offset?: string | null;
  normalized_utc?: string | null;
  utc_deadline?: string | null;
  is_aoe?: boolean;
  precision?: string;
  timezone_source?: string;
  normalization_confidence?: number;
  normalization_status?: string;
  is_end_of_day_inferred?: boolean;
  source_evidence?: DeadlineEvidence | null;
  metadata?: Record<string, unknown>;
}

export interface DeadlineAssessment {
  deadline_type: DeadlineType | string;
  reference_time: string;
  normalized_deadline?: NormalizedDeadline | null;
  status: DeadlineTemporalStatus | string;
  urgency_tier: UrgencyTier | string;
  urgency_score: number;
  seconds_remaining?: number | null;
  minutes_remaining?: number | null;
  hours_remaining?: number | null;
  days_remaining?: number | null;
  confidence: number;
  explanation: string;
  metadata?: Record<string, unknown>;
}

export interface DeadlineObservation {
  opportunity_id?: string | null;
  deadline_type: DeadlineType | string;
  raw_value?: string | null;
  normalized_deadline?: NormalizedDeadline | null;
  source: string;
  source_url?: string | null;
  observation_time?: string | null;
  provenance: string;
  extraction_method: string;
  authority_tier: number;
  normalization_confidence: number;
  source_confidence: number;
  is_current: boolean;
  is_retracted: boolean;
  retraction_evidence?: string | null;
  metadata?: Record<string, unknown>;
}

export interface DeadlineRevision {
  deadline_type: DeadlineType | string;
  classification: RevisionClassification | string;
  days_diff?: number | null;
  hours_diff?: number | null;
  explanation: string;
  previous_observation?: DeadlineObservation | null;
  current_observation: DeadlineObservation;
  previous_deadline?: NormalizedDeadline | null;
  current_deadline?: NormalizedDeadline | null;
  metadata?: Record<string, unknown>;
}

export interface CanonicalDeadlineView {
  deadline_type: DeadlineType | string;
  canonical_deadline?: NormalizedDeadline | null;
  canonical_assessment?: DeadlineAssessment | null;
  selected_source?: string | null;
  selected_observation?: DeadlineObservation | null;
  all_observations: DeadlineObservation[];
  observations?: DeadlineObservation[];
  revision_history: DeadlineRevision[];
  latest_revision?: DeadlineRevision | null;
  conflict_state: ConflictState | string;
  confidence: number;
  explanation: string;
  unresolved_alternatives: DeadlineObservation[];
  deterministic_explanation: string;
  source_selection_reason?: string | null;
  conflict_reason?: string | null;
  extension_reason?: string | null;
  unresolved_reason?: string | null;
  metadata?: Record<string, unknown>;
}

export interface OpportunityDeadline {
  opportunity_id?: string | null;
  reference_time: string;
  primary_milestone: DeadlineType | string;
  primary_view?: CanonicalDeadlineView | null;
  milestone_views: Record<string, CanonicalDeadlineView>;
  summary: string;
  explanation?: string;
  overall_urgency_tier?: UrgencyTier | string;
  overall_urgency_score?: number;
  has_extension: boolean;
  has_conflict: boolean;
  primary_reason: string;
  metadata?: Record<string, unknown>;
}

export type OpportunityListItem = {
  id: string;
  title: string;
  opportunity_type: OpportunityType;
  publisher: string | null;
  organizer: string | null;
  summary: string | null;
  delivery_mode: DeliveryMode;
  location: string | null;
  submission_deadline: string | null; // ISO datetime string
  event_start_date: string | null;
  event_end_date: string | null;
  indexing: string[] | null;
  website_url: string | null;
  submission_url: string | null;
  is_predatory_flag: boolean;
  risk_score: number | null;
  risk_level?: RiskLevel | string | null;
  risk_confidence?: number | null;
  deadline_intelligence?: OpportunityDeadline | null;
  status: OpportunityStatus;
  created_at: string;
  updated_at: string;
};

export type OpportunityListResponse = {
  items: OpportunityListItem[];
  page: number;
  page_size: number;
  total: number;
};

export type OpportunityRead = OpportunityListItem & {
  slug: string | null;
  description: string | null;
  series_name: string | null;
  edition: string | null;
  submission_url: string | null;
  notification_date: string | null;
  camera_ready_deadline: string | null;
  apc_or_fee: Record<string, unknown> | null;
  risk_reasons: string[] | null;
  risk_explanation?: RiskExplanation | null;
  deadline_intelligence?: OpportunityDeadline | null;
  source_id: string | null;
  last_verified_at: string | null;
};
