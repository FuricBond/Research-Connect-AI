"use client";

import { Suspense } from "react";
import { PostingsPage } from "../../components/postings/PostingsPage";
import { SkeletonList } from "../../components/ui/State/State";

/** Research postings: Discover, and My postings at `?view=mine` (P9). The view lives in the address. */
export default function PostingsRoute() {
  return (
    <Suspense fallback={<SkeletonList rows={3} lines={3} label="Loading research postings" />}>
      <PostingsPage />
    </Suspense>
  );
}
