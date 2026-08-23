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
  source_id: string | null;
  last_verified_at: string | null;
};
