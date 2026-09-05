import type { Metadata } from "next";
import { OpportunityMatchesPage } from "../../components/pages/OpportunityMatches";

export const metadata: Metadata = {
  title: "Opportunity Matcher — ResearchConnect AI",
  description:
    "Match and rank academic venues, conferences, journals, and calls for papers by semantic compatibility, publication-type fit, predatory-risk score, and deadline urgency.",
};

/**
 * /opportunities route — Opportunity Matcher (tab: opportunities)
 *
 * Reads the selected ResearchWorkRead from sessionStorage, hydrated client-side.
 */
export default function OpportunitiesPage() {
  return <OpportunityMatchesPage />;
}
