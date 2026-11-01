import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Research postings — ResearchConnect AI" };

export default function PostingsLayout({ children }: { children: ReactNode }) {
  return children;
}
