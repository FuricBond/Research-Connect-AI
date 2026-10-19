"use client";

import { useCallback, useRef, useState } from "react";
import { transitionApplication } from "../../services/api";
import type { ApplicationStatus, PostingApplication } from "../../types/posting";
import { applicationStatusMeta } from "../../utils/status";
import { decisionFailed, isNewer } from "../../utils/postings";
import { changeError } from "./errors";

export interface DecisionFailure {
  application: PostingApplication;
  target: ApplicationStatus;
  message: string;
}

/**
 * P9 — a posting author's decisions on applications, for the inbox and a posting's own page.
 *
 * Nothing is shown before the server agrees: while a decision is sent its card waits (its actions
 * disabled, so a second click sends nothing), then shows the server's answer. A refused or failed
 * decision leaves the application as the server last confirmed it and says so. Each application's
 * newest request wins (an older answer arriving late is ignored), and an answer only replaces a
 * listed application that is not newer than it, so a reload and a decision can arrive in any
 * order without the older state coming back.
 */
export function useApplicationDecisions() {
  const [decided, setDecided] = useState<Record<string, PostingApplication>>({});
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());
  const [failure, setFailure] = useState<DecisionFailure | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const latest = useRef(new Map<string, number>());
  const sending = useRef(new Set<string>());
  const counter = useRef(0);

  /** The application as the server last confirmed it: the listed one or a newer decision's answer. */
  const current = useCallback(
    (listed: PostingApplication): PostingApplication => {
      const answer = decided[listed.id];
      return answer && isNewer(answer, listed) ? answer : listed;
    },
    [decided]
  );

  const decide = useCallback(async (application: PostingApplication, target: ApplicationStatus, options: { decisionReason?: string } = {}): Promise<boolean> => {
    if (sending.current.has(application.id) || !application.allowed_transitions.includes(target)) return false;
    const mine = ++counter.current;
    latest.current.set(application.id, mine);
    sending.current.add(application.id);
    setPending((before) => new Set(before).add(application.id));
    setFailure(null);
    const name = application.applicant.full_name ?? "The applicant";
    try {
      const answer = await transitionApplication(application.id, target, { decisionReason: options.decisionReason?.trim() || undefined });
      if (latest.current.get(application.id) !== mine) return false;
      setDecided((before) => ({ ...before, [answer.id]: answer }));
      setAnnouncement(`${name}: ${applicationStatusMeta(answer.status).label}.`);
      return true;
    } catch (error) {
      if (latest.current.get(application.id) !== mine) return false;
      const message = changeError(error, decisionFailed(name, target));
      setFailure({ application, target, message });
      setAnnouncement(`${message} It is still ${applicationStatusMeta(application.status).label.toLowerCase()}.`);
      return false;
    } finally {
      if (latest.current.get(application.id) === mine) {
        sending.current.delete(application.id);
        setPending((before) => {
          const next = new Set(before);
          next.delete(application.id);
          return next;
        });
      }
    }
  }, []);

  return { current, decide, pending, failure, dismissFailure: () => setFailure(null), announcement };
}
