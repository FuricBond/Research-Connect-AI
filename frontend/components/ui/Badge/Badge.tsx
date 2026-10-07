import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "../../../utils/cx";
import { priorityMeta, type StatusMeta, type StatusTone } from "../../../utils/status";
import styles from "./Badge.module.css";

const TONE_CLASS: Record<StatusTone, string> = {
  neutral: styles.neutral,
  brand: styles.brand,
  "brand-strong": styles.brandStrong,
  info: styles.info,
  success: styles.success,
  warning: styles.warning,
  danger: styles.danger,
  muted: styles.muted,
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: StatusTone;
  icon?: ReactNode;
}

/** A short status word in sentence case, with an optional icon. DESIGN_SYSTEM.md §8.4. */
export function Badge({ tone = "neutral", icon, className, children, ...rest }: BadgeProps) {
  return (
    <span className={cx(styles.badge, TONE_CLASS[tone], className)} {...rest}>
      {icon}
      {children}
    </span>
  );
}

/** A Badge from a domain status map (utils/status.ts): never shows the raw enum. */
export function StatusBadge({ meta, className }: { meta: StatusMeta; className?: string }) {
  const Icon = meta.icon;
  return (
    <Badge tone={meta.tone} icon={Icon ? <Icon size={12} aria-hidden="true" /> : undefined} className={className}>
      {meta.label}
    </Badge>
  );
}

/** Priority as a word with a 1–4 level glyph; deliberately not colour-coded. */
export function PriorityLabel({ priority, className }: { priority: string | null | undefined; className?: string }) {
  const { label, level } = priorityMeta(priority);
  return (
    <span className={cx(styles.priority, className)}>
      <span className={styles.bars} aria-hidden="true">
        {[1, 2, 3, 4].map((n) => (
          <span key={n} className={cx(styles.bar, n <= level && styles.barOn)} />
        ))}
      </span>
      {label} priority
    </span>
  );
}
