import type { Metadata } from "next";
import type { ReactNode } from "react";

/** P7: the reading list is a client page; this is its title. */
export const metadata: Metadata = {
  title: "Reading list — ResearchConnect AI",
  description: "Papers you saved, with what you are reading, private notes and BibTeX export.",
};

export default function ReadingListLayout({ children }: { children: ReactNode }) {
  return children;
}
