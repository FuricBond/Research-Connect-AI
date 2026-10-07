import type { ReactNode } from "react";
import { cx } from "../../../utils/cx";
import styles from "./PageHeader.module.css";

interface PageHeaderProps {
  /** The page's one h1, in serif. */
  title: ReactNode;
  /** One sentence on what the page is for (max two lines); no implementation details. */
  description?: ReactNode;
  /** A short label above the title, sentence case (not all caps). */
  eyebrow?: ReactNode;
  /** At most one primary action, plus secondary ones. They wrap under the title on phones. */
  actions?: ReactNode;
  /** The larger display size: the signed-in home greeting only. */
  display?: boolean;
  className?: string;
}

/** One per page. DESIGN_SYSTEM.md §8.3. */
export function PageHeader({ title, description, eyebrow, actions, display, className }: PageHeaderProps) {
  return (
    <header className={cx(styles.page, className)}>
      <div className={styles.titles}>
        {eyebrow && <span className={styles.eyebrow}>{eyebrow}</span>}
        <h1 className={cx(styles.title, display && styles.display)}>{title}</h1>
        {description && <p className={styles.description}>{description}</p>}
      </div>
      {actions && <div className={styles.actions}>{actions}</div>}
    </header>
  );
}

interface SectionHeaderProps {
  title: ReactNode;
  id?: string;
  description?: ReactNode;
  /** A link or ghost action aligned right. */
  action?: ReactNode;
  as?: "h2" | "h3";
  className?: string;
}

/** A section's h2 with an optional description and a right-aligned link or ghost action. */
export function SectionHeader({ title, id, description, action, as: Heading = "h2", className }: SectionHeaderProps) {
  return (
    <div className={cx(styles.section, className)}>
      <Heading id={id} className={styles.sectionTitle}>
        {title}
      </Heading>
      {action}
      {description && <p className={styles.sectionDescription}>{description}</p>}
    </div>
  );
}
