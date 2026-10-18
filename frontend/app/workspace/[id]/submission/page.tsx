import { redirect } from "next/navigation";

interface PageProps {
  params: Promise<{ id: string }>;
}

/**
 * P7 — the submission workflow is the item's Submission tab now (plan §13). The old address
 * keeps working for bookmarks and links in notifications.
 */
export default async function SubmissionRedirect({ params }: PageProps) {
  const { id } = await params;
  redirect(`/workspace/${encodeURIComponent(id)}?tab=submission`);
}
