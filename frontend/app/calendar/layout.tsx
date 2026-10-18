import type { Metadata } from "next";
import type { ReactNode } from "react";

/** P7: the calendar is a client page; this is its title. */
export const metadata: Metadata = {
  title: "Calendar — ResearchConnect AI",
  description: "The deadlines of the calls you track and your own research milestones, with .ics export.",
};

export default function CalendarLayout({ children }: { children: ReactNode }) {
  return children;
}
