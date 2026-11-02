/**
 * Audit VIS-02 — what the visual suite may reorder in an API answer: only true ties, whose order the
 * API leaves to each seed's random ids. Everything the API actually ranks stays where it put it, so
 * a sorting or ranking regression shows up as a difference in the screenshots.
 */
const DAY = 86_400_000;

/**
 * How far to move an API answer's dates, in whole days. With the time of day in the distance, a date
 * stored at midnight landed on the day before when the suite ran after 12:00 UTC, so the same screen
 * differed by the clock alone.
 */
export function wholeDaysBetween(from: number, to: number): number {
  return (Math.floor(to / DAY) - Math.floor(from / DAY)) * DAY;
}

export type Ranked = { rank: number; final_score: number; opportunity: { title: string } };

type Posting = { title: string; created_at?: string; updated_at?: string };

/** Sorts each run of adjacent items with the same key by title. The runs themselves never move. */
function sortTiesOnly<T>(items: T[], key: (item: T) => unknown, title: (item: T) => string): T[] {
  const result: T[] = [];
  let run: T[] = [];
  const flush = () => {
    run.sort((a, b) => title(a).localeCompare(title(b)));
    result.push(...run);
    run = [];
  };
  for (const item of items) {
    if (run.length > 0 && key(run[0]) !== key(item)) flush();
    run.push(item);
  }
  flush();
  return result;
}

/**
 * Postings, tied on the field the request sorted by (`sort_by`, or the endpoint's default). Compared
 * on the API's own timestamps, before the suite moved every date to noon.
 */
export function normalizePostings<T>(original: Posting[], shown: T[], url: string): T[] {
  const parsed = new URL(url);
  const field = (parsed.searchParams.get("sort_by") ?? (parsed.pathname.endsWith("/mine") ? "updated_at" : "created_at")) as keyof Posting;
  const pairs = original.map((posting, index) => ({ posting, shown: shown[index] }));
  return sortTiesOnly(pairs, (pair) => pair.posting[field], (pair) => pair.posting.title).map((pair) => pair.shown);
}

/** Recommendations, tied on their score to six places. The rank numbers stay in order. */
export function normalizeRecommendations<T extends Ranked>(items: T[]): T[] {
  const ranks = items.map((item) => item.rank);
  const sorted = sortTiesOnly(items, (item) => item.final_score.toFixed(6), (item) => item.opportunity.title);
  return sorted.map((item, index) => ({ ...item, rank: ranks[index] }));
}
