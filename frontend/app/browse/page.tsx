import type { Metadata } from "next";
import { OpportunityList } from "../../components/OpportunityList";
import { PageHeader } from "../../components/ui/PageHeader/PageHeader";

export const metadata: Metadata = {
  title: "Calls for papers — ResearchConnect AI",
  description:
    "Browse calls for papers from conferences, journals, workshops and special issues, with each call's deadline and venue risk.",
};

/**
 * /browse — Calls for papers (P5): search, filters, sort and pages in the address; each call
 * links to its own page, /calls/[id].
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
