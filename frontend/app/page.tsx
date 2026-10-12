import type { Metadata } from "next";
import { DiscoverySearch } from "../components/pages/DiscoverySearch";

export const metadata: Metadata = {
  title: "Literature search — ResearchConnect AI",
  description: "Find papers by topic, method or author, and see why each result ranks where it does. Searching is open to everyone.",
};

/**
 * `/` — Literature search: the signed-out landing (with a line on what an account adds, P3) and
 * the search page for everyone. All data fetching happens client-side, in response to a query.
 */
export default function SearchPage() {
  return <DiscoverySearch />;
}
