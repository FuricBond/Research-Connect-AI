"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";
import { RequireAuth } from "../../components/auth/RequireAuth";
import { SkeletonList } from "../../components/ui/State/State";
import { preloadForSession } from "../../utils/preloadForSession";

const load = () => import("../../components/workspace/WorkspacePage");
preloadForSession(load);
const WorkspacePage = dynamic(() => load().then((loaded) => loaded.WorkspacePage), { ssr: false, loading: () => <SkeletonList rows={4} lines={2} label="Loading your workspace" /> });

/** /workspace (P7): the calls you track, list first (components/workspace). */
export default function WorkspacePageRoute() {
  return (
    <RequireAuth roles={["STUDENT", "FACULTY"]}>
      {/* The status, sort and search live in the address (useAddressSearch). */}
      <Suspense fallback={null}>
        <WorkspacePage />
      </Suspense>
    </RequireAuth>
  );
}
