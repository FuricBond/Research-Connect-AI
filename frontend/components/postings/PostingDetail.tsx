"use client";

import Link from "next/link";
import { useState } from "react";
import { ExternalLink, Mail, Send } from "lucide-react";
import { useApiResource } from "../../hooks/useApiResource";
import { fetchPostingFit, fetchPosting } from "../../services/api";
import type { ResearchPosting } from "../../types/posting";
import { POSTING_TYPE_LABELS, WORK_MODE_LABELS } from "../../types/posting";
import { isNewer, MY_POSTINGS_HREF, webAddress } from "../../utils/postings";
import { applicationStatusMeta, postingStatusMeta } from "../../utils/status";
import { useSession } from "../auth/SessionProvider";
import { DeadlineCountdown } from "../research/DeadlineCountdown";
import { TopicTags } from "../research/TopicTags";
import { Badge, StatusBadge } from "../ui/Badge/Badge";
import { Breadcrumb } from "../ui/Breadcrumb/Breadcrumb";
import { Button, ButtonLink } from "../ui/Button/Button";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { Alert, ErrorState, SkeletonList, SkeletonText } from "../ui/State/State";
import { shortDate } from "../workspace/workflow";
import { Applications, ApplyForm } from "./lazy";
import { ManagePosting } from "./PostingManage";
import { OpeningTermsPanel } from "./OpeningTermsPanel";
import styles from "./Faculty.module.css";

/**
 * A posting's own page (`/postings/[id]`). Everyone who may see it reads the same posting; its
 * author also manages it here — the lifecycle actions the server lists ("Cancel posting" and
 * "Delete draft" ask first), Edit, and the applications with the review decisions (P9, plan §14).
 * A student sees their fit and, where the opening takes applications on the platform, applies
 * here (the "Apply now" → "Submit application" flow and the `#cover-note` field are kept).
 *
 * The posting is asked for once the session is known (its answer depends on who asks: drafts are
 * visible to their author only, `is_owner`, the reader's own application), and again for another
 * account. Drafts and postings that are not open are "not found" for everyone else.
 */
export function PostingDetail({ postingId }: { postingId: string | null }) {
  const { status: sessionStatus, user, hasRole } = useSession();
  const viewer = sessionStatus === "loading" ? null : (user?.id ?? "visitor");
  const resource = useApiResource(postingId && viewer ? `posting:${postingId}:${viewer}` : null, (signal) => fetchPosting(postingId!, signal), { scope: "public" });
  // The author's latest confirmed change (PostingAuthor), shown unless the server's listing is newer.
  const [answer, setAnswer] = useState<ResearchPosting | null>(null);
  const listed = resource.data ?? null;
  const posting = listed ? (answer && answer.id === listed.id && isNewer(answer, listed) ? answer : listed) : null;

  if (resource.status === "error") {
    const missing = resource.error?.kind === "not-found";
    return (
      <>
        <Breadcrumb items={[{ label: "Research postings", href: "/postings" }]} current="Posting" />
        <ErrorState
          headingLevel={1}
          kind={missing ? "not-found" : resource.error?.kind === "network" ? "offline" : "failed"}
          title={missing ? "This posting is not available" : "This posting could not be loaded"}
          description={missing ? "It may have been withdrawn, or it may still be an unpublished draft." : undefined}
          onRetry={missing ? undefined : resource.retry}
          actions={<ButtonLink href="/postings">Back to research postings</ButtonLink>}
        />
      </>
    );
  }
  if (!posting) {
    return (
      <div aria-busy="true" className={styles.detailLoading}>
        <SkeletonText title lines={3} />
        <SkeletonList rows={2} lines={2} label="Loading the posting" />
      </div>
    );
  }

  const student = sessionStatus === "authenticated" && hasRole("STUDENT");
  return <PostingView posting={posting} onChanged={setAnswer} reload={resource.retry} student={student} />;
}

