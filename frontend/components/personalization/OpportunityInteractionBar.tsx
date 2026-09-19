"use client";

import React, { useState } from "react";
import {
  Bookmark,
  Check,
  EyeOff,
  Share2,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import { recordOpportunityInteraction } from "../../services/api";
import type {
  InteractionResponse,
  InteractionType,
} from "../../types/personalization";

interface OpportunityInteractionBarProps {
  profileId: string;
  opportunityId: string;
  userId?: string;
  initialSaved?: boolean;
  onInteractionRecorded?: (interaction: InteractionResponse) => void;
  className?: string;
}

export const OpportunityInteractionBar: React.FC<OpportunityInteractionBarProps> = ({
  profileId,
  opportunityId,
  userId,
  initialSaved = false,
  onInteractionRecorded,
  className = "",
}) => {
  const [activeType, setActiveType] = useState<InteractionType | null>(null);
  const [isSaved, setIsSaved] = useState<boolean>(initialSaved);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);

  const handleInteraction = async (type: InteractionType) => {
    if (isSubmitting || !profileId || !opportunityId) return;

    setIsSubmitting(true);
    setFeedbackMessage(null);

    // Optimistic toggle for saved
    if (type === "SAVED") {
      setIsSaved((prev) => !prev);
    }
    setActiveType(type);

    try {
      const response = await recordOpportunityInteraction(
        profileId,
        opportunityId,
        {
          interaction_type: type,
          source: "RECOMMENDATION",
          client_event_id: `client-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
        },
        userId
      );

      if (type === "SAVED") {
        setIsSaved(true);
        setFeedbackMessage("Saved to workspace");
      } else if (type === "INTERESTED") {
        setFeedbackMessage("Marked interested");
      } else if (type === "NOT_INTERESTED") {
        setFeedbackMessage("Marked not interested");
      } else if (type === "DISMISSED") {
        setFeedbackMessage("Opportunity dismissed");
      } else if (type === "HIDDEN") {
        setFeedbackMessage("Opportunity hidden");
      } else if (type === "SHARED") {
        setFeedbackMessage("Link copied / shared");
      }

      onInteractionRecorded?.(response);

      // Clear transient feedback message after 2.5s
      setTimeout(() => {
        setFeedbackMessage(null);
      }, 2500);
    } catch (err: unknown) {
      console.error("Failed to record interaction:", err);
      // Revert optimistic save if failed
      if (type === "SAVED") {
        setIsSaved(initialSaved);
      }
      setActiveType(null);
      setFeedbackMessage(err instanceof Error ? err.message : "Action failed");
      setTimeout(() => {
        setFeedbackMessage(null);
      }, 3000);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className={`flex items-center gap-1.5 flex-wrap ${className}`}
      role="toolbar"
      aria-label="Opportunity interaction actions"
    >
      {/* Save / Bookmark Button */}
      <button
        type="button"
        onClick={() => handleInteraction("SAVED")}
        disabled={isSubmitting}
        aria-label={isSaved ? "Saved to workspace" : "Save opportunity"}
        title={isSaved ? "Saved to workspace" : "Save to workspace"}
        className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
          isSaved
            ? "bg-purple-100 text-purple-800 border border-purple-200"
            : "text-gray-600 hover:text-purple-700 hover:bg-purple-50 border border-gray-200"
        } disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        <Bookmark className={`w-3.5 h-3.5 ${isSaved ? "fill-current text-purple-700" : ""}`} />
        <span>{isSaved ? "Saved" : "Save"}</span>
      </button>

      {/* Interested (Thumbs Up) */}
      <button
        type="button"
        onClick={() => handleInteraction("INTERESTED")}
        disabled={isSubmitting}
        aria-label="Mark interested"
        title="Mark as interested"
        className={`p-1.5 rounded-md border transition-colors ${
          activeType === "INTERESTED"
            ? "bg-emerald-100 text-emerald-800 border-emerald-300"
            : "text-gray-500 hover:text-emerald-700 hover:bg-emerald-50 border-gray-200"
        } disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        <ThumbsUp className="w-3.5 h-3.5" />
      </button>

      {/* Not Interested (Thumbs Down) */}
      <button
        type="button"
        onClick={() => handleInteraction("NOT_INTERESTED")}
        disabled={isSubmitting}
        aria-label="Mark not interested"
        title="Mark as not interested"
        className={`p-1.5 rounded-md border transition-colors ${
          activeType === "NOT_INTERESTED"
            ? "bg-rose-100 text-rose-800 border-rose-300"
            : "text-gray-500 hover:text-rose-700 hover:bg-rose-50 border-gray-200"
        } disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        <ThumbsDown className="w-3.5 h-3.5" />
      </button>

      {/* Dismiss (Skip) */}
      <button
        type="button"
        onClick={() => handleInteraction("DISMISSED")}
        disabled={isSubmitting}
        aria-label="Dismiss opportunity"
        title="Dismiss / Skip from current feed"
        className={`p-1.5 rounded-md border transition-colors ${
          activeType === "DISMISSED"
            ? "bg-amber-100 text-amber-800 border-amber-300"
            : "text-gray-500 hover:text-amber-700 hover:bg-amber-50 border-gray-200"
        } disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        <X className="w-3.5 h-3.5" />
      </button>

      {/* Hide (Filter out) */}
      <button
        type="button"
        onClick={() => handleInteraction("HIDDEN")}
        disabled={isSubmitting}
        aria-label="Hide opportunity"
        title="Hide from recommendations"
        className={`p-1.5 rounded-md border transition-colors ${
          activeType === "HIDDEN"
            ? "bg-gray-200 text-gray-800 border-gray-300"
            : "text-gray-500 hover:text-gray-800 hover:bg-gray-100 border-gray-200"
        } disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        <EyeOff className="w-3.5 h-3.5" />
      </button>

      {/* Share */}
      <button
        type="button"
        onClick={() => handleInteraction("SHARED")}
        disabled={isSubmitting}
        aria-label="Share opportunity"
        title="Share opportunity"
        className={`p-1.5 rounded-md border transition-colors ${
          activeType === "SHARED"
            ? "bg-blue-100 text-blue-800 border-blue-300"
            : "text-gray-500 hover:text-blue-700 hover:bg-blue-50 border-gray-200"
        } disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        <Share2 className="w-3.5 h-3.5" />
      </button>

      {/* Transient Status Feedback */}
      {feedbackMessage && (
        <span
          className="inline-flex items-center gap-1 text-[11px] font-medium text-gray-600 bg-gray-50 px-2 py-0.5 rounded border border-gray-200 animate-fade-in"
          role="status"
          aria-live="polite"
        >
          <Check className="w-3 h-3 text-emerald-600" />
          {feedbackMessage}
        </span>
      )}
    </div>
  );
};

export default OpportunityInteractionBar;
