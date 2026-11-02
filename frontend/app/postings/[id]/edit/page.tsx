"use client";

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { RequireAuth } from "../../../../components/auth/RequireAuth";
import { SkeletonList } from "../../../../components/ui/State/State";
import { preloadForSession } from "../../../../utils/preloadForSession";

const load = () => import("../../../../components/postings/EditPosting");
preloadForSession(load);
const EditPosting = dynamic(() => load().then((loaded) => loaded.EditPosting), { ssr: false, loading: () => <SkeletonList rows={4} lines={2} label="Loading the editor" /> });

/** P9 — editing a posting, for its author. */
export default function EditPostingPage() {
  const params = useParams<{ id: string }>();
  return (
    <RequireAuth roles={["FACULTY"]}>
      <EditPosting postingId={params?.id ?? null} />
    </RequireAuth>
  );
}
