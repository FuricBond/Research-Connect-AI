/**
 * The API client. Everything is imported from here; each area of the API has its own module in
 * services/api/ because webpack keeps, per module, every function any route uses, so one large
 * file put all of them on every page (audit PERF-04).
 */
export * from "./api/client";
export * from "./api/auth";
export * from "./api/admin";
export * from "./api/opportunities";
export * from "./api/discovery";
export * from "./api/similarResearch";
export * from "./api/venueMatching";
export * from "./api/researchers";
export * from "./api/preferences";
export * from "./api/candidates";
export * from "./api/ranking";
export * from "./api/feedback";
export * from "./api/history";
export * from "./api/explainability";
export * from "./api/workspace";
export * from "./api/submissions";
export * from "./api/submissionDocuments";
export * from "./api/calendar";
export * from "./api/notifications";
export * from "./api/notificationsLatest";
export * from "./api/collaboration";
export * from "./api/invitations";
export * from "./api/workspaceMembers";
export * from "./api/intelligence";
export * from "./api/explicitPreferences";
export * from "./api/personalizationScoring";
export * from "./api/interactions";
export * from "./api/adaptiveSignals";
export * from "./api/calibration";
export * from "./api/quality";
export * from "./api/governance";
export * from "./api/transparency";
export * from "./api/postings";
export * from "./api/postingFit";
export * from "./api/applications";
export * from "./api/peers";
export * from "./api/supervisors";
export * from "./api/readingList";
