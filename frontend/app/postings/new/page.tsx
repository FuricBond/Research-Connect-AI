"use client";

import { RequireAuth } from "../../../components/auth/RequireAuth";
import { PostingEditor } from "../../../components/postings/PostingEditor";

/** P9 — writing a posting (FACULTY and ADMIN accounts may author; the server enforces it). */
export default function NewPostingPage() {
  return (
    <RequireAuth roles={["FACULTY", "ADMIN"]}>
      <PostingEditor />
    </RequireAuth>
  );
}
