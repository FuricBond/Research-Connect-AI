/**
 * Research refresh (step 4/6) — admin data freshness contract types.
 *
 * These mirror `IngestionRunRead`, `ResearchRefreshStatus` and `IngestionRunListResponse`
 * in `backend/app/schemas/opportunity.py`. Dates arrive as ISO 8601 strings.
 */

export type IngestionRunStatus = "RUNNING" | "COMPLETED" | "FAILED";

/** One ingestion run. `error_message` is a category, never the stored error text. */
export interface IngestionRunRead {
  id: string;
  source_id: string;
  status: IngestionRunStatus;
  /** For a research refresh pass: `research_refresh:{run_tag}:{lane}:{subfield}`. */
  topic: string | null;
  pages_fetched: number;
  records_parsed: number;
  records_valid: number;
  records_invalid: number;
  records_inserted: number;
  records_updated: number;
  records_unchanged: number;
  duplicates_detected: number;
  potential_duplicates_detected: number;
  records_expired: number;
  error_message: string | null;
  metrics_detail: Record<string, number> | null;
  started_at: string;
  completed_at: string | null;
}

/** Data freshness of the scheduled research refresh. */
export interface ResearchRefreshStatus {
  enabled: boolean;
  interval_seconds: number;
  last_run_started_at: string | null;
  /** The newest refresh as a whole; null before the first run. */
  last_run_status: IngestionRunStatus | null;
  works_added_last_24h: number;
  /** Last start plus the interval; null when the refresh is not scheduled. */
  next_run_estimate: string | null;
}

export interface IngestionRunListResponse {
  items: IngestionRunRead[];
  research_refresh: ResearchRefreshStatus;
}
