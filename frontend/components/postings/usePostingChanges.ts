"use client";

import { useCallback, useRef, useState } from "react";
import { deletePosting, transitionPosting } from "../../services/api";
import type { PostingStatus, ResearchPosting } from "../../types/posting";
import { isNewer } from "../../utils/postings";
import { postingStatusMeta } from "../../utils/status";
import { changeError } from "./errors";

export interface PostingFailure {
  posting: ResearchPosting;
  /** The status asked for, or null for deleting a draft. */
  target: PostingStatus | null;
  message: string;
}

/**
 * P9 — an author's lifecycle changes to their postings (My postings, a posting's own page), the
 * way decisions on applications work: only a move the server listed is sent, nothing is shown
 * before the server agrees, one request per posting at a time (a second click sends nothing), the
 * newest request's answer wins, and a failure leaves the posting as the server last confirmed it.
 * `onChanged` runs after every confirmed change (the filter counts are asked for again).
 */
export function usePostingChanges(onChanged?: () => void) {
  const [changed, setChanged] = useState<Record<string, ResearchPosting>>({});
  const [removed, setRemoved] = useState<ReadonlySet<string>>(new Set());
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());
  const [failure, setFailure] = useState<PostingFailure | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const latest = useRef(new Map<string, number>());
  const sending = useRef(new Set<string>());
  const counter = useRef(0);
  const onChangedRef = useRef(onChanged);
  onChangedRef.current = onChanged;

  const current = useCallback(
    (listed: ResearchPosting): ResearchPosting | null => {
      if (removed.has(listed.id)) return null;
      const answer = changed[listed.id];
      return answer && isNewer(answer, listed) ? answer : listed;
    },
    [changed, removed]
  );

  const begin = (id: string) => {
    if (sending.current.has(id)) return null;
    const mine = ++counter.current;
    latest.current.set(id, mine);
    sending.current.add(id);
    setPending((before) => new Set(before).add(id));
    setFailure(null);
    return mine;
  };
  const end = (id: string, mine: number) => {
    if (latest.current.get(id) !== mine) return;
    sending.current.delete(id);
    setPending((before) => {
      const next = new Set(before);
      next.delete(id);
      return next;
    });
  };

  const transition = useCallback(async (posting: ResearchPosting, target: PostingStatus): Promise<ResearchPosting | null> => {
    if (!posting.allowed_transitions.includes(target)) return null;
    const mine = begin(posting.id);
    if (mine === null) return null;
    try {
      const answer = await transitionPosting(posting.id, target);
      if (latest.current.get(posting.id) !== mine) return null;
      setChanged((before) => ({ ...before, [answer.id]: answer }));
      setAnnouncement(`“${answer.title}” is now ${postingStatusMeta(answer.status).label.toLowerCase()}.`);
      onChangedRef.current?.();
      return answer;
    } catch (error) {
      if (latest.current.get(posting.id) !== mine) return null;
      const message = changeError(error, `“${posting.title}” could not be changed.`);
      setFailure({ posting, target, message });
      setAnnouncement(`${message} It is still ${postingStatusMeta(posting.status).label.toLowerCase()}.`);
      return null;
    } finally {
      end(posting.id, mine);
    }
  }, []);

  const remove = useCallback(async (posting: ResearchPosting): Promise<boolean> => {
    if (posting.status !== "DRAFT") return false;
    const mine = begin(posting.id);
    if (mine === null) return false;
    try {
      await deletePosting(posting.id);
      if (latest.current.get(posting.id) !== mine) return false;
      setRemoved((before) => new Set(before).add(posting.id));
      setAnnouncement(`The draft “${posting.title}” was deleted.`);
      onChangedRef.current?.();
      return true;
    } catch (error) {
      if (latest.current.get(posting.id) !== mine) return false;
      const message = changeError(error, `The draft “${posting.title}” could not be deleted.`);
      setFailure({ posting, target: null, message });
      setAnnouncement(message);
      return false;
    } finally {
      end(posting.id, mine);
    }
  }, []);

  return { current, transition, remove, pending, failure, dismissFailure: () => setFailure(null), announcement };
}
