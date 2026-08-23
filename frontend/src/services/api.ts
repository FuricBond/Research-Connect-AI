import type {
  OpportunityListResponse,
  OpportunityRead,
} from "../types/opportunity";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export type OpportunityFilters = {
  search?: string;
  opportunity_type?: string;
  status?: string;
  delivery_mode?: string;
  upcoming?: boolean;
  sort?: "newest" | "deadline" | "title";
  page?: number;
  page_size?: number;
};

export async function fetchOpportunities(
  filters: OpportunityFilters = {}
): Promise<OpportunityListResponse> {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.opportunity_type) params.set("opportunity_type", filters.opportunity_type);
  if (filters.status) params.set("status", filters.status);
  if (filters.delivery_mode) params.set("delivery_mode", filters.delivery_mode);
  if (filters.upcoming) params.set("upcoming", "true");
  if (filters.sort) params.set("sort", filters.sort);
  if (filters.page) params.set("page", String(filters.page));
  if (filters.page_size) params.set("page_size", String(filters.page_size));

  const query = params.toString();
  return fetchJson<OpportunityListResponse>(
    `/api/opportunities${query ? `?${query}` : ""}`
  );
}

export async function fetchOpportunity(id: string): Promise<OpportunityRead> {
  return fetchJson<OpportunityRead>(`/api/opportunities/${id}`);
}
