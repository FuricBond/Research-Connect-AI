"use client";

import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ApiError, confirmEmail } from "../../services/api";
import { Button } from "../ui/Button/Button";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { Alert } from "../ui/State/State";
import { EmailConfirmationPrompt } from "./EmailConfirmationPrompt";
import { RequireAuth } from "./RequireAuth";
import { useSession } from "./SessionProvider";

const HELD_TOKEN = "researchconnect_email_confirmation";

function readHeld(): string | null {
  try {
    return window.sessionStorage.getItem(HELD_TOKEN);
  } catch {
    return null;
  }
}

function forgetHeld() {
  try {
    window.sessionStorage.removeItem(HELD_TOKEN);
  } catch {
    // Site data blocked: nothing was held.
  }
}

/**
 * `/verify-email#token=…`, the link in the confirmation email (Decision C). The token travels after
 * the `#`, so it reaches no server log and no Referer, and leaves the address bar at once. It is
 * held for this tab while the person signs in, because confirming needs the account that asked:
 * someone else's link confirms nothing, and someone who cannot sign in to that account cannot use it.
 */
export function VerifyEmailPage() {
  // Before RequireAuth's effect can send a visitor to sign in, which would drop the address.
  useLayoutEffect(() => {
    const match = /^#token=([\w-]+)$/.exec(window.location.hash);
    if (!match) return;
    try {
      window.sessionStorage.setItem(HELD_TOKEN, match[1]);
    } catch {
      // Site data blocked: the page below offers a new email.
    }
    window.history.replaceState(null, "", window.location.pathname);
  }, []);

  return (
    <RequireAuth>
      <Confirmation />
    </RequireAuth>
  );
}

function Confirmation() {
  const { user, refresh } = useSession();
  const [state, setState] = useState<"working" | "done" | "refused" | "failed" | "no-link">("working");
  const [refusal, setRefusal] = useState<string | null>(null);
  const started = useRef(false);

  const run = useCallback(async () => {
    const token = readHeld();
    if (!token) {
      setState("no-link");
      return;
    }
    setState("working");
    try {
      await confirmEmail(token);
      forgetHeld();
      await refresh();
      setState("done");
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        forgetHeld();
        setRefusal(err.detail ?? "This link does not confirm this account's address.");
        setState("refused");
      } else {
        setState("failed");
      }
    }
  }, [refresh]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void run();
  }, [run]);

  return (
    <>
      <PageHeader title="Confirm your email address" description={`Signed in as ${user?.email ?? "your account"}.`} />
      {state === "working" && <p role="status">Confirming your address…</p>}
      {(state === "done" || (state === "no-link" && user?.email_verified)) && (
        <Alert tone="success" announce title="Your email address is confirmed.">
          Workspace invitations sent to it now appear on <Link href="/notifications#invitations">your notifications page</Link>.
        </Alert>
      )}
      {state === "failed" && (
        <Alert tone="danger" announce action={<Button size="sm" onClick={() => void run()}>Try again</Button>}>
          Your address could not be confirmed just now. Nothing was changed.
        </Alert>
      )}
      {state === "refused" && (
        <Alert tone="danger" announce>
          {refusal}
        </Alert>
      )}
      {(state === "refused" || (state === "no-link" && !user?.email_verified)) && (
        <EmailConfirmationPrompt why={`Send a new link to ${user?.email ?? "your address"}. It only works for this account.`} />
      )}
    </>
  );
}
