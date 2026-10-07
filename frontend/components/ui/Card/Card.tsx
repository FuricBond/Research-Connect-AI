import type { ElementType, HTMLAttributes, ReactNode } from "react";
import { cx } from "../../../utils/cx";
import styles from "./Card.module.css";

interface CardProps extends HTMLAttributes<HTMLElement> {
  /** default: bordered surface · muted: sunken, for secondary information ·
   *  interactive: the whole card is one link (put the link on the title). */
  variant?: "default" | "muted" | "interactive";
  padding?: "default" | "compact" | "flush";
  as?: ElementType;
}

/** One object, one card. No nested cards and no shadows. DESIGN_SYSTEM.md §8.3. */
export function Card({ variant = "default", padding = "default", as: Tag = "div", className, ...rest }: CardProps) {
  return (
    <Tag
      className={cx(
        styles.card,
        variant === "muted" && styles.muted,
        variant === "interactive" && styles.interactive,
        padding === "compact" && styles.compact,
        padding === "flush" && styles.flush,
        className
      )}
      {...rest}
    />
  );
}

/** A card's title row: title on the left, a status or action slot on the right. */
export function CardHeader({ title, titleAs: Title = "h3", aside, className }: { title: ReactNode; titleAs?: ElementType; aside?: ReactNode; className?: string }) {
  return (
    <div className={cx(styles.header, className)}>
      <Title className={styles.title}>{title}</Title>
      {aside}
    </div>
  );
}

/** A ruled footer for the card's actions (one primary at most). */
export function CardFooter({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx(styles.footer, className)} {...rest} />;
}