function PostingView({ posting, onChanged, reload, student }: { posting: ResearchPosting; onChanged: (posting: ResearchPosting) => void; reload: () => void; student: boolean }) {
  const place = posting.location || posting.country || null;
  const official = webAddress(posting.external_url);
  const author = posting.is_owner;

  return (
    <article className={styles.detail} aria-labelledby="posting-title">
      <Breadcrumb items={[author ? { label: "My postings", href: MY_POSTINGS_HREF } : { label: "Research postings", href: "/postings" }]} current={posting.title} />
      <div className={styles.badges}>
        <Badge tone="neutral">{POSTING_TYPE_LABELS[posting.posting_type]}</Badge>
        <StatusBadge meta={postingStatusMeta(posting.status)} />
        {posting.status === "OPEN" && (posting.is_accepting_applications ? <Badge tone="success">Accepting applications</Badge> : <Badge tone="muted">Not accepting applications</Badge>)}
        {posting.application_deadline && <DeadlineCountdown deadline={posting.application_deadline} daysRemaining={posting.days_until_deadline} />}
      </div>
      <PageHeader
        title={<span id="posting-title">{posting.title}</span>}
        description={[posting.author.full_name ?? "Unnamed researcher", posting.author.institution, posting.department].filter(Boolean).join(" · ")}
      />

      {author && <ManagePosting posting={posting} onChanged={onChanged} />}
      {!author && student && <YourFit posting={posting} />}

      {posting.summary && <p className={styles.lead}>{posting.summary}</p>}

      <section className={styles.detailSection} aria-labelledby="posting-about">
        <h2 id="posting-about" className={styles.detailTitle}>
          About this opportunity
        </h2>
        <p className={styles.body}>{posting.description}</p>
      </section>

      {(posting.required_skills.length > 0 || posting.preferred_qualifications) && (
        <section className={styles.detailSection} aria-labelledby="posting-expected">
          <h2 id="posting-expected" className={styles.detailTitle}>
            What is expected
          </h2>
          {posting.required_skills.length > 0 && <TopicTags topics={posting.required_skills} label={`Skills for ${posting.title}`} />}
          {posting.preferred_qualifications && <p className={styles.body}>{posting.preferred_qualifications}</p>}
        </section>
      )}

      <OpeningTermsPanel terms={posting.opening_terms} />

      {posting.opening_terms.accepts_applications && posting.opening_terms.is_structured_opening && !author && <Apply posting={posting} reload={reload} />}

      {author && (posting.opening_terms.accepts_applications || posting.application_count > 0) && <Applications posting={posting} />}

      <section className={styles.detailSection} aria-labelledby="posting-details">
        <h2 id="posting-details" className={styles.detailTitle}>
          Details
        </h2>
        <dl className={styles.factList}>
          <div>
            <dt>Positions</dt>
            <dd>{posting.positions_available}</dd>
          </div>
          <div>
            <dt>Work mode</dt>
            <dd>{WORK_MODE_LABELS[posting.work_mode]}</dd>
          </div>
          {place && (
            <div>
              <dt>Location</dt>
              <dd>{place}</dd>
            </div>
          )}
          <div>
            <dt>Application deadline</dt>
            <dd>{posting.application_deadline ? shortDate(posting.application_deadline) : "Open-ended"}</dd>
          </div>
          {posting.expected_start_date && (
            <div>
              <dt>Expected start</dt>
              <dd>{shortDate(posting.expected_start_date)}</dd>
            </div>
          )}
          {posting.expected_end_date && (
            <div>
              <dt>Expected end</dt>
              <dd>{shortDate(posting.expected_end_date)}</dd>
            </div>
          )}
          {posting.published_at && (
            <div>
              <dt>Published</dt>
              <dd>{shortDate(posting.published_at)}</dd>
            </div>
          )}
        </dl>
      </section>

      {posting.topics.length > 0 && (
        <section className={styles.detailSection} aria-labelledby="posting-topics">
          <h2 id="posting-topics" className={styles.detailTitle}>
            Research topics
          </h2>
          <TopicTags topics={posting.topics.map((topic) => `${topic.name ?? topic.slug ?? "Topic"}${topic.is_primary ? " (primary)" : ""}`)} label={`Topics of ${posting.title}`} />
        </section>
      )}

      {(posting.contact_email || official) && (
        <section className={styles.detailSection} aria-labelledby="posting-contact">
          <h2 id="posting-contact" className={styles.detailTitle}>
            How to get in touch
          </h2>
          <p className={styles.contacts}>
            {posting.contact_email && (
              <a className={styles.contact} href={`mailto:${posting.contact_email}`}>
                <Mail size={16} aria-hidden="true" />
                {posting.contact_email}
              </a>
            )}
            {official && (
              <a className={styles.contact} href={official} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={16} aria-hidden="true" />
                Official page<span className="rc-visually-hidden"> (opens in a new tab)</span>
              </a>
            )}
          </p>
        </section>
      )}
    </article>
  );
}

