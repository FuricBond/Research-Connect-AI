"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useApiResource } from "../../../hooks/useApiResource";
import { addWorkspaceComment, getWorkspaceActivity } from "../../../services/api";
import { Button } from "../../ui/Button/Button";
import { TextArea } from "../../ui/Field/Field";
import { Alert, EmptyState, ErrorState, SkeletonList } from "../../ui/State/State";
import { actionError, dateTime, type Abilities } from "../workflow";
import { useKept } from "./useWorkspaceItem";
import styles from "./Item.module.css";

const LIMIT = 50;

/**
 * Activity: what happened on the item, newest first (the latest 50), and notes for the team.
 * Contributors and up post notes. `version` changes when another tab changed something, and the
 * feed is read again only then.
 */
export function ActivityPanel({ workspaceId, can, version }: { workspaceId: string; can: Abilities; version: number }) {
  const activity = useApiResource(`workspace:${workspaceId}:activity`, (signal) => getWorkspaceActivity(workspaceId, LIMIT, 0, undefined, signal));
  const shown = useKept(activity);
  const [note, setNote] = useState("");
  const [noteError, setNoteError] = useState<string | null>(null);
  const [postError, setPostError] = useState<string | null>(null);
  const [posting, setPosting] = useState(false);
  const [message, setMessage] = useState("");
  const submitting = useRef(false);
  const noteRef = useRef<HTMLTextAreaElement>(null);

  const seen = useRef(version);
  const { retry } = activity;
  useEffect(() => {
    if (seen.current === version) return;
    seen.current = version;
    retry();
  }, [version, retry]);

  const post = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting.current) return;
    const comment = note.trim();
    if (!comment) {
      setNoteError("Write the note first.");
      noteRef.current?.focus();
      return;
    }
    submitting.current = true;
    setPosting(true);
    setNoteError(null);
    setPostError(null);
    try {
      await addWorkspaceComment(workspaceId, { comment });
      setNote("");
      setMessage("Note posted.");
      retry();
    } catch (err) {
      setPostError(actionError(err, "The note could not be posted."));
    } finally {
      submitting.current = false;
      setPosting(false);
    }
  };

  const items = shown?.items ?? [];

  return (
    <div className={styles.stack}>
      {can.contribute && (
        <section className={styles.section} aria-labelledby="item-note-heading">
          <h2 id="item-note-heading" className={styles.sectionTitle}>
            Post a note
          </h2>
          <form className={styles.form} onSubmit={post} noValidate>
            {postError && (
              <Alert tone="danger" announce>
                {postError}
              </Alert>
            )}
            <TextArea
              ref={noteRef}
              label="Note for the team"
              rows={3}
              value={note}
              error={noteError}
              onChange={(event) => {
                setNote(event.target.value);
                if (noteError) setNoteError(null);
              }}
            />
            <div className={styles.formActions}>
              <Button type="submit" loading={posting}>
                Post note
              </Button>
            </div>
          </form>
          <p role="status" className="rc-visually-hidden">
            {message}
          </p>
        </section>
      )}

      <section className={styles.section} aria-labelledby="item-activity-heading">
        <h2 id="item-activity-heading" className={styles.sectionTitle}>
          Activity
        </h2>
        {shown === undefined ? (
          activity.status === "error" ? (
            <ErrorState title="The activity could not be loaded" kind={activity.error?.kind === "network" ? "offline" : "failed"} onRetry={retry} />
          ) : (
            <SkeletonList rows={3} label="Loading activity" />
          )
        ) : items.length === 0 ? (
          <EmptyState title="Nothing has happened here yet." description="Changes to tasks, members and the submission appear here, with the notes the team posts." />
        ) : (
          <>
            <ol className={styles.list} aria-busy={activity.status === "loading" || undefined}>
              {items.map((entry) => (
                <li key={entry.id} className={styles.feedItem}>
                  <p className={styles.feedLine}>
                    <span className={styles.actor}>{entry.actor_name || "A collaborator"}</span> {entry.description}
                  </p>
                  {entry.comment && <p className={styles.comment}>{entry.comment}</p>}
                  <time className={styles.time} dateTime={entry.created_at}>
                    {dateTime(entry.created_at)}
                  </time>
                </li>
              ))}
            </ol>
            {shown && shown.total_count > items.length && (
              <p className={styles.time}>
                Showing the latest {items.length} of {shown.total_count}.
              </p>
            )}
          </>
        )}
      </section>
    </div>
  );
}
