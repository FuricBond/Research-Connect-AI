"use client";

import { useRef, useState, type FormEvent } from "react";
import { Send } from "lucide-react";
import { ApiError, applyToPosting } from "../../services/api";
import { Button } from "../ui/Button/Button";
import { TextArea, TextInput } from "../ui/Field/Field";
import { Alert } from "../ui/State/State";
import styles from "./Faculty.module.css";

/**
 * The application form of a posting's page (Phase 5.11; P9 on the design system, loaded when
 * "Apply now" is pressed). Sent once; on failure what was written stays, with the reason.
 */
export function ApplyForm({ postingId, onCancel, onSubmitted }: { postingId: string; onCancel: () => void; onSubmitted: () => void }) {
  const [coverNote, setCoverNote] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [portfolioUrl, setPortfolioUrl] = useState("");
  const [sending, setSending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const inFlight = useRef(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setSending(true);
    setFailure(null);
    try {
      await applyToPosting(postingId, { cover_note: coverNote.trim() || null, contact_email: contactEmail.trim() || null, portfolio_url: portfolioUrl.trim() || null });
      onSubmitted();
    } catch (error) {
      setFailure(
        error instanceof ApiError && error.status === 409
          ? "You have already applied to this opening."
          : error instanceof ApiError && error.status === 400
            ? "This opening is not taking applications any more."
            : error instanceof ApiError && error.status === 422
              ? "Check the email address and the link, then try again."
              : "Your application could not be submitted. What you wrote is kept; try again."
      );
    } finally {
      inFlight.current = false;
      setSending(false);
    }
  };

  return (
    <form className={styles.applyForm} onSubmit={onSubmit}>
      <TextArea id="cover-note" label="Statement of interest" hint="What draws you to this work." maxLength={5000} rows={6} value={coverNote} onChange={(event) => setCoverNote(event.target.value)} />
      <div className={styles.formGrid}>
        <TextInput id="apply-email" label="Contact email" type="email" autoComplete="email" value={contactEmail} onChange={(event) => setContactEmail(event.target.value)} />
        <TextInput id="apply-portfolio" label="CV or portfolio link" hint="Optional." type="url" value={portfolioUrl} onChange={(event) => setPortfolioUrl(event.target.value)} />
      </div>
      {failure && (
        <Alert tone="danger" announce>
          {failure}
        </Alert>
      )}
      <div className={styles.formActions}>
        <Button type="submit" variant="primary" loading={sending} disabled={sending} leadingIcon={<Send size={16} aria-hidden="true" />}>
          Submit application
        </Button>
        <Button variant="secondary" disabled={sending} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
