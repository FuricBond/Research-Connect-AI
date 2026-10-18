"use client";

import { useState } from "react";
import { useApiResource } from "../../../hooks/useApiResource";
import { fetchPersonalizedCandidates } from "../../../services/api";
import type { CandidateSourceType } from "../../../types/researcher";
import { humanizeEnum } from "../../../utils/date";
import { DeadlineCountdown } from "../../research/DeadlineCountdown";
import { Fact } from "../../research/RiskDetails";
import { RiskIndicator } from "../../research/RiskIndicator";
import { Button } from "../../ui/Button/Button";
import { Checkbox, Select } from "../../ui/Field/Field";
import { Alert } from "../../ui/State/State";
import details from "../../research/Details.module.css";
import { Loaded, Metrics } from "./shared";
import styles from "../Recommendations.module.css";

const SOURCE: Record<CandidateSourceType, string> = {
  EXPLICIT_PREFERENCE: "Stated preference",
  INFERRED_PREFERENCE: "Inferred preference",
  RESEARCH_EXPERTISE: "Expertise in your publications",
  RESEARCH_INTEREST: "Research interest",
  PROFILE_KEYWORD: "Profile keyword",
  COLD_START_FALLBACK: "Discovery",
};

interface Options {
  inferred: boolean;
  expertise: boolean;
  fallback: boolean;
  limit: number;
}

/**
 * The calls considered before ranking (Phase 3.4, formerly "Personalized Candidate Preview"):
 * where each came from, with its provenance, and the coverage of each source. Not ranked.
 */
export default function CandidatesPart({ profileId }: { profileId: string }) {
  const [draft, setDraft] = useState<Options>({ inferred: true, expertise: true, fallback: true, limit: 50 });
  const [options, setOptions] = useState<Options>(draft);
  const key = `technical:candidates:${profileId}:${options.inferred}:${options.expertise}:${options.fallback}:${options.limit}`;
  const candidates = useApiResource(key, (signal) =>
    fetchPersonalizedCandidates(
      profileId,
      { limit: options.limit, includeInferred: options.inferred, includeExpertise: options.expertise, includeFallback: options.fallback },
      undefined,
      signal
    )
  );

  return (
    <>
      <form
        className={styles.controls}
        onSubmit={(event) => {
          event.preventDefault();
          setOptions({ ...draft });
        }}
      >
        <Checkbox label="Inferred preferences" checked={draft.inferred} onChange={(event) => setDraft({ ...draft, inferred: event.target.checked })} />
        <Checkbox label="Expertise in your publications" checked={draft.expertise} onChange={(event) => setDraft({ ...draft, expertise: event.target.checked })} />
        <Checkbox label="Discovery" checked={draft.fallback} onChange={(event) => setDraft({ ...draft, fallback: event.target.checked })} />
        <Select label="Calls" value={String(draft.limit)} onChange={(event) => setDraft({ ...draft, limit: Number(event.target.value) })}>
          {[10, 25, 50, 100].map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </Select>
        <Button type="submit" variant="secondary" size="sm">
          Apply
        </Button>
      </form>
      <Loaded resource={candidates} label="Loading the calls considered" failure="The calls considered could not be loaded.">
        {(data) => (
          <>
            <Metrics
              label="Where the calls considered came from"
              items={[
                ["Calls considered", data.candidate_count],
                ["From stated preferences", data.coverage.explicit_preference_count],
                ["From inferred preferences", data.coverage.inferred_preference_count],
                ["From expertise", data.coverage.expertise_count],
                ["From your profile", data.coverage.profile_count],
                ["From discovery", data.coverage.fallback_count],
              ]}
            />
            {data.is_cold_start && <Alert>Few preferences and publications are recorded, so discovery filled in the calls considered.</Alert>}
            {data.candidates.length === 0 ? (
              <p className={styles.muted}>No calls were considered. Turn on discovery or add topics and preferences.</p>
            ) : (
              <ul className={styles.records} aria-label="Calls considered, not ranked">
                {data.candidates.map((item) => {
                  const call = item.opportunity;
                  const provenance = item.provenance;
                  return (
                    <li key={item.candidate_id} className={styles.record}>
                      <span className={styles.recordHead}>
                        <span className={styles.recordTitle}>{call.title}</span>
                      </span>
                      <span className={styles.recordHead}>
                        <span>{humanizeEnum(call.opportunity_type)}</span>
                        <span>· {humanizeEnum(call.delivery_mode)}</span>
                        <DeadlineCountdown deadline={call.submission_deadline} daysRemaining={call.days_remaining} status={call.deadline_status} urgencyTier={call.urgency_tier} />
                        <RiskIndicator level={call.risk_level} isPredatory={call.is_predatory_flag} />
                      </span>
                      <span className={styles.numbers}>From: {provenance.sources.map((source) => SOURCE[source] ?? humanizeEnum(source)).join(", ")}</span>
                      <details className={details.technical}>
                        <summary>
                          Why it was considered<span className="rc-visually-hidden"> — {call.title}</span>
                        </summary>
                        <div className={details.technicalBody}>
                          {provenance.reasons.length > 0 && (
                            <ul className={details.list}>
                              {provenance.reasons.map((reason, i) => (
                                <li key={i}>{reason}</li>
                              ))}
                            </ul>
                          )}
                          <dl className={details.facts}>
                            {provenance.matched_topics.length > 0 && <Fact term="Matched topics" value={provenance.matched_topics.join(", ")} />}
                            {provenance.matched_preferences.length > 0 && <Fact term="Matched preferences" value={provenance.matched_preferences.join(", ")} />}
                            {provenance.matched_expertise.length > 0 && <Fact term="Matched expertise" value={provenance.matched_expertise.join(", ")} />}
                            {call.location && <Fact term="Location" value={call.location} />}
                            {call.organizer && <Fact term="Organiser" value={call.organizer} />}
                            <Fact term="Status" value={humanizeEnum(call.status)} />
                            {call.risk_reasons.length > 0 && <Fact term="Venue risk" value={call.risk_reasons.join("; ")} />}
                            {call.deadline_explanation && <Fact term="Deadline" value={call.deadline_explanation} />}
                          </dl>
                        </div>
                      </details>
                    </li>
                  );
                })}
              </ul>
            )}
          </>
        )}
      </Loaded>
    </>
  );
}
