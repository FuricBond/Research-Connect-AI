import { Loader2 } from "lucide-react";

/**
 * Next.js loading.tsx — shown automatically during page transitions.
 * Server Component (no "use client" needed).
 */
export default function Loading() {
  return (
    <div className="state-container loading-state" role="status" aria-label="Loading">
      <Loader2 size={28} className="spin" />
      <p>Loading...</p>
    </div>
  );
}
