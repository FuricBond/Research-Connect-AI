import type { Metadata } from "next";
import type { ReactNode } from "react";

/** P8: the notifications page is a client page; this is its title. */
export const metadata: Metadata = {
  title: "Notifications — ResearchConnect AI",
};

export default function NotificationsLayout({ children }: { children: ReactNode }) {
  return children;
}
