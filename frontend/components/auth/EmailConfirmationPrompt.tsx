"use client";

import { useState } from "react";
import { ApiError, requestEmailConfirmation } from "../../services/api";
import { Button } from "../ui/Button/Button";
import { Alert } from "../ui/State/State";
import { useSession } from "./SessionProvider";
import styles from "./EmailConfirmationPrompt.module.css";

/**
 * Asks for the email that proves this account receives mail at its address (Decision C). The API's
 * words are used when it refuses, because they say what to do: this server may have no mail server.
 */
export function EmailConfirmationPrompt({ why }: { why: string }) {
  const { user, refresh } = useSession();
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = async () => {
    setSending(true);
    setError(null);
    try {
      const answer = await requestEmailConfirmation();
      if (answer.status === "ALREADY_VERIFIED") await refresh();
      else setSent(true);
    } catch (err) {
      setSent(false);
      setError(err instanceof ApiError && (err.status === 503 || err.status === 429) && err.detail ? err.detail : "The email could not be sent. Nothing was changed. Try again.");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className={styles.prompt}>
      <p className={styles.why}>{why}</p>
      {sent && (
        <Alert tone="success" announce title={`We sent a link to ${user?.email ?? "your address"}.`}>
          Open it and stay signed in to this account. It works once, for 24 hours. A newer email replaces it.
        </Alert>
      )}
      {error && (
        <Alert tone="danger" announce>
          {error}
        </Alert>
      )}
      <div>
        <Button size="sm" variant={sent ? "secondary" : "primary"} loading={sending} onClick={() => void send()}>
          {sent ? "Send the email again" : "Send the confirmation email"}
        </Button>
      </div>
    </div>
  );
}
