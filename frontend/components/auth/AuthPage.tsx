import type { ComponentProps, ReactNode } from "react";
import { cx } from "../../utils/cx";
import { Card } from "../ui/Card/Card";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import styles from "./AuthPage.module.css";

/**
 * P3 — the frame of the sign-in and registration pages: one flat card holding the page's title
 * (its one h1) and purpose, the form, and the way to the other form. Full width on phones.
 */
export function AuthPage({
  title,
  description,
  wide,
  alternative,
  children,
}: {
  title: ReactNode;
  description: ReactNode;
  /** The registration form: room for two fields side by side. */
  wide?: boolean;
  /** One line under the form, linking to the other form. */
  alternative?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={styles.page}>
      <Card className={cx(styles.card, wide && styles.wide)}>
        <PageHeader className={styles.header} title={title} description={description} />
        {children}
        {alternative && <p className={styles.alternative}>{alternative}</p>}
      </Card>
    </div>
  );
}

/** The form's layout: fields stacked with the design system's field gap. */
export function AuthForm({ className, ...rest }: ComponentProps<"form">) {
  return <form className={cx(styles.form, className)} noValidate {...rest} />;
}

/** Two fields side by side where the card is wide enough; stacked otherwise. */
export function AuthFieldPair({ children }: { children: ReactNode }) {
  return <div className={styles.pair}>{children}</div>;
}