/** Phase 5.15 — the signed-in student's fit; never asked for the author or other roles. */
function YourFit({ posting }: { posting: ResearchPosting }) {
  const fit = useApiResource(`posting-fit:${posting.id}`, (signal) => fetchPostingFit(posting.id, signal));
  if (!fit.data) return null; // The posting is still shown; only the fit is left out.
  const data = fit.data;
  return (
    <section className={styles.detailSection} aria-labelledby="your-fit-heading">
      <h2 id="your-fit-heading" className={styles.detailTitle}>
        Your fit
      </h2>
      {data.score === null ? (
        <p className={styles.facts}>
          {data.gaps[0] ?? "Add research interests or keywords to your profile"} so this posting can be compared with your interests. <Link href="/researcher">Update your profile</Link>
        </p>
      ) : (
        <>
          <p className={styles.fitLine}>
            {data.score}% fit · {data.band}
          </p>
          {data.reasons.length > 0 && (
            <ul className={styles.reasons}>
              {data.reasons.map((reason) => (
                <li key={reason.code}>
                  {reason.label}
                  {reason.matched.length > 0 && reason.code !== "TOPIC" && reason.code !== "OPENING" ? `: ${reason.matched.join(", ")}` : ""}
                </li>
              ))}
            </ul>
          )}
          {data.gaps.length > 0 && (
            <>
              <h3 className={styles.subTitle}>To strengthen your application</h3>
              <TopicTags topics={data.gaps} label="Skills to strengthen your application" />
            </>
          )}
        </>
      )}
    </section>
  );
}

/** Applying (Phase 5.11), for anyone but the author, where the opening takes applications here; the form loads when asked for. */
function Apply({ posting, reload }: { posting: ResearchPosting; reload: () => void }) {
  const [open, setOpen] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  return (
    <section className={styles.detailSection} aria-labelledby="posting-apply">
      <h2 id="posting-apply" className={styles.detailTitle}>
        Apply for this opening
      </h2>
      {posting.viewer_application_status ? (
        <p className={styles.facts}>
          You have applied to this opening. Its status: <strong>{applicationStatusMeta(posting.viewer_application_status).label}</strong>. Follow it in{" "}
          <Link href="/postings/applications">My applications</Link>.
        </p>
      ) : submitted ? (
        <p className={styles.facts}>
          Your application has been submitted. Follow it in <Link href="/postings/applications">My applications</Link>.
        </p>
      ) : !posting.is_accepting_applications ? (
        <p className={styles.facts}>This opening is no longer accepting applications.</p>
      ) : open ? (
        <ApplyForm
          postingId={posting.id}
          onCancel={() => setOpen(false)}
          onSubmitted={() => {
            setSubmitted(true);
            setOpen(false);
            reload();
          }}
        />
      ) : (
        <Button variant="primary" leadingIcon={<Send size={16} aria-hidden="true" />} onClick={() => setOpen(true)}>
          Apply now
        </Button>
      )}
    </section>
  );
}
