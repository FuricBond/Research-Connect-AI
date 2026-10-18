import type { Metadata } from "next";
import type { ReactNode } from "react";

/** P6: the profile is a client page; this is its title. */
export const metadata: Metadata = {
  title: "Your profile — ResearchConnect AI",
  description: "Your researcher profile: summary, publications, research topics and preferences.",
};

export default function ResearcherLayout({ children }: { children: ReactNode }) {
  return children;
}
