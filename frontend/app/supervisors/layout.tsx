import type { Metadata } from "next";
import type { ReactNode } from "react";

/** P6: the page is a client page; this is its title. */
export const metadata: Metadata = {
  title: "Find a supervisor — ResearchConnect AI",
};

export default function SupervisorsLayout({ children }: { children: ReactNode }) {
  return children;
}
