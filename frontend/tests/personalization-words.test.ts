/**
 * P6 — personalization in words (utils/personalization.ts): what the API sends is shown in its
 * own words, without its marks, raw enum suffixes or case-only duplicates, and a confidence that
 * arrives as a number is said as a percentage (the live API sends 0–1, which once crashed a page
 * that expected a word).
 */

import { describe, expect, it } from "vitest";
import { academicStatusLabel, confidenceLabel, impactWord, strengthWord, uniqueWords, withoutMark, wordedSuffix } from "../utils/personalization";
import { humanizeEnum } from "../utils/date";

describe("personalization words", () => {
  it("drops the backend's leading marks and keeps the words", () => {
    expect(withoutMark("✓ Matches your explicit research preferences")).toBe("Matches your explicit research preferences");
    expect(withoutMark("⚠️ CRITICAL WARNING: This venue is flagged")).toBe("CRITICAL WARNING: This venue is flagged");
    expect(withoutMark("Plain reason")).toBe("Plain reason");
  });

  it("puts an enum suffix into words and removes case-only duplicates", () => {
    expect(wordedSuffix("Accessibility (PRIMARY_EXPERTISE)")).toBe("Accessibility (primary expertise)");
    expect(wordedSuffix("Behavioral Mode: HYBRID (POSITIVE)")).toBe("Behavioral Mode: HYBRID (positive)");
    expect(uniqueWords(["Accessibility", "accessibility", " human-computer  interaction", "human-computer interaction"])).toEqual(["Accessibility", " human-computer  interaction"]);
  });

  it("says a 0–1 confidence as a percentage, and nothing when there is none", () => {
    expect(confidenceLabel(0.79)).toBe("79% confidence");
    expect(confidenceLabel(null)).toBeNull();
    expect(confidenceLabel(Number.NaN)).toBeNull();
  });

  it("never throws on a number where a word was expected", () => {
    expect(humanizeEnum(0.79 as unknown as string)).toBe("0.79");
  });

  it("names impacts, strengths and career stages in words", () => {
    expect(impactWord("WARNING")).toBe("A caution");
    expect(impactWord("NEGATIVE")).toBe("Counted against it");
    expect(strengthWord(0.8)).toBe("Strong");
    expect(academicStatusLabel("PHD")).toBe("PhD");
    expect(academicStatusLabel("UNKNOWN")).toBeNull();
  });
});
