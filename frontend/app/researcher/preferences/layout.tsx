import type { Metadata } from "next";
import type { ReactNode } from "react";

/** P6: its own title, so it does not take the profile's. */
export const metadata: Metadata = {
  title: "Research preferences — ResearchConnect AI",
};

export default function PreferencesLayout({ children }: { children: ReactNode }) {
  return children;
}
