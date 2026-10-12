import type { Metadata } from "next";
import { Search } from "lucide-react";
import { ButtonLink } from "../components/ui/Button/Button";
import { ErrorState } from "../components/ui/State/State";

export const metadata: Metadata = {
  title: "Page not found — ResearchConnect AI",
};

/**
 * Next.js not-found.tsx — shown for unmatched routes. P3: the design system's not-found state,
 * as the page's one h1, with the way back to search (FRONTEND_REDESIGN_PLAN.md §21).
 */
export default function NotFound() {
  return (
    <ErrorState
      kind="not-found"
      headingLevel={1}
      title="Page not found"
      description="The address may be mistyped, or the page may have moved. Check it, or start again from search."
      actions={
        <ButtonLink href="/" variant="primary" leadingIcon={<Search size={16} aria-hidden="true" />}>
          Go to search
        </ButtonLink>
      }
    />
  );
}
