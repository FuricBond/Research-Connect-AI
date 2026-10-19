"use client";

import { useParams } from "next/navigation";
import { PostingDetail } from "../../../components/postings/PostingDetail";

/** A posting's own page; for its author also where it is managed and its applicants reviewed (P9). */
export default function PostingDetailPage() {
  const params = useParams<{ id: string }>();
  return <PostingDetail postingId={params?.id ?? null} />;
}
