"use client";

import dynamic from "next/dynamic";

/**
 * P5 — the Evidence and paper panels load with their first opening, not with the page (as the
 * dashboard's "Why?" dialog does, P4): a results page that is only read never downloads them.
 * Render them only while open; unmounting closes the dialog and hands focus back.
 */
export const EvidencePanel = dynamic(() => import("./EvidencePanel").then((loaded) => loaded.EvidencePanel), { ssr: false });
export const PaperPanel = dynamic(() => import("./PaperPanel").then((loaded) => loaded.PaperPanel), { ssr: false });
