"use client";

import { Suspense } from "react";
import { RequireAuth } from "../../components/auth/RequireAuth";
import { ReadingListPage } from "../../components/reading-list/ReadingListPage";

/** P7 — saved papers (components/reading-list/ReadingListPage). */
export default function ReadingListPageRoute() {
  return (
    <RequireAuth>
      <Suspense fallback={null}>
        <ReadingListPage />
      </Suspense>
    </RequireAuth>
  );
}
