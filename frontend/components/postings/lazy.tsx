"use client";

import dynamic from "next/dynamic";
import { SkeletonList, SkeletonText } from "../ui/State/State";

/**
 * P9 — the faculty-only parts of the postings pages load when they are first needed (as P5's
 * lazyPanels and P7's lazyTabs), so a visitor or a student reading /postings or a posting's page
 * never downloads My postings, the applicant review or the confirmations. (The author's controls
 * on a posting's page come with the page: they sit above the posting, so arriving late they would
 * push it down.)
 */
export const MyPostings = dynamic(() => import("./MyPostings").then((loaded) => loaded.MyPostings), {
  ssr: false,
  loading: () => <SkeletonList rows={4} lines={2} label="Loading your postings" />,
});

export const Applications = dynamic(() => import("./PostingAuthor").then((loaded) => loaded.Applications), {
  ssr: false,
  loading: () => <SkeletonList rows={2} lines={2} label="Loading the applications" announce={false} />,
});

/** A posting's application form, once "Apply now" is pressed. */
export const ApplyForm = dynamic(() => import("./ApplyForm").then((loaded) => loaded.ApplyForm), {
  ssr: false,
  loading: () => <SkeletonList rows={2} lines={2} label="Loading the application form" />,
});

/** The editor's preview: beside or below the form, never above it, so its arrival moves nothing. */
export const PreviewCard = dynamic(() => import("./PostingCard").then((loaded) => loaded.PostingCard), {
  ssr: false,
  loading: () => <SkeletonText title lines={3} />,
});

// A confirmation is shown only when asked for; until its code arrives nothing is shown or sent.
export const NotSelectedDialog = dynamic(() => import("./ConfirmDialogs").then((loaded) => loaded.NotSelectedDialog), { ssr: false });
export const CancelPostingDialog = dynamic(() => import("./ConfirmDialogs").then((loaded) => loaded.CancelPostingDialog), { ssr: false });
export const DeleteDraftDialog = dynamic(() => import("./ConfirmDialogs").then((loaded) => loaded.DeleteDraftDialog), { ssr: false });
