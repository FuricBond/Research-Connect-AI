"use client";

import dynamic from "next/dynamic";
import { RequireAuth } from "../../../components/auth/RequireAuth";
import { SkeletonList } from "../../../components/ui/State/State";
import { preloadForSession } from "../../../utils/preloadForSession";

const load = () => import("../../../components/postings/PostingEditor");
preloadForSession(load);
const PostingEditor = dynamic(() => load().then((loaded) => loaded.PostingEditor), { ssr: false, loading: () => <SkeletonList rows={4} lines={2} label="Loading the editor" /> });

/** P9 — writing a posting (FACULTY and ADMIN accounts may author; the server enforces it). */
export default function NewPostingPage() {
  return (
    <RequireAuth roles={["FACULTY", "ADMIN"]}>
      <PostingEditor />
    </RequireAuth>
  );
}
