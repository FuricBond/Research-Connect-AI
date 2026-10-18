"use client";

import Link from "next/link";
import { useId } from "react";
import type { CollaborationStatus, PeerMatchTier, PeerProfile } from "../../types/peer";
import { COLLABORATION_INTEREST_LABELS, COLLABORATION_STATUS_LABELS } from "../../types/peer";
import { POSTING_TYPE_LABELS } from "../../types/posting";
import type { MatchingPaper, OpenPostingRef } from "../../types/supervisor";
import { humanizeEnum } from "../../utils/date";
import { academicStatusLabel } from "../../utils/personalization";
import { FitScore } from "../research/FitScore";
import { TopicTags } from "../research/TopicTags";
import { Badge } from "../ui/Badge/Badge";
import details from "../research/Details.module.css";
import styles from "./People.module.css";

const AVAILABILITY_TONE: Record<CollaborationStatus, "brand" | "neutral" | "muted"> = {
  SEEKING_COLLABORATORS: "brand",
  OPEN_TO_ENQUIRIES: "brand",
  SELECTIVELY_AVAILABLE: "neutral",
  NOT_AVAILABLE: "muted",
};

export interface ScoredSignal {
  key: string;
  label: string;
  rawScore: number;
  contribution: number;
  explanation: string;
}

interface ResearcherCardProps {
  person: PeerProfile;
  /** 0–1, as the API returns it. */
  score: number;
  tier: PeerMatchTier;
  confidence: number;
  reasons: string[];
  sharedTopics: string[];
  /** Peers: expertise they have that the viewer does not. */
  complementaryTopics?: string[];
  /** Supervisors: their recent papers closest to the viewer's interests. */
  papers?: MatchingPaper[];
  /** Supervisors: their open thesis topics, projects and assistantships. */
  postings?: OpenPostingRef[];
  signals: ScoredSignal[];
}

const topicWords = (topics: string[]) => topics.map((topic) => topic.replace(/-/g, " "));

