"use client";

import { forwardRef, useState, type ComponentProps } from "react";
import { Eye, EyeOff } from "lucide-react";
import { cx } from "../../../utils/cx";
import { Field, type FieldChrome } from "./Field";
import styles from "./Field.module.css";

type InputProps = FieldChrome & Omit<ComponentProps<"input">, "className"> & { inputClassName?: string };

type PasswordInputProps = Omit<InputProps, "type"> & {
  /** The toggle's name; name the field when a form has several ("Show new password"). */
  revealLabel?: string;
};

/**
 * A password field with a toggle that shows what was typed (DESIGN_SYSTEM.md §8.2). The toggle
 * is named by its own (visually hidden) text, not aria-label, so it never doubles as a label
 * for the field, and `aria-pressed` says whether the password is shown.
 */
export const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(function PasswordInput(
  { label, hint, error, required, className, inputClassName, id, revealLabel = "Show password", ...rest },
  ref
) {
  const [shown, setShown] = useState(false);
  return (
    <Field id={id} label={label} hint={hint} error={error} required={required} className={className}>
      {(control) => (
        <div className={styles.password}>
          <input ref={ref} type={shown ? "text" : "password"} className={cx(styles.control, styles.passwordControl, inputClassName)} {...control} {...rest} />
          <button type="button" className={styles.reveal} aria-pressed={shown} aria-controls={control.id} onClick={() => setShown((value) => !value)}>
            {shown ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
            <span className="rc-visually-hidden">{revealLabel}</span>
          </button>
        </div>
      )}
    </Field>
  );
});
