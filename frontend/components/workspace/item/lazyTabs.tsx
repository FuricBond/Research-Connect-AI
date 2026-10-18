"use client";

import dynamic from "next/dynamic";
import { SkeletonList } from "../../ui/State/State";

/**
 * P7 — the item's tabs other than Overview load with their first opening, not with the page (as
 * P5's lazyPanels): an item only glanced at never downloads the submission workflow.
 */
const loading = () => <SkeletonList rows={3} lines={2} label="Loading" />;

export const TasksPanel = dynamic(() => import("./TasksPanel").then((loaded) => loaded.TasksPanel), { ssr: false, loading });
export const MembersPanel = dynamic(() => import("./MembersPanel").then((loaded) => loaded.MembersPanel), { ssr: false, loading });
export const ActivityPanel = dynamic(() => import("./ActivityPanel").then((loaded) => loaded.ActivityPanel), { ssr: false, loading });
export const SubmissionPanel = dynamic(() => import("../submission/SubmissionPanel").then((loaded) => loaded.SubmissionPanel), { ssr: false, loading });
