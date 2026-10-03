"use client";

import { useEffect, useState } from "react";
import { Bookmark, BookmarkCheck } from "lucide-react";
import { addToReadingList } from "../../services/api";
import { useSession } from "../auth/SessionProvider";

interface SaveToReadingListButtonProps {
  workId: string;
  /** Whether the work is already on the list, as far as the page knows. */
  isSaved?: boolean;
  onSaved?: (workId: string, itemId: string) => void;
}

/**
 * Saves a research work to the signed-in user's reading list.
 *
 * Rendered only for a signed-in user: the list is personal, so there is nothing to save to
 * without an account. Saving is idempotent on the server, and it records no personalization
 * signal.
 */
export function SaveToReadingListButton({ workId, isSaved = false, onSaved }: SaveToReadingListButtonProps) {
  const { status } = useSession();
  const [saved, setSaved] = useState(isSaved);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The saved state can arrive after the first render, once the page has looked it up.
  useEffect(() => {
    if (isSaved) setSaved(true);
  }, [isSaved]);

  if (status !== "authenticated") return null;

  const save = async () => {
    if (saved || saving) return;
    setSaving(true);
    setError(null);
    try {
      const item = await addToReadingList(workId);
      setSaved(true);
      onSaved?.(workId, item.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save to your reading list");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <button
        type="button"
        className="action-btn secondary-btn"
        onClick={save}
        disabled={saving}
        aria-pressed={saved}
        aria-label={saved ? "Saved to reading list" : "Save to reading list"}
        title={saved ? "On your reading list" : "Save to your reading list"}
      >
        {saved ? <BookmarkCheck size={15} /> : <Bookmark size={15} />}
        <span>{saved ? "Saved" : "Save"}</span>
      </button>
      {error && (
        <span className="meta-item" role="alert">
          {error}
        </span>
      )}
    </>
  );
}
