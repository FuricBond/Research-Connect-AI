import type { PersonalizedRankedCandidate } from "../../types/researcher";

/** Why a group of recommendations is together, in the words the page shows. */
export type GroupReason = "follow" | "work" | "profile" | "other";

export interface RecommendationGroup {
  key: string;
  reason: GroupReason;
  /** The topic the group is about; none for "More calls for you". */
  topic: string | null;
  items: PersonalizedRankedCandidate[];
}

const norm = (value: string) => value.trim().toLowerCase();

/**
 * Where a matched topic came from, read from the item's own matched signals: a stated or inferred
 * topic preference ("Topic: X", "Inferred Topic: X"), the expertise in the researcher's
 * publications ("X (CLASSIFICATION)"), or else a keyword on their profile.
 */
export function topicReason(item: PersonalizedRankedCandidate, topic: string): GroupReason {
  const wanted = norm(topic);
  const preferences = item.matched_signals?.matched_preferences ?? [];
  if (preferences.some((entry) => norm(entry.replace(/^(inferred\s+)?topic:\s*/i, "")) === wanted && /topic:/i.test(entry))) return "follow";
  const expertise = item.matched_signals?.matched_expertise ?? [];
  if (expertise.some((entry) => norm(entry.replace(/\s*\([^)]*\)\s*$/, "")) === wanted)) return "work";
  return "profile";
}

/**
 * P6 — recommendations in groups (plan §12, "Because you follow Graph neural networks"). Each
 * item joins the group of its matched topic that the most items share (ties: the first in
 * alphabetical order), so the groups are few and meaningful; an item with no matched topic goes
 * to "More calls for you". Groups keep the ranking: they are ordered by their best-ranked item
 * and items keep their order and their overall rank. Nothing is invented: a group exists only
 * where the API reported the match.
 */
export function groupRecommendations(items: PersonalizedRankedCandidate[]): RecommendationGroup[] {
  const counts = new Map<string, number>();
  const label = new Map<string, string>();
  for (const item of items) {
    const seen = new Set<string>();
    for (const topic of item.matched_signals?.matched_topics ?? []) {
      if (typeof topic !== "string" || !topic.trim()) continue;
      const key = norm(topic);
      if (seen.has(key)) continue;
      seen.add(key);
      counts.set(key, (counts.get(key) ?? 0) + 1);
      if (!label.has(key)) label.set(key, topic.trim());
    }
  }

  const groups = new Map<string, RecommendationGroup>();
  const order: string[] = [];
  for (const item of [...items].sort((a, b) => a.rank - b.rank)) {
    const topics = (item.matched_signals?.matched_topics ?? []).filter((topic) => typeof topic === "string" && topic.trim()).map(norm);
    let best: string | null = null;
    for (const key of topics) {
      if (best === null) best = key;
      else {
        const difference = (counts.get(key) ?? 0) - (counts.get(best) ?? 0);
        if (difference > 0 || (difference === 0 && key < best)) best = key;
      }
    }
    const key = best === null ? "__other__" : `topic:${best}`;
    let group = groups.get(key);
    if (!group) {
      const topic = best === null ? null : (label.get(best) ?? best);
      group = { key, reason: topic === null ? "other" : "profile", topic, items: [] };
      groups.set(key, group);
      order.push(key);
    }
    group.items.push(item);
  }

  // A topic counts as followed if any item matched it through a topic preference, else as work.
  const strength: GroupReason[] = ["follow", "work", "profile"];
  for (const group of groups.values()) {
    if (group.topic === null) continue;
    const reasons = group.items.map((item) => topicReason(item, group.topic!));
    group.reason = strength.find((reason) => reasons.includes(reason)) ?? "profile";
  }

  // "More calls for you" goes last whatever its best rank; the rest keep the order of their best item.
  return order
    .map((key) => groups.get(key)!)
    .sort((a, b) => (a.reason === "other" ? 1 : 0) - (b.reason === "other" ? 1 : 0));
}

export function groupHeading(group: RecommendationGroup): { lead: string; topic: string | null } {
  switch (group.reason) {
    case "follow":
      return { lead: "Because you follow", topic: group.topic };
    case "work":
      return { lead: "Because of your work on", topic: group.topic };
    case "profile":
      return { lead: "Because your profile mentions", topic: group.topic };
    default:
      return { lead: "More calls for you", topic: null };
  }
}
