import type { Metadata } from "next";
import type { ReactNode } from "react";

/** P7: the workspace pages are client pages; this is their title (an item sets its own). */
export const metadata: Metadata = {
  title: "Workspace — ResearchConnect AI",
  description: "The calls for papers you are tracking, their deadlines, tasks and submissions.",
};

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  return children;
}
