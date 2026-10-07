import type { Metadata } from "next";
import { OpportunityList } from "../../components/OpportunityList";
import { PageHeader } from "../../components/ui/PageHeader/PageHeader";
import "../../styles/opportunities.css";

export const metadata: Metadata = {
  title: "Browse All Calls — ResearchConnect AI",
  description:
    "Browse all academic calls for papers, conferences, journals, workshops, and special issues tracked by ResearchConnect AI.",
};

/**
 * /browse route — Browse All Calls (tab: all_opportunities)
 */
export default function BrowsePage() {
  return (
    <>
      <PageHeader
        title="Calls for papers"
        description="Conferences, journals, workshops and special issues accepting submissions, with each call's deadline and venue risk."
      />
      <OpportunityList />
    </>
  );
}
