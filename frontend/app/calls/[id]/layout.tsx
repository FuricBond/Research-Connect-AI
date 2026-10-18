import type { Metadata } from "next";
import type { ReactNode } from "react";

/** P5: the call page is a client page; this is its title until the call's own title arrives. */
export const metadata: Metadata = {
  title: "Call for papers — ResearchConnect AI",
};

export default function CallLayout({ children }: { children: ReactNode }) {
  return children;
}
