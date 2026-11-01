"use client";

import dynamic from "next/dynamic";
import { Suspense, use } from "react";
import { RequireAuth } from "../../../components/auth/RequireAuth";
import { SkeletonList } from "../../../components/ui/State/State";
import { preloadForSession } from "../../../utils/preloadForSession";

const load = () => import("../../../components/workspace/item/ItemPage");
preloadForSession(load);
const ItemPage = dynamic(() => load().then((loaded) => loaded.ItemPage), { ssr: false, loading: () => <SkeletonList rows={4} lines={2} label="Loading this call" /> });

interface PageProps {
  params: Promise<{ id: string }>;
}

/** P7 — a tracked call with its tabs (components/workspace/item). */
export default function WorkspaceItemRoute({ params }: PageProps) {
  const { id } = use(params);
  return (
    <RequireAuth roles={["STUDENT", "FACULTY"]}>
      <Suspense fallback={null}>
        <ItemPage key={id} id={id} />
      </Suspense>
    </RequireAuth>
  );
}
