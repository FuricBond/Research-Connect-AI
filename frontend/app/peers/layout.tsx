import type { Metadata } from "next";
import type { ReactNode } from "react";

/** P6: the page is a client page; this is its title. */
export const metadata: Metadata = {
  title: "Find peers — ResearchConnect AI",
};

export default function PeersLayout({ children }: { children: ReactNode }) {
  return children;
}
