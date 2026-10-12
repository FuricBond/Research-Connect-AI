import type { Metadata } from "next";
import type { ReactNode } from "react";

/** P4: the home is a client page, so its title is set here. */
export const metadata: Metadata = {
  title: "Home — ResearchConnect AI",
};

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return children;
}
