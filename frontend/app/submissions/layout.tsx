import type { Metadata } from "next";
import type { ReactNode } from "react";

/** P7: the submissions page is a client page; this is its title. */
export const metadata: Metadata = {
  title: "Submissions — ResearchConnect AI",
  description: "Every manuscript you are tracking, from first draft to decision.",
};

export default function SubmissionsLayout({ children }: { children: ReactNode }) {
  return children;
}
