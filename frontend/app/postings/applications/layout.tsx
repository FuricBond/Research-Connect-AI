import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "My applications — ResearchConnect AI" };

export default function ApplicationsLayout({ children }: { children: ReactNode }) {
  return children;
}
