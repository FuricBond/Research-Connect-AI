"use client";

import Link from "next/link";
import { useState } from "react";
import { Plus } from "lucide-react";
import type { ApiResource } from "../../hooks/useApiResource";
import { createResearcherPreference } from "../../services/api";
import type {
  ExpertiseClassification,
  ResearcherIntelligenceResponse,
  ResearcherInterestItem,
  ResearcherPreferenceIntelligenceResponse,
  ResearcherPreferenceItem,
  ResearcherProfile,
} from "../../types/researcher";
import { humanizeEnum } from "../../utils/date";
import { TOPIC_CATEGORIES, preferenceLabel } from "../../utils/personalization";
import { TopicTags } from "../research/TopicTags";
import { Button } from "../ui/Button/Button";
import { Select } from "../ui/Field/Field";
import { SkeletonList } from "../ui/State/State";
import styles from "./Profile.module.css";

const CLASSIFICATION: Record<ExpertiseClassification, string> = {
  PRIMARY_EXPERTISE: "Primary expertise",
  SECONDARY_EXPERTISE: "Secondary expertise",
  EMERGING_INTEREST: "Emerging interest",
  WEAK_INTEREST: "Occasional interest",
  INSUFFICIENT_EVIDENCE: "Not enough evidence",
};

const FILTERS: { value: string; label: string; match: (item: ResearcherInterestItem) => boolean }[] = [
  { value: "ALL", label: "All topics", match: () => true },
  { value: "PRIMARY", label: "Primary expertise", match: (item) => item.classification === "PRIMARY_EXPERTISE" },
  { value: "SECONDARY", label: "Secondary expertise", match: (item) => item.classification === "SECONDARY_EXPERTISE" },
  { value: "EMERGING", label: "Emerging interests", match: (item) => item.classification === "EMERGING_INTEREST" },
];

/** Topics listed before "Show all". */
const SHOWN = 6;
const pct = (value: number) => `${Math.round(value * 100)}%`;
const norm = (value: string) => value.trim().toLowerCase();

/** What the researcher stated: topic preferences, and the keywords on their profile. */
export function declaredTopics(profile: ResearcherProfile, stated: ResearcherPreferenceItem[]): string[] {
  const seen = new Set<string>();
  const topics: string[] = [];
  const add = (value: string) => {
    if (!value.trim() || seen.has(norm(value))) return;
    seen.add(norm(value));
    topics.push(value.trim());
  };
  for (const item of stated) {
    if (item.is_active && item.preference_type !== "EXCLUDED" && TOPIC_CATEGORIES.includes(item.category)) add(preferenceLabel(item));
  }
  for (const keyword of profile.keywords) add(keyword);
  return topics;
}

