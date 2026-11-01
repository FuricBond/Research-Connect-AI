import type { Metadata } from "next";
import type { ReactNode } from "react";

/** A client page: this is its title until the posting's own title arrives. */
export const metadata: Metadata = { title: "Research posting — ResearchConnect AI" };

export default function PostingLayout({ children }: { children: ReactNode }) {
  return children;
}
