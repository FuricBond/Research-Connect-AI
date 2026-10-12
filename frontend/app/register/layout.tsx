import type { Metadata } from "next";
import type { ReactNode } from "react";

/** P3: the registration page is a client component, so its title is set here. */
export const metadata: Metadata = {
  title: "Create an account — ResearchConnect AI",
};

export default function RegisterLayout({ children }: { children: ReactNode }) {
  return children;
}
