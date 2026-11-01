"use client";

import { useId, type ReactNode } from "react";
import { cx } from "../../../utils/cx";
import styles from "./Field.module.css";

export interface RadioOption {
  value: string;
  label: ReactNode;
  hint?: ReactNode;
  disabled?: boolean;
}

interface RadioGroupProps {
  legend: ReactNode;
  name: string;
  options: RadioOption[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

/** Radios grouped under a visible legend; arrow keys move between them natively. */
export function RadioGroup({ legend, name, options, value, onChange, className }: RadioGroupProps) {
  const generated = useId();
  return (
    <fieldset className={cx(styles.group, className)}>
      <legend className={cx(styles.label, styles.legend)}>{legend}</legend>
      {options.map((option) => {
        const id = `${name}-${generated}-${option.value}`;
        return (
          <label key={option.value} className={styles.check} htmlFor={id}>
            <input
              id={id}
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              disabled={option.disabled}
              onChange={() => onChange(option.value)}
            />
            <span className={styles.checkLabel}>{option.label}</span>
            {option.hint && <span className={cx(styles.hint, styles.checkHint)}>{option.hint}</span>}
          </label>
        );
      })}
    </fieldset>
  );
}
