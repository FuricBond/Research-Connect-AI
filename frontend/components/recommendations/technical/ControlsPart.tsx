"use client";

import { useApiResource } from "../../../hooks/useApiResource";
import { fetchPersonalizationControlHistory } from "../../../services/api";
import type { PersonalizationControlEventType } from "../../../types/personalization";
import { humanizeEnum } from "../../../utils/date";
import { Loaded, when } from "./shared";
import styles from "../Recommendations.module.css";

const EVENT: Record<PersonalizationControlEventType, string> = {
  PERSONALIZATION_ENABLED: "Personalization turned on",
  PERSONALIZATION_DISABLED: "Personalization turned off",
  ADAPTIVE_SIGNALS_ENABLED: "Learned signals used",
  ADAPTIVE_SIGNALS_DISABLED: "Learned signals not used",
  FEEDBACK_LEARNING_ENABLED: "Learning from new activity",
  FEEDBACK_LEARNING_DISABLED: "Learning paused",
  PERSONALIZATION_RESET: "What was learned was reset",
};

/** Changes to the personalization settings, with the reason given (Phase 5.9's audit log). */
export default function ControlsPart({ profileId }: { profileId: string }) {
  const history = useApiResource(`technical:controls:${profileId}`, (signal) => fetchPersonalizationControlHistory(profileId, 20, 0, undefined, signal));
  return (
    <Loaded resource={history} label="Loading changes to your settings" failure="Changes to your settings could not be loaded.">
      {(data) =>
        data.events.length === 0 ? (
          <p className={styles.muted}>No changes to your personalization settings yet.</p>
        ) : (
          <ul className={styles.records} aria-label="Changes to your personalization settings">
            {data.events.map((event) => (
              <li key={event.id} className={styles.record}>
                <span className={styles.recordHead}>
                  <span className={styles.recordTitle}>{EVENT[event.event_type] ?? humanizeEnum(event.event_type)}</span>
                  <span className={styles.numbers}>{when(event.created_at)}</span>
                </span>
                {event.trigger_reason && <span>{event.trigger_reason}</span>}
              </li>
            ))}
          </ul>
        )
      }
    </Loaded>
  );
}
