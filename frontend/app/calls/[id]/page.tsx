"use client";

import { useParams } from "next/navigation";
import { CallDetail } from "../../../components/calls/CallDetail";

/**
 * /calls/[id] — one call for papers (P5). Public, like the list it comes from; the page fetches
 * the call on the client like every other page, and says "not found" for an id the API does not
 * know (or that cannot be an id at all, without asking).
 */
export default function CallPage() {
  const params = useParams<{ id: string }>();
  const raw = typeof params?.id === "string" ? params.id : "";
  let id = raw;
  try {
    id = decodeURIComponent(raw);
  } catch {
    // A malformed escape is simply not an id; the page says "not found".
  }
  // A new call starts afresh (its own requests, its own calendar message).
  return <CallDetail key={id} id={id} />;
}
