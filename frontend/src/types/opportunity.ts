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
  source_id: string | null;
  last_verified_at: string | null;
};
