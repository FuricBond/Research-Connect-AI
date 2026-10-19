import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Applicants — ResearchConnect AI" };

export default function ApplicantsLayout({ children }: { children: ReactNode }) {
  return children;
}
