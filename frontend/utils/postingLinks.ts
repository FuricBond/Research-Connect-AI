/** On its own: most postings pages need these, and none of the rules in utils/postings.ts. */
export const MY_POSTINGS_HREF = "/postings?view=mine";
export const APPLICANTS_HREF = "/postings/applicants";
export const NEW_POSTING_HREF = "/postings/new";

/** Whether a server answer is at least as new as another of the same object. */
export function isNewer(candidate: { updated_at: string }, than: { updated_at: string }): boolean {
  return (Date.parse(candidate.updated_at) || 0) >= (Date.parse(than.updated_at) || 0);
}
