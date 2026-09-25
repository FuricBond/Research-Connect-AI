/**
 * Phase 5.12 — Peer & Co-Author Discovery.
 *
 * Mirrors backend/app/schemas/researcher_discovery.py.
 *
 * Two things are decided entirely server-side and must only be rendered here, never recomputed:
 * the match score with its signal breakdown, and which of a peer's fields are disclosed. A peer's
 * `institution` or `contact_email` arriving as null means they chose not to show it.
 */

export type CollaborationStatus =
  | "SEEKING_COLLABORATORS"
  | "OPEN_TO_ENQUIRIES"
  | "SELECTIVELY_AVAILABLE"
  | "NOT_AVAILABLE";

export type CollaborationInterest =
  | "CO_AUTHORSHIP"
  | "JOINT_GRANT"
  | "DATA_SHARING"
  | "METHOD_EXCHANGE"
  | "STUDENT_CO_SUPERVISION"
  | "PEER_REVIEW_EXCHANGE"
  | "MENTORSHIP";

export type PeerMatchTier = "STRONG" | "MODERATE" | "EXPLORATORY" | "INSUFFICIENT_EVIDENCE";

export type PeerSignalType =
  | "SHARED_EXPERTISE"
  | "COMPLEMENTARY_EXPERTISE"
  | "TAXONOMY_PROXIMITY"
  | "METHODOLOGY_OVERLAP"
  | "COLLABORATION_READINESS"
  | "INSTITUTION_DIVERSITY";

export interface DiscoverySettings {
  profile_id: string;
  is_discoverable: boolean;
  collaboration_status: CollaborationStatus;
  collaboration_interests: CollaborationInterest[];
  show_institution: boolean;
  show_contact_email: boolean;
  collaboration_note: string | null;
  /** When discoverability was last changed; the record of consent. */
  consent_updated_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface DiscoverySettingsUpdate {
  is_discoverable?: boolean;
  collaboration_status?: CollaborationStatus;
  collaboration_interests?: CollaborationInterest[];
  show_institution?: boolean;
  show_contact_email?: boolean;
  collaboration_note?: string | null;
}

export interface PeerMatchSignal {
  signal_type: PeerSignalType;
  raw_score: number;
  weight: number;
  weighted_contribution: number;
  evidence: string[];
  explanation: string;
}

export interface PeerProfile {
  profile_id: string;
  full_name: string | null;
  /** Null when this researcher chose not to disclose their institution. */
  institution: string | null;
  department: string | null;
  academic_status: string | null;
  /** Null unless this researcher opted to share their email. */
  contact_email: string | null;
  collaboration_status: CollaborationStatus;
  collaboration_interests: CollaborationInterest[];
  collaboration_note: string | null;
}

export interface PeerMatch {
  peer: PeerProfile;
  match_score: number;
  tier: PeerMatchTier;
  confidence: number;
  shared_topics: string[];
  complementary_topics: string[];
  signals: PeerMatchSignal[];
  explanation_reasons: string[];
}

export interface PeerMatchResponse {
  researcher_id: string;
  matches: PeerMatch[];
  total_candidates_evaluated: number;
  returned_count: number;
  algorithm_version: string;
  /** Whether the requesting researcher is themselves discoverable. */
  is_discoverable: boolean;
  data_sufficiency: "SUFFICIENT" | "INSUFFICIENT_PROFILE" | "NO_CANDIDATES";
  /** Present when no matches could be produced, explaining which problem applies. */
  guidance: string | null;
}

export const COLLABORATION_STATUS_LABELS: Record<CollaborationStatus, string> = {
  SEEKING_COLLABORATORS: "Actively seeking collaborators",
  OPEN_TO_ENQUIRIES: "Open to enquiries",
  SELECTIVELY_AVAILABLE: "Selectively available",
  NOT_AVAILABLE: "Not currently available",
};

export const COLLABORATION_INTEREST_LABELS: Record<CollaborationInterest, string> = {
  CO_AUTHORSHIP: "Co-authorship",
  JOINT_GRANT: "Joint grant application",
  DATA_SHARING: "Data sharing",
  METHOD_EXCHANGE: "Method exchange",
  STUDENT_CO_SUPERVISION: "Student co-supervision",
  PEER_REVIEW_EXCHANGE: "Peer review exchange",
  MENTORSHIP: "Mentorship",
};

export const PEER_TIER_LABELS: Record<PeerMatchTier, string> = {
  STRONG: "Strong match",
  MODERATE: "Moderate match",
  EXPLORATORY: "Exploratory",
  INSUFFICIENT_EVIDENCE: "Not enough evidence",
};

export const PEER_SIGNAL_LABELS: Record<PeerSignalType, string> = {
  SHARED_EXPERTISE: "Shared expertise",
  COMPLEMENTARY_EXPERTISE: "Complementary expertise",
  TAXONOMY_PROXIMITY: "Related fields",
  METHODOLOGY_OVERLAP: "Shared methods",
  COLLABORATION_READINESS: "Availability",
  INSTITUTION_DIVERSITY: "Institution",
};

export const ALL_COLLABORATION_INTERESTS: CollaborationInterest[] = [
  "CO_AUTHORSHIP",
  "JOINT_GRANT",
  "DATA_SHARING",
  "METHOD_EXCHANGE",
  "STUDENT_CO_SUPERVISION",
  "PEER_REVIEW_EXCHANGE",
  "MENTORSHIP",
];

export const ALL_COLLABORATION_STATUSES: CollaborationStatus[] = [
  "SEEKING_COLLABORATORS",
  "OPEN_TO_ENQUIRIES",
  "SELECTIVELY_AVAILABLE",
  "NOT_AVAILABLE",
];
