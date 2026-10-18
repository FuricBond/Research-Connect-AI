"use client";

import { Suspense } from "react";
import { RequireAuth } from "../../components/auth/RequireAuth";
import { WorkspacePage } from "../../components/workspace/WorkspacePage";

/** /workspace (P7): the calls you track, list first (components/workspace). */
export default function WorkspacePageRoute() {
  return (
    <RequireAuth>
      {/* The status, sort and search live in the address (useAddressSearch). */}
      <Suspense fallback={null}>
        <WorkspacePage />
      </Suspense>
    </RequireAuth>
  );
}