function initials(name: string | null): string {
  const parts = (name ?? "").split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

function paperHref(paper: MatchingPaper): string | null {
  if (paper.doi) return `https://doi.org/${paper.doi}`;
  return paper.landing_page_url;
}

/** Matching papers shown on the card; the rest are under "How this was scored". */
const PAPERS_SHOWN = 2;

/** Papers open where they are published; the "new tab" note follows the title for screen readers. */
function Papers({ papers }: { papers: MatchingPaper[] }) {
  return (
    <ul className={styles.plainList}>
      {papers.map((paper) => {
        const href = paperHref(paper);
        return (
          <li key={paper.work_id}>
            {href ? (
              <a className={styles.link} href={href} target="_blank" rel="noopener noreferrer">
                {paper.title}
                <span className="rc-visually-hidden"> (opens in new tab)</span>
              </a>
            ) : (
              paper.title
            )}
            {paper.publication_year ? ` (${paper.publication_year})` : ""}
            {` · ${Math.round(paper.similarity * 100)}% similar`}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * A suggested supervisor or peer (DESIGN_SYSTEM.md §9 ResearcherCard): who they are, their
 * availability, the fit in the API's words, up to three shared topics and the two strongest
 * reasons; open postings and matching papers for supervisors; then "How this was scored". A
 * field the person chose not to share (institution, email) arrives as null and is left out,
 * never shown as unknown. Scores and reasons are the server's.
 */
export function ResearcherCard({ person, score, tier, confidence, reasons, sharedTopics, complementaryTopics = [], papers = [], postings = [], signals }: ResearcherCardProps) {
  const titleId = `person-${useId()}`;
  const name = person.full_name ?? "Unnamed researcher";
  const facts = [academicStatusLabel(person.academic_status), person.institution, person.department].filter(Boolean);
  const shared = topicWords(sharedTopics);
  const adds = topicWords(complementaryTopics);

  return (
    <article className={styles.card} aria-labelledby={titleId}>
      <div className={styles.head}>
        <span className={styles.avatar} aria-hidden="true">
          {initials(person.full_name)}
        </span>
        <div className={styles.who}>
          <h3 id={titleId} className={styles.name}>
            {name}
          </h3>
          {facts.length > 0 && <p className={styles.facts}>{facts.join(" · ")}</p>}
          <div className={styles.badges}>
            <Badge className={styles.availability} tone={AVAILABILITY_TONE[person.collaboration_status] ?? "neutral"}>{COLLABORATION_STATUS_LABELS[person.collaboration_status] ?? humanizeEnum(person.collaboration_status)}</Badge>
          </div>
        </div>
      </div>

      <FitScore score={score * 100} tier={tier} reason={reasons[0] ?? null} />
      {reasons[1] && <p className={styles.text}>{reasons[1]}</p>}

      {shared.length > 0 && (
        <div className={styles.group}>
          <h4 className={styles.groupTitle}>Shared topics</h4>
          <TopicTags topics={shared.slice(0, 3)} shared label={`Topics you share with ${name}`} />
          {shared.length > 3 && <span className={styles.more}>and {shared.length - 3} more, under How this was scored</span>}
        </div>
      )}

      {papers.length > 0 && (
        <div className={styles.group}>
          <h4 className={styles.groupTitle}>Their papers closest to your interests</h4>
          <Papers papers={papers.slice(0, PAPERS_SHOWN)} />
        </div>
      )}

      {postings.length > 0 && (
        <div className={styles.group}>
          <h4 className={styles.groupTitle}>Open postings</h4>
          <ul className={styles.plainList}>
            {postings.map((posting) => (
              <li key={posting.posting_id}>
                <Link className={styles.link} href={`/postings/${posting.posting_id}`}>
                  {posting.title}
                </Link>
                {` · ${POSTING_TYPE_LABELS[posting.posting_type]}`}
                {posting.application_deadline ? ` · apply by ${new Date(posting.application_deadline).toLocaleDateString(undefined, { dateStyle: "medium" })}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      {person.collaboration_note && <p className={styles.text}>{person.collaboration_note}</p>}

      {person.collaboration_interests.length > 0 && (
        <div className={styles.group}>
          <h4 className={styles.groupTitle}>Will collaborate on</h4>
          <TopicTags topics={person.collaboration_interests.map((interest) => COLLABORATION_INTEREST_LABELS[interest] ?? humanizeEnum(interest))} label={`Collaboration ${name} will consider`} />
        </div>
      )}

      {person.contact_email && (
        <p className={styles.facts}>
          <a className={styles.link} href={`mailto:${person.contact_email}`}>
            {person.contact_email}
          </a>
        </p>
      )}

      <details className={styles.scored}>
        <summary>
          How this was scored<span className="rc-visually-hidden"> for {name}</span>
        </summary>
        <div className={styles.scoredBody}>
          <p className={styles.note}>Confidence {Math.round(confidence * 100)}%: how much evidence the score rests on.</p>
          {signals.length > 0 && (
            <div className="rc-scroll-x" role="region" aria-label={`Signals for ${name}`} tabIndex={0}>
              <table className={details.table}>
                <caption className="rc-visually-hidden">Signals for {name}</caption>
                <thead>
                  <tr>
                    <th scope="col">Signal</th>
                    <th scope="col">Score</th>
                    <th scope="col">Contribution</th>
                  </tr>
                </thead>
                <tbody>
                  {signals.map((signal) => (
                    <tr key={signal.key}>
                      <td>
                        {signal.label}
                        <span className={details.source}> — {signal.explanation}</span>
                      </td>
                      <td>{signal.rawScore.toFixed(2)}</td>
                      <td>
                        {signal.contribution >= 0 ? "+" : "−"}
                        {Math.abs(signal.contribution).toFixed(3)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {reasons.length > 2 && (
            <ul className={styles.plainList}>
              {reasons.slice(2).map((reason, i) => (
                <li key={i}>{reason}</li>
              ))}
            </ul>
          )}
          {shared.length > 3 && <TopicTags topics={shared} shared label={`All topics you share with ${name}`} />}
          {adds.length > 0 && (
            <div className={styles.group}>
              <h4 className={styles.groupTitle}>They add</h4>
              <TopicTags topics={adds.slice(0, 6)} label={`Topics ${name} adds`} />
            </div>
          )}
          {papers.length > PAPERS_SHOWN && (
            <div className={styles.group}>
              <h4 className={styles.groupTitle}>More of their papers close to your interests</h4>
              <Papers papers={papers.slice(PAPERS_SHOWN)} />
            </div>
          )}
        </div>
      </details>
    </article>
  );
}
