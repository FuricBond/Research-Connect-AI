/**
 * Audit VIS-02 — the visual suite settles ties and nothing else: an ordering change in what the API
 * decides reaches the screenshots.
 */
import { describe, expect, it } from "vitest";
import { normalizePostings, normalizeRecommendations, wholeDaysBetween } from "../e2e/visual-normalize";

const posting = (title: string, created_at: string) => ({ title, created_at, updated_at: created_at });
const titles = (items: { title: string }[]) => items.map((item) => item.title);
const ranked = (title: string, final_score: number, rank: number) => ({ rank, final_score, opportunity: { title } });

describe("postings", () => {
  const URL_ALL = "http://api/api/v1/postings?limit=20";

  it("settles a tie by title, whatever order the seed's ids gave it", () => {
    const a = [posting("B", "2030-01-01T00:00:00Z"), posting("A", "2030-01-01T00:00:00Z")];
    const b = [posting("A", "2030-01-01T00:00:00Z"), posting("B", "2030-01-01T00:00:00Z")];
    expect(titles(normalizePostings(a, a, URL_ALL))).toEqual(titles(normalizePostings(b, b, URL_ALL)));
  });

  it("leaves what the API sorted exactly where it put it, even against title order", () => {
    const list = [posting("Z newest", "2030-01-03T00:00:00Z"), posting("M", "2030-01-02T00:00:00Z"), posting("A oldest", "2030-01-01T00:00:00Z")];
    expect(titles(normalizePostings(list, list, URL_ALL))).toEqual(["Z newest", "M", "A oldest"]);
  });

  it("shows a sorting regression: a reversed list stays reversed, so the screenshot differs", () => {
    const right = [posting("Z newest", "2030-01-03T00:00:00Z"), posting("A oldest", "2030-01-01T00:00:00Z")];
    const wrong = [...right].reverse();
    expect(titles(normalizePostings(wrong, wrong, URL_ALL))).not.toEqual(titles(normalizePostings(right, right, URL_ALL)));
  });

  it("uses the field the request sorted by", () => {
    const list = [
      { title: "B", created_at: "2030-01-01T00:00:00Z", updated_at: "2030-01-05T00:00:00Z" },
      { title: "A", created_at: "2030-01-01T00:00:00Z", updated_at: "2030-01-04T00:00:00Z" },
    ];
    expect(titles(normalizePostings(list, list, "http://api/api/v1/postings/mine"))).toEqual(["B", "A"]);
    expect(titles(normalizePostings(list, list, "http://api/api/v1/postings"))).toEqual(["A", "B"]);
  });

  it("returns the shown answer, not the one it compared", () => {
    const original = [posting("B", "2030-01-01T00:00:00Z"), posting("A", "2030-01-01T00:00:00Z")];
    const shown = [{ title: "B", moved: true }, { title: "A", moved: true }];
    expect(normalizePostings(original, shown, URL_ALL)).toEqual([{ title: "A", moved: true }, { title: "B", moved: true }]);
  });
});

describe("recommendations", () => {
  it("settles only equal scores, and keeps the ranks in order", () => {
    const list = [ranked("Z", 0.9, 1), ranked("C", 0.5, 2), ranked("B", 0.5, 3), ranked("A", 0.1, 4)];
    const out = normalizeRecommendations(list);
    expect(out.map((item) => item.opportunity.title)).toEqual(["Z", "B", "C", "A"]);
    expect(out.map((item) => item.rank)).toEqual([1, 2, 3, 4]);
  });

  it("shows a ranking regression: a lower score placed first stays first", () => {
    const wrong = [ranked("Low", 0.1, 1), ranked("High", 0.9, 2)];
    expect(normalizeRecommendations(wrong).map((item) => item.opportunity.title)).toEqual(["Low", "High"]);
  });
});

describe("the distance dates are moved", () => {
  const FIXED = Date.UTC(2030, 0, 15, 12);

  it("does not depend on the time of day the suite runs at", () => {
    const morning = wholeDaysBetween(Date.UTC(2026, 10, 2, 5, 30), FIXED);
    const evening = wholeDaysBetween(Date.UTC(2026, 10, 2, 19, 45), FIXED);
    expect(evening).toBe(morning);
    const stored = Date.UTC(2026, 10, 2);
    expect(new Date(stored + morning).toISOString().slice(0, 10)).toBe("2030-01-15");
  });

  it("is always a whole number of days", () => {
    expect(wholeDaysBetween(Date.UTC(2026, 10, 2, 23, 59), FIXED) % 86_400_000).toBe(0);
  });
});