function Topic({ item }: { item: ResearcherInterestItem }) {
  const years =
    item.first_observed_year && item.last_observed_year && item.first_observed_year !== item.last_observed_year
      ? `${item.first_observed_year}–${item.last_observed_year}`
      : item.last_observed_year
        ? String(item.last_observed_year)
        : null;
  return (
    <li className={styles.row}>
      <div className={styles.topicHead}>
        <h4 className={styles.topicName}>{item.topic_name}</h4>
        <span className={styles.muted}>{CLASSIFICATION[item.classification] ?? humanizeEnum(item.classification)}</span>
      </div>
      <span className={styles.rowMeta}>
        <span>
          {item.evidence_count} work{item.evidence_count === 1 ? "" : "s"}
        </span>
        {years && <span>{years}</span>}
        <span>
          Strength {pct(item.strength)} · confidence {pct(item.confidence)} · recency {pct(item.recency_score)}
        </span>
        <span>Source: {humanizeEnum(item.source)}</span>
      </span>
      <details className={styles.why}>
        <summary>
          Why this topic?<span className="rc-visually-hidden"> {item.topic_name}</span>
        </summary>
        <div className={styles.whyBody}>
          {item.provenance_reasons.length > 0 && (
            <ul className={styles.plainList}>
              {item.provenance_reasons.map((reason, i) => (
                <li key={i}>{reason}</li>
              ))}
            </ul>
          )}
          {item.supporting_works.length === 0 ? (
            <p className={styles.muted}>From your profile keywords; no indexed publication supports it yet.</p>
          ) : (
            <>
              <p className={styles.muted}>
                Supported by {item.supporting_works.length} publication{item.supporting_works.length === 1 ? "" : "s"}
                {item.supporting_works.length > 5 ? ", the first 5 shown" : ""}:
              </p>
              <ul className={styles.plainList}>
                {item.supporting_works.slice(0, 5).map((work) => (
                  <li key={work.id}>
                    {work.title}
                    {work.publication_year ? ` (${work.publication_year})` : ""}
                    {work.cited_by_count > 0 ? `, ${work.cited_by_count} citation${work.cited_by_count === 1 ? "" : "s"}` : ""}
                    {work.author_position ? `, ${work.author_position} author` : ""}
                    {work.doi && (
                      <>
                        {" "}
                        <a className={styles.link} href={`https://doi.org/${work.doi}`} target="_blank" rel="noopener noreferrer">
                          DOI<span className="rc-visually-hidden"> for {work.title} (opens in new tab)</span>
                        </a>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </details>
    </li>
  );
}

interface ResearchTopicsProps {
  profile: ResearcherProfile;
  topics: ApiResource<ResearcherIntelligenceResponse>;
  preferences: ApiResource<ResearcherPreferenceIntelligenceResponse>;
  onRecompute: () => void;
}

/**
 * Research topics (plan §12, resolves P1-14 by naming both): the topics the researcher stated —
 * topic preferences and profile keywords — beside the topics found in their publications
 * (Phase 3.2), each with its evidence. Topics suggested from the publications can be added to
 * what they follow in one step; nothing is added without asking.
 */
export function ResearchTopics({ profile, topics, preferences, onRecompute }: ResearchTopicsProps) {
  const [filter, setFilter] = useState("ALL");
  const [all, setAll] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  const stated = preferences.data?.explicit_preferences ?? [];
  const declared = declaredTopics(profile, stated);
  const known = new Set(declared.map(norm));
  const suggestions = (preferences.data?.derived_candidates ?? []).filter((candidate) => !known.has(norm(preferenceLabel(candidate))));

  async function adopt(candidate: ResearcherPreferenceItem) {
    setAdding(candidate.id);
    try {
      await createResearcherPreference(profile.id, {
        category: candidate.category,
        preference_key: candidate.preference_key,
        preference_value: candidate.preference_value,
        display_label: candidate.display_label,
        canonical_id: candidate.canonical_id,
      });
      setNotice(`Added ${preferenceLabel(candidate)} to the topics you follow.`);
      preferences.retry();
    } catch {
      setNotice("That topic could not be added. Try again.");
    } finally {
      setAdding(null);
    }
  }

  const data = topics.data;
  const rule = FILTERS.find((entry) => entry.value === filter) ?? FILTERS[0];
  const interests = data?.interests ?? [];
  const filtered = interests.filter(rule.match);
  const shown = all ? filtered : filtered.slice(0, SHOWN);

  return (
    <section id="topics" className={styles.card} aria-labelledby="topics-heading">
      <div className={styles.cardHead}>
        <h2 id="topics-heading" className={styles.cardTitle}>
          Research topics
        </h2>
      </div>
      <div className={styles.topics}>
        <div className={styles.topicColumn}>
          <h3 className={styles.subTitle}>You stated</h3>
          {preferences.status === "loading" || preferences.status === "idle" ? (
            <SkeletonList rows={2} label="Loading the topics you stated" announce={false} />
          ) : declared.length > 0 ? (
            <TopicTags topics={declared} label="Topics you stated" />
          ) : (
            <p className={styles.muted}>No topics stated yet.</p>
          )}
          {preferences.status === "error" && (
            <p className={styles.muted}>
              Your topic preferences could not be loaded; your profile keywords are shown.{" "}
              <Button variant="link" size="sm" onClick={preferences.retry}>
                Try again
              </Button>
            </p>
          )}
          <Link href="/researcher/preferences" className={styles.link}>
            Edit research preferences
          </Link>
        </div>

        <div className={styles.topicColumn}>
          <h3 className={styles.subTitle}>From your publications</h3>
          {topics.status === "loading" || topics.status === "idle" ? (
            <SkeletonList rows={3} label="Loading the topics in your publications" announce={false} />
          ) : topics.status === "error" || !data ? (
            <div className={styles.completeness}>
              <p className={styles.muted}>The topics in your publications could not be loaded.</p>
              <div>
                <Button variant="secondary" size="sm" onClick={topics.retry}>
                  Try again
                </Button>
              </div>
            </div>
          ) : interests.length === 0 ? (
            <p className={styles.muted}>No topics found yet. Link an ORCID iD or OpenAlex author ID and the topics of your publications appear here.</p>
          ) : (
            <>
              <p className={styles.muted}>
                {data.summary
                  ? `${data.summary.total_topics_analyzed} topics from ${data.summary.total_works_analyzed} publication${data.summary.total_works_analyzed === 1 ? "" : "s"} · ${data.summary.primary_expertise_count} primary · ${data.summary.emerging_interest_count} emerging${data.summary.active_years_span ? ` · active ${data.summary.active_years_span}` : ""}. `
                  : ""}
                Worked out from your publications alone, not from your preferences.
              </p>
              <div className={styles.controls}>
                <Select label="Show" value={filter} onChange={(event) => setFilter(event.target.value)}>
                  {FILTERS.map((entry) => (
                    <option key={entry.value} value={entry.value}>
                      {entry.label} ({interests.filter(entry.match).length})
                    </option>
                  ))}
                </Select>
                <Button variant="secondary" size="sm" onClick={onRecompute}>
                  Work out again
                </Button>
              </div>
              {filtered.length === 0 ? (
                <p className={styles.muted}>No topics of this kind.</p>
              ) : (
                <ul className={styles.rows} aria-label="Topics in your publications">
                  {shown.map((item, i) => (
                    <Topic key={`${item.topic_slug}-${i}`} item={item} />
                  ))}
                </ul>
              )}
              {filtered.length > SHOWN && (
                <div>
                  <Button variant="link" size="sm" aria-expanded={all} onClick={() => setAll(!all)}>
                    {all ? "Show fewer" : `Show all ${filtered.length}`}
                  </Button>
                </div>
              )}
            </>
          )}
          {suggestions.length > 0 && (
            <div className={styles.completeness}>
              <h4 className={styles.subTitle}>Follow a topic from your publications</h4>
              <ul className={styles.chips}>
                {suggestions.map((candidate) => (
                  <li key={candidate.id}>
                    <Button
                      variant="secondary"
                      size="sm"
                      leadingIcon={<Plus size={16} aria-hidden="true" />}
                      disabled={adding !== null}
                      onClick={() => adopt(candidate)}
                    >
                      <span className="rc-visually-hidden">Follow </span>
                      {preferenceLabel(candidate)}
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p role="status" className={styles.notice}>
            {notice}
          </p>
        </div>
      </div>
    </section>
  );
}
