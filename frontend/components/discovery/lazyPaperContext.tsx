"use client";

import dynamic from "next/dynamic";
import { SkeletonList } from "../ui/State/State";

/**
 * P12 — what the paper tools show when opened without a paper. Arriving from a paper (the usual way)
 * never downloads it.
 */
export const PaperContextRequired = dynamic(() => import("./PaperContextRequired").then((loaded) => loaded.PaperContextRequired), {
  ssr: false,
  loading: () => <SkeletonList rows={3} lines={2} label="Loading" />,
});
