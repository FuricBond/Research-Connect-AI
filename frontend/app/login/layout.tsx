import type { Metadata } from "next";
import type { ReactNode } from "react";

/** P3: the sign-in page is a client component, so its title is set here. */
export const metadata: Metadata = {
  title: "Sign in — ResearchConnect AI",
};

export default function LoginLayout({ children }: { children: ReactNode }) {
  return children;
}
