"use client";

import Link from "next/link";
import { forwardRef, useImperativeHandle, useRef, type ComponentProps, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cx } from "../../../utils/cx";
import styles from "./Button.module.css";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "danger-ghost" | "link";
export type ButtonSize = "sm" | "md" | "lg";

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: styles.primary,
  secondary: styles.secondary,
  ghost: styles.ghost,
  danger: styles.danger,
  "danger-ghost": styles.dangerGhost,
  link: styles.link,
};

interface Appearance {
  /** primary: the one main action of a section · secondary: everything else · ghost: toolbars ·
   *  danger: inside confirmations · danger-ghost: the entry point to a destructive action. */
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  leadingIcon?: ReactNode;
  trailingIcon?: ReactNode;
}

function buttonClass({ variant = "secondary", size = "md", fullWidth }: Appearance, className?: string, extra?: string) {
  return cx(styles.button, VARIANT_CLASS[variant], size !== "md" && styles[size], fullWidth && styles.fullWidth, extra, className);
}

export interface ButtonProps extends Appearance, ComponentProps<"button"> {
  /** Shows a spinner, keeps the label and width, and marks the button busy. */
  loading?: boolean;
}

/** DESIGN_SYSTEM.md §8.1. A native button; `type` defaults to "button". */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant, size, fullWidth, leadingIcon, trailingIcon, loading = false, className, children, type = "button", disabled, onClick, ...rest },
  ref
) {
  // P11: natively disabling a button that has focus (the person just pressed it) drops focus to the
  // page, and a refusal then leaves them nowhere. Held instead, while it works or has focus:
  // aria-disabled, looks the same, keeps focus, and a press does nothing (a submit's included).
  const own = useRef<HTMLButtonElement>(null);
  useImperativeHandle(ref, () => own.current as HTMLButtonElement);
  const focused = own.current !== null && own.current === own.current.ownerDocument.activeElement;
  const held = Boolean(disabled) && (loading || focused);
  return (
    <button
      ref={own}
      type={type}
      className={buttonClass({ variant, size, fullWidth }, className, loading ? styles.loading : undefined)}
      disabled={disabled && !held}
      aria-disabled={held || undefined}
      aria-busy={loading || undefined}
      onClick={held ? (event) => event.preventDefault() : onClick}
      {...rest}
    >
      {loading ? <Loader2 className={styles.spinner} aria-hidden="true" /> : leadingIcon}
      {children}
      {trailingIcon}
    </button>
  );
});

export interface ButtonLinkProps extends Appearance, Omit<ComponentProps<typeof Link>, "className"> {
  className?: string;
}

/** Navigation that looks like a button (a call to action). Plain navigation uses a link. */
export function ButtonLink({ variant, size, fullWidth, leadingIcon, trailingIcon, className, children, ...rest }: ButtonLinkProps) {
  return (
    <Link className={buttonClass({ variant, size, fullWidth }, className)} {...rest}>
      {leadingIcon}
      {children}
      {trailingIcon}
    </Link>
  );
}

export interface IconButtonProps extends Omit<ButtonProps, "children" | "leadingIcon" | "trailingIcon" | "fullWidth"> {
  /** Required: the control's accessible name (also shown as a tooltip). */
  label: string;
  icon: ReactNode;
}

/** A square button with a universally understood icon (close, more, refresh). */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, icon, variant = "ghost", size, className, title, ...rest },
  ref
) {
  return (
    <Button ref={ref} variant={variant} size={size} className={cx(styles.icon, className)} aria-label={label} title={title ?? label} {...rest}>
      {icon}
    </Button>
  );
});
