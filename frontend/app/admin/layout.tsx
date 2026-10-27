import type { Metadata } from "next";
import type { ReactNode } from "react";

/** P10: the administration pages are client pages, so their titles are set by layouts. */
export const metadata: Metadata = { title: "Administration — ResearchConnect AI" };

export default function AdminLayout({ children }: { children: ReactNode }) {
  return children;
}
