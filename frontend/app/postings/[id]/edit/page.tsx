"use client";

import { useParams } from "next/navigation";
import { RequireAuth } from "../../../../components/auth/RequireAuth";
import { EditPosting } from "../../../../components/postings/EditPosting";

/** P9 — editing a posting, for its author. */
export default function EditPostingPage() {
  const params = useParams<{ id: string }>();
  return (
    <RequireAuth roles={["FACULTY", "ADMIN"]}>
      <EditPosting postingId={params?.id ?? null} />
    </RequireAuth>
  );
}
