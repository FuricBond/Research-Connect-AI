"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { WorkspaceItem, WorkspaceItemUpdatePayload } from "../../../types/workspace";
import { DeadlineMilestones } from "../../research/DeadlineMilestones";
import { callHref } from "../../research/OpportunityCard";
import { ItemNotesForm } from "../ItemNotesForm";
import { nextStep } from "../WorkspaceRow";
import { shortDate, type Abilities } from "../workflow";
import type { ItemTab } from "./ItemPage";
import styles from "./Item.module.css";
import workspaceStyles from "../Workspace.module.css";

interface OverviewPanelProps {
  item: WorkspaceItem;
  can: Abilities;
  saving: boolean;
  onUpdate: (item: WorkspaceItem, payload: WorkspaceItemUpdatePayload) => Promise<boolean>;
  onOpenTab: (tab: ItemTab) => void;
}

/**
 * Overview: the next step, the call's dates (deadline timeline, with time zones and extensions
 * from the deadline intelligence), and the notes, tags and priority. Editors change them here;
 * other roles read them. Nothing here asks the server for more than the item itself.
 */
export function OverviewPanel({ item, can, saving, onUpdate, onOpenTab }: OverviewPanelProps) {
  const opp = item.opportunity;
  const title = opp?.title || "Untitled call";
  const step = nextStep(item.status);
  const updated = shortDate(item.status_updated_at);

  return (
    <div className={styles.overviewGrid}>
      <div className={styles.stack}>
        <section className={styles.section} aria-labelledby="item-dates-heading">
          <h2 id="item-dates-heading" className={styles.sectionTitle}>
            Dates
          </h2>
          {opp ? (
            <DeadlineMilestones
              intelligence={opp.deadline_intelligence}
              dates={{
                submission_deadline: opp.submission_deadline,
                notification_date: opp.notification_date,
                camera_ready_deadline: opp.camera_ready_deadline,
                event_start_date: opp.event_start_date,
              }}
            />
          ) : (
            <p className={styles.text}>{"The call's details are not available."}</p>
          )}
          {opp && (
            <div className={styles.links}>
              <Link href={callHref(item.opportunity_id)} className={workspaceStyles.nextStep}>
                Open the call for papers
                <ArrowRight size={14} aria-hidden="true" />
              </Link>
            </div>
          )}
        </section>

        <section className={styles.section} aria-labelledby="item-notes-heading">
          <h2 id="item-notes-heading" className={styles.sectionTitle}>
            Notes, tags and priority
          </h2>
          {can.edit ? (
            <ItemNotesForm item={item} title={title} saving={saving} onUpdate={onUpdate} />
          ) : (
            <>
              {item.notes ? <p className={styles.prose}>{item.notes}</p> : <p className={styles.text}>No notes yet.</p>}
              {item.tags.length > 0 && (
                <ul className={styles.tagList} aria-label={`Tags on ${title}`}>
                  {item.tags.map((tag) => (
                    <li key={tag} className={styles.tag}>
                      {tag}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>
      </div>

      <aside className={styles.nextStep} aria-labelledby="item-next-heading">
        <h2 id="item-next-heading" className={styles.sectionTitle}>
          Next step
        </h2>
        <p className={styles.text}>
          {step === "Draft submission"
            ? "Draft the submission: its details, the documents it needs and a readiness check."
            : step === "Open submission"
              ? "Keep the submission up to date: its status, documents and the decision."
              : "This call is archived. Restore it from the status menu to work on it again."}
        </p>
        {step && (
          <div>
            <button type="button" className={workspaceStyles.nextStep} onClick={() => onOpenTab("submission")}>
              {step}
              <ArrowRight size={14} aria-hidden="true" />
            </button>
          </div>
        )}
        {updated && <p className={styles.time}>Status last changed {updated}</p>}
      </aside>
    </div>
  );
}
