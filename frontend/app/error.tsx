"use client";

import { ErrorState } from "../components/ui/State/State";

/**
 * Something on a page failed while rendering, or a part of it could not be downloaded (it is loaded
 * on demand, and a connection can drop). The page says so in the shell, instead of the framework's
 * bare error screen, and Try again renders it afresh without leaving it.
 */
export default function PageError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorState announce headingLevel={1} title="This page could not be shown" description="Something went wrong on our side. Nothing you saved has been lost." onRetry={reset} />;
}
