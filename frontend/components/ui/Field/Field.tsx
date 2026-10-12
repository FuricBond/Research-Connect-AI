"use client";

import { forwardRef, useId, useState, type ComponentProps, type ReactNode } from "react";
import { AlertCircle, Eye, EyeOff, Search, X } from "lucide-react";
import { cx } from "../../../utils/cx";
import { IconButton } from "../Button/Button";
import styles from "./Field.module.css";

/** What a field passes to the control it labels. */
export interface ControlProps {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
  required?: boolean;
}

interface FieldChrome {
  /** Always visible: placeholder text is never the only label. */
  label: ReactNode;
  hint?: ReactNode;
  /** Shown under the control, linked with aria-describedby, and marks the control invalid. */
  error?: ReactNode;
  required?: boolean;
  className?: string;
}

export interface FieldProps extends FieldChrome {
  id?: string;
  children: (control: ControlProps) => ReactNode;
}

/** Label + control + hint + error, wired for assistive technology. DESIGN_SYSTEM.md §8.2. */
export function Field({ id, label, hint, error, required, className, children }: FieldProps) {
  const generated = useId();
  const controlId = id ?? `field-${generated}`;
  const hintId = hint ? `${controlId}-hint` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cx(styles.field, className)}>
      <label className={styles.label} htmlFor={controlId}>
        {label}
        {required && <span className={styles.required}>(required)</span>}
      </label>
      {children({ id: controlId, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined, required })}
      {hint && (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className={styles.error}>
          <AlertCircle size={14} aria-hidden="true" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}

type InputProps = FieldChrome & Omit<ComponentProps<"input">, "className"> & { inputClassName?: string };

/** Text, email, password, number, URL and date inputs. */
export const TextInput = forwardRef<HTMLInputElement, InputProps>(function TextInput(
  { label, hint, error, required, className, inputClassName, id, type = "text", ...rest },
  ref
) {
  return (
    <Field id={id} label={label} hint={hint} error={error} required={required} className={className}>
      {(control) => <input ref={ref} type={type} className={cx(styles.control, inputClassName)} {...control} {...rest} />}
    </Field>
  );
});

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

type TextAreaProps = FieldChrome & Omit<ComponentProps<"textarea">, "className">;

export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(function TextArea(
  { label, hint, error, required, className, id, ...rest },
  ref
) {
  return (
    <Field id={id} label={label} hint={hint} error={error} required={required} className={className}>
      {(control) => <textarea ref={ref} className={styles.control} {...control} {...rest} />}
    </Field>
  );
});

type SelectProps = FieldChrome & Omit<ComponentProps<"select">, "className">;

/** A native select: the most accessible picker, and the platform's own on phones. */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, error, required, className, id, children, ...rest },
  ref
) {
  return (
    <Field id={id} label={label} hint={hint} error={error} required={required} className={className}>
      {(control) => (
        <select ref={ref} className={styles.control} {...control} {...rest}>
          {children}
        </select>
      )}
    </Field>
  );
});

type SearchInputProps = Omit<ComponentProps<"input">, "className" | "type"> & {
  /** The accessible name; shown as a visible label unless `hideLabel`. */
  label: string;
  hideLabel?: boolean;
  /** Shows one clear button while there is text. */
  onClear?: () => void;
  className?: string;
};

export const SearchInput = forwardRef<HTMLInputElement, SearchInputProps>(function SearchInput(
  { label, hideLabel, onClear, className, id, value, ...rest },
  ref
) {
  const generated = useId();
  const inputId = id ?? `search-${generated}`;
  const hasText = typeof value === "string" ? value.length > 0 : false;
  return (
    <div className={cx(styles.field, className)}>
      <label className={cx(styles.label, hideLabel && "rc-visually-hidden")} htmlFor={inputId}>
        {label}
      </label>
      <div className={styles.search}>
        <Search size={16} className={styles.searchIcon} aria-hidden="true" />
        <input ref={ref} id={inputId} type="search" className={cx(styles.control, styles.searchControl)} value={value} {...rest} />
        {onClear && hasText && (
          <IconButton className={styles.clear} size="sm" label="Clear search" icon={<X size={16} aria-hidden="true" />} onClick={onClear} />
        )}
      </div>
    </div>
  );
});

type CheckboxProps = Omit<ComponentProps<"input">, "type" | "className"> & { label: ReactNode; hint?: ReactNode; className?: string };

/** A native checkbox with its label to the right; 24px hit area. */
export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox({ label, hint, className, id, ...rest }, ref) {
  const generated = useId();
  const inputId = id ?? `check-${generated}`;
  const hintId = hint ? `${inputId}-hint` : undefined;
  return (
    <label className={cx(styles.check, className)} htmlFor={inputId}>
      <input ref={ref} id={inputId} type="checkbox" aria-describedby={hintId} {...rest} />
      <span className={styles.checkLabel}>{label}</span>
      {hint && (
        <span id={hintId} className={cx(styles.hint, styles.checkHint)}>
          {hint}
        </span>
      )}
    </label>
  );
});

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
