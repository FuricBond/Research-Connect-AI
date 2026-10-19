"use client";

import { useApiResource } from "../../hooks/useApiResource";
import { fetchPosting } from "../../services/api";
import { MY_POSTINGS_HREF } from "../../utils/postings";
import { ButtonLink } from "../ui/Button/Button";
import { ErrorState, SkeletonList, SkeletonText } from "../ui/State/State";
import { PostingEditor } from "./PostingEditor";
import styles from "./Faculty.module.css";

/**
 * P9 — `/postings/[id]/edit`: the editor, filled from the posting as the server has it. Only its
 * author may edit (the server refuses anyone else with 403, and hides other people's drafts), and
 * an archived posting can no longer change; both are said instead of showing a form that would
 * be refused.
 */
export function EditPosting({ postingId }: { postingId: string | null }) {
  const resource = useApiResource(postingId ? `posting:${postingId}:edit` : null, (signal) => fetchPosting(postingId!, signal));
  const posting = resource.data;

  if (resource.status === "error") {
    const missing = resource.error?.kind === "not-found";
    return (
      <ErrorState
        headingLevel={1}
        kind={missing ? "not-found" : resource.error?.kind === "network" ? "offline" : "failed"}
        title={missing ? "This posting is not available" : "This posting could not be loaded"}
        onRetry={missing ? undefined : resource.retry}
        actions={<ButtonLink href={MY_POSTINGS_HREF}>Go to my postings</ButtonLink>}
      />
    );
  }
  if (!posting) {
    return (
      <div aria-busy="true" className={styles.detailLoading}>
        <SkeletonText title lines={2} />
        <SkeletonList rows={3} lines={2} label="Loading the posting" />
      </div>
    );
  }
  if (!posting.is_owner) {
    return (
      <ErrorState
        kind="permission"
        headingLevel={1}
        title="Only the posting’s author can edit it."
        actions={<ButtonLink href={`/postings/${posting.id}`}>Open the posting</ButtonLink>}
      />
    );
  }
  if (posting.status === "ARCHIVED") {
    return (
      <ErrorState
        kind="invalid"
        headingLevel={1}
        title="An archived posting can no longer be edited."
        actions={<ButtonLink href={`/postings/${posting.id}`}>Open the posting</ButtonLink>}
      />
    );
  }
  return <PostingEditor posting={posting} />;
}
