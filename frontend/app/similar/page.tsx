import type { Metadata } from "next";
import { SimilarResearchPage } from "../../components/pages/SimilarResearch";

export const metadata: Metadata = {
  title: "Similar Research — ResearchConnect AI",
  description:
    "Discover academically similar research works using semantic embedding distance and canonical topic DAG proximity.",
};

/**
 * /similar route — Similar Research Explorer (tab: similar)
 *
 * Reads the selected ResearchWorkRead from sessionStorage, hydrated client-side.
 */
export default function SimilarPage() {
  return <SimilarResearchPage />;
}
