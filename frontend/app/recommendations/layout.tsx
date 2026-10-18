import type { Metadata } from "next";
import type { ReactNode } from "react";

/** P6: the recommendations page is a client page; this is its title. */
export const metadata: Metadata = {
  title: "Recommendations — ResearchConnect AI",
  description: "Calls for papers matched to your research and preferences, with the reasons behind each match and the controls over them.",
};

export default function RecommendationsLayout({ children }: { children: ReactNode }) {
  return children;
}
