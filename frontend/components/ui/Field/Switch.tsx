"use client";

import { useId, type ReactNode } from "react";
import { cx } from "../../../utils/cx";
import styles from "./Field.module.css";

interface SwitchProps {
  label: ReactNode;
  description?: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  /** Words for the state shown next to the switch. */
  stateLabels?: [on: string, off: string];
  className?: string;
}

/** For settings that apply immediately (not inside a form that needs Save). */
export function Switch({ label, description, checked, onChange, disabled, stateLabels = ["On", "Off"], className }: SwitchProps) {
  const generated = useId();
  const labelId = `switch-${generated}-label`;
  const descriptionId = description ? `switch-${generated}-description` : undefined;
  return (
    <div className={cx(styles.switchRow, className)}>
      <div className={styles.switchText}>
        <span id={labelId} className={styles.label}>
          {label}
        </span>
        {description && (
          <span id={descriptionId} className={styles.hint}>
            {description}
          </span>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={labelId}
        aria-describedby={descriptionId}
        disabled={disabled}
        className={styles.switch}
        onClick={() => onChange(!checked)}
      >
        <span className={styles.track} aria-hidden="true">
          <span className={styles.thumb} />
        </span>
        <span aria-hidden="true">{checked ? stateLabels[0] : stateLabels[1]}</span>
      </button>
    </div>
  );
}
