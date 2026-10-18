"use client";

import { useEffect, useState } from "react";
import { Bookmark, BookmarkCheck } from "lucide-react";
import { addToReadingList } from "../../services/api";
import { useSession } from "../auth/SessionProvider";
import { Button, type ButtonSize, type ButtonVariant } from "../ui/Button/Button";

interface SaveToReadingListButtonProps {
  workId: string;
  /** Whether the work is already on the list, as far as the page knows. */
  isSaved?: boolean;
  onSaved?: (workId: string, itemId: string) => void;
  /** Secondary in lists; the paper panel makes it its primary action (P5). */
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Id of the paper's title, so the button is announced with the paper it saves. */
  describedBy?: string;
}

/**
 * Saves a research work to the signed-in user's reading list.
 *
 * Rendered only for a signed-in user: the list is personal, so there is nothing to save to
 * without an account. Saving is idempotent on the server, and it records no personalization
 * signal. P5: drawn with the Button primitive; the names and behaviour are unchanged.
 */
export function SaveToReadingListButton({ workId, isSaved = false, onSaved, variant = "secondary", size = "sm", describedBy }: SaveToReadingListButtonProps) {
  const { status } = useSession();
  const [saved, setSaved] = useState(isSaved);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  // The saved state can arrive after the first render, once the page has looked it up.
  useEffect(() => {
    if (isSaved) setSaved(true);
  }, [isSaved]);

  if (status !== "authenticated") return null;

  const save = async () => {
    if (saved || saving) return;
    setSaving(true);
    setFailed(false);
    try {
      const item = await addToReadingList(workId);
      setSaved(true);
      onSaved?.(workId, item.id);
    } catch {
      // The server's text never reaches the screen.
      setFailed(true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Button
        variant={saved ? "secondary" : variant}
        size={size}
        onClick={save}
        loading={saving}
        aria-pressed={saved}
        aria-label={saved ? "Saved to reading list" : "Save to reading list"}
        aria-describedby={describedBy}
        title={saved ? "On your reading list" : "Save to your reading list"}
        leadingIcon={saved ? <BookmarkCheck size={16} aria-hidden="true" /> : <Bookmark size={16} aria-hidden="true" />}
      >
        {saved ? "Saved" : "Save"}
      </Button>
      {failed && (
        <span className="rc-small rc-text-secondary" role="alert">
          Could not save to your reading list. Try again.
        </span>
      )}
    </>
  );
}
