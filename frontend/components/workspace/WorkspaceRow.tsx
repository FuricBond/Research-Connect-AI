"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId } from "react";
import { ArrowRight, MoreHorizontal } from "lucide-react";
import type { WorkspaceItem, WorkspaceItemUpdatePayload, WorkspaceStatus } from "../../types/workspace";
import { callTypeLabel, deliveryModeLabel } from "../../utils/research";
import { workspaceDeadline } from "../../utils/workspace";
import { DeadlineCountdown } from "../research/DeadlineCountdown";
import { RiskIndicator } from "../research/RiskIndicator";
import { PriorityLabel } from "../ui/Badge/Badge";
import { Menu } from "../ui/Menu/Menu";
import { ItemNotesForm } from "./ItemNotesForm";
import { StatusMenu } from "./StatusMenu";
import styles from "./Workspace.module.css";

export const itemHref = (id: string, tab?: string) => `/workspace/${encodeURIComponent(id)}${tab ? `?tab=${tab}` : ""}`;

/** The next step for an item, by its status: where the work continues. */
export function nextStep(status: WorkspaceStatus): string | null {
  if (status === "SAVED" || status === "CONSIDERING" || status === "PLANNING") return "Draft submission";
  if (status === "APPLIED" || status === "ACCEPTED" || status === "REJECTED") return "Open submission";
  return null;
}

interface WorkspaceRowProps {
  item: WorkspaceItem;
  saving: boolean;
  onStatus: (item: WorkspaceItem, target: WorkspaceStatus) => void;
  onUpdate: (item: WorkspaceItem, payload: WorkspaceItemUpdatePayload) => Promise<boolean>;
  onRemove: (item: WorkspaceItem) => void;
}

/**
 * One tracked call (plan §13): title, type, deadline and venue risk; the status as a menu of the
 * allowed moves; priority as a word with its glyph; the next step; and an overflow menu (Open,
 * Collaborate, Archive or Restore, Remove). Notes, tags and priority sit behind one disclosure.
 * `workspace-card` stays on the row as a stable hook for tests.
 */
export function WorkspaceRow({ item, saving, onStatus, onUpdate, onRemove }: WorkspaceRowProps) {
  const router = useRouter();
  const titleId = `workspace-item-${useId()}`;
  const opp = item.opportunity;
  const title = opp?.title || "Untitled call";
  const deadline = workspaceDeadline(opp);
  const facts = [opp?.opportunity_type ? callTypeLabel(opp.opportunity_type) : null, opp?.publisher || opp?.organizer, opp?.location, deliveryModeLabel(opp?.delivery_mode)].filter(Boolean);
  const step = nextStep(item.status);
  const archived = item.status === "ARCHIVED";

  return (
    <li className={`${styles.row} workspace-card`} aria-labelledby={titleId}>
      <div className={styles.rowMain}>
        <h3 className={styles.rowTitle}>
          <Link id={titleId} href={itemHref(item.id)} className={styles.rowTitleLink}>
            {title}
          </Link>
        </h3>
        {facts.length > 0 && <p className={styles.rowFacts}>{facts.join(" · ")}</p>}
        {opp && (
          <div className={styles.rowSignals}>
            <DeadlineCountdown deadline={deadline.deadline} daysRemaining={deadline.daysRemaining} status={deadline.status} urgencyTier={deadline.urgencyTier} />
            <RiskIndicator level={opp.risk_explanation?.risk_level ?? null} isPredatory={opp.is_predatory_flag} />
          </div>
        )}
      </div>

      <div className={styles.rowControls}>
        <StatusMenu item={item} saving={saving} describedBy={titleId} onChange={(target) => onStatus(item, target)} />
        <PriorityLabel priority={item.priority} />
        {step && (
          <Link href={itemHref(item.id, "submission")} className={styles.nextStep} aria-describedby={titleId}>
            {step}
            <ArrowRight size={14} aria-hidden="true" />
          </Link>
        )}
        <Menu
          align="end"
          triggerLabel={`More actions for ${title}`}
          triggerClassName={styles.moreTrigger}
          trigger={<MoreHorizontal size={16} aria-hidden="true" />}
          disabled={saving}
          items={[
            { id: "open", label: "Open", onSelect: () => router.push(itemHref(item.id)) },
            { id: "collaborate", label: "Collaborate", onSelect: () => router.push(itemHref(item.id, "members")) },
            archived
              ? { id: "restore", label: "Restore", onSelect: () => onStatus(item, "SAVED"), disabled: !item.allowed_transitions.includes("SAVED") }
              : { id: "archive", label: "Archive", onSelect: () => onStatus(item, "ARCHIVED"), disabled: !item.allowed_transitions.includes("ARCHIVED") },
            { id: "remove", label: "Remove from workspace", danger: true, onSelect: () => onRemove(item) },
          ]}
        />
      </div>

      <details className={styles.rowDetails}>
        <summary>
          Notes, tags and priority<span className="rc-visually-hidden"> for {title}</span>
        </summary>
        <ItemNotesForm item={item} title={title} saving={saving} onUpdate={onUpdate} />
      </details>
    </li>
  );
}
