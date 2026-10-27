"use client";

import { ResearchDataMonitor } from "../../../components/admin/ResearchDataMonitor";
import { RequireAuth } from "../../../components/auth/RequireAuth";
import { PageHeader } from "../../../components/ui/PageHeader/PageHeader";

/** P10 — the research data monitor in full (plan §15): the title first, the monitor beneath it. */
export default function ResearchDataPage() {
  return (
    <RequireAuth roles={["ADMIN"]}>
      <PageHeader title="Research data" description="Whether the scheduled refresh is keeping the paper corpus up to date: its state, its recent runs and what each lane added." />
      <ResearchDataMonitor />
    </RequireAuth>
  );
}
