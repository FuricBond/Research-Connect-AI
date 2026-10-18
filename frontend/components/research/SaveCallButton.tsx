"use client";

import { useEffect, useState } from "react";
import { Bookmark, BookmarkCheck } from "lucide-react";
import { addOpportunityToWorkspace } from "../../services/api";
import type { WorkspaceItem } from "../../types/workspace";
import { useSession } from "../auth/SessionProvider";
import { Button, type ButtonSize, type ButtonVariant } from "../ui/Button/Button";

interface SaveCallButtonProps {
  opportunityId: string;
  /** Whether the call is already in the workspace, as far as the page knows. */
  isSaved?: boolean;
  onSaved?: (item: WorkspaceItem) => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Id of the call's title, so the button is announced with the call it saves. */
  describedBy?: string;
}

/**
 * P5 — "Save to workspace" for a call (DESIGN_SYSTEM.md §9 OpportunityCard). Signed-in only: the
 * workspace is personal. The server answers an already-tracked call with its existing item, so
 * saving twice is harmless. It records no personalization signal (the recommendation list's own
 * save button does that). The server's text never reaches the screen.
 */
export function SaveCallButton({ opportunityId, isSaved = false, onSaved, variant = "secondary", size = "sm", describedBy }: SaveCallButtonProps) {
  const { status } = useSession();
  const [saved, setSaved] = useState(isSaved);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (isSaved) setSaved(true);
  }, [isSaved]);

  if (status !== "authenticated") return null;

  const save = async () => {
    if (saved || saving) return;
    setSaving(true);
    setFailed(false);
    try {
      const item = await addOpportunityToWorkspace({ opportunity_id: opportunityId });
      setSaved(true);
      onSaved?.(item);
    } catch {
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
        aria-label={saved ? "Saved to workspace" : "Save to workspace"}
        aria-describedby={describedBy}
        leadingIcon={saved ? <BookmarkCheck size={16} aria-hidden="true" /> : <Bookmark size={16} aria-hidden="true" />}
      >
        {saved ? "Saved" : "Save"}
      </Button>
      {failed && (
        <span className="rc-small rc-text-secondary" role="alert">
          Could not save to your workspace. Try again.
        </span>
      )}
    </>
  );
}
