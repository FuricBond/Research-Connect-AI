import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Research data — ResearchConnect AI" };

export default function ResearchDataLayout({ children }: { children: ReactNode }) {
  return children;
}
