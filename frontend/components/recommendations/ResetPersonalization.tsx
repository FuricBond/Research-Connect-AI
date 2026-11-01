"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { Button } from "../ui/Button/Button";
import styles from "./Recommendations.module.css";

const ResetDialog = dynamic(() => import("./ResetDialog").then((loaded) => loaded.ResetDialog), { ssr: false });

/**
 * Reset what personalization learned (Phase 5.6), behind a confirmation (P12: its code loads when
 * asked for; until it arrives nothing is shown or sent).
 */
export function ResetPersonalization({ profileId, onReset }: { profileId: string; onReset: () => void }) {
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState("");

  return (
    <div className={styles.group}>
      <h3 className={styles.groupTitle}>Start over</h3>
      <p className={styles.muted}>Clears what was learned from your activity. What you stated stays.</p>
      <div>
        <Button variant="secondary" size="sm" leadingIcon={<RotateCcw size={16} aria-hidden="true" />} onClick={() => setOpen(true)}>
          Reset what was learned
        </Button>
      </div>
      <p role="status" className={styles.notice}>
        {notice}
      </p>

      {open && (
        <ResetDialog
          profileId={profileId}
          onClose={() => setOpen(false)}
          onDone={() => {
            setOpen(false);
            setNotice("What was learned has been reset. Your stated preferences and profile are unchanged.");
            onReset();
          }}
        />
      )}
    </div>
  );
}
