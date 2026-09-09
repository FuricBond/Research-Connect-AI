export type AcademicStatus =
  | "UNDERGRADUATE"
  | "POSTGRADUATE"
  | "PHD"
  | "POSTDOC"
  | "FACULTY"
  | "RESEARCHER"
  | "OTHER"
  | "UNKNOWN";

export type CompletenessLevel = "INCOMPLETE" | "BASIC" | "INTERMEDIATE" | "COMPLETE";

export interface ExternalIdentifiers {
  orcid?: string | null;
  openalex_id?: string | null;
  google_scholar_id?: string | null;
  scopus_id?: string | null;
  semantic_scholar_id?: string | null;
  [key: string]: unknown;
}

export interface InstitutionSummary {
  id: string;
  display_name: string;
  ror?: string | null;
  country_code?: string | null;
  institution_type?: string | null;
  homepage_url?: string | null;
}

export interface ResearcherWorkSummary {
  id: string;
  title: string;
  doi?: string | null;
  publication_year?: number | null;
  work_type?: string | null;
  author_position?: string | null;
  is_corresponding: boolean;
  cited_by_count: number;
}

export interface ProfileCompleteness {
  score: number;
  percentage: number;
  level: CompletenessLevel;
  is_complete: boolean;
  missing_fields: string[];
  field_breakdown: Record<string, boolean>;
}

export interface ResearcherProfile {
  id: string;
  user_id: string;
  full_name: string;
  email?: string | null;
  academic_status: AcademicStatus;
  academic_level?: string | null;
  department?: string | null;
  bio?: string | null;
  institution_id?: string | null;
  institution_name?: string | null;
  institution?: InstitutionSummary | null;
  canonical_researcher_id?: string | null;
  orcid?: string | null;
  openalex_id?: string | null;
  external_identifiers: ExternalIdentifiers;
  keywords: string[];
  target_opportunity_types: string[];
  completeness: ProfileCompleteness;
  works_count: number;
  created_at: string;
  updated_at: string;
}

export interface ResearcherProfileCreatePayload {
  full_name: string;
  email: string;
  institution_name?: string | null;
  institution_id?: string | null;
  department?: string | null;
  academic_status?: AcademicStatus;
  academic_level?: string | null;
  bio?: string | null;
  orcid?: string | null;
  openalex_id?: string | null;
  external_identifiers?: ExternalIdentifiers;
  keywords?: string[];
  target_opportunity_types?: string[];
}

export interface ResearcherProfileUpdatePayload {
  full_name?: string | null;
  institution_name?: string | null;
  institution_id?: string | null;
  department?: string | null;
  academic_status?: AcademicStatus | null;
  academic_level?: string | null;
  bio?: string | null;
  orcid?: string | null;
  openalex_id?: string | null;
  external_identifiers?: ExternalIdentifiers | null;
  keywords?: string[] | null;
  target_opportunity_types?: string[] | null;
}
