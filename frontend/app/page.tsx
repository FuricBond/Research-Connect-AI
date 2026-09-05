import type { Metadata } from "next";
import { DiscoverySearch } from "../components/pages/DiscoverySearch";

export const metadata: Metadata = {
  title: "Literature Search — ResearchConnect AI",
  description:
    "Search peer-reviewed academic literature using multi-channel hybrid intelligence combining semantic embeddings, full-text lexical ranking, and canonical topic proximity.",
};

/**
 * Home page — Literature Search (tab: search)
 *
 * This is a Client Component page. All data fetching happens client-side
 * in response to user search queries. No server-side data fetching needed.
 */
export default function SearchPage() {
  return <DiscoverySearch />;
}
