"use client";

import { Suspense, use } from "react";
import { RequireAuth } from "../../../components/auth/RequireAuth";
import { ItemPage } from "../../../components/workspace/item/ItemPage";

interface PageProps {
  params: Promise<{ id: string }>;
}

/** P7 — a tracked call with its tabs (components/workspace/item). */
export default function WorkspaceItemRoute({ params }: PageProps) {
  const { id } = use(params);
  return (
    <RequireAuth>
      <Suspense fallback={null}>
        <ItemPage key={id} id={id} />
      </Suspense>
    </RequireAuth>
  );
}
