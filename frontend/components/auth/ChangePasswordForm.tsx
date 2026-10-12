"use client";

/**
 * Phase 6.7 (Fix 5/9) — changing the password. P3: moved from the notification settings to the
 * Account section of Settings, and rebuilt on the design system's fields.
 *
 * Changing the password revokes every token the account holds, this browser's included, and the
 * backend answers with a fresh one, which this browser keeps: it stays signed in while every
 * other device is signed out. Each field's problem is explained next to it (the registration
 * rules, `formRules.ts`); the backend's answer (a wrong current password) appears above the form.
 */

import React, { useRef, useState } from "react";
import { KeyRound } from "lucide-react";
import { changePassword } from "../../services/api";
import { storeSession } from "../../services/auth";
import { MIN_PASSWORD_LENGTH } from "../../types/auth";
import { Button } from "../ui/Button/Button";
import { PasswordInput } from "../ui/Field/Field";
import { Alert } from "../ui/State/State";
import { describeChangePasswordError } from "./authMessages";
import { confirmationProblem, firstInvalid, newPasswordProblem, withoutField, type FieldErrors } from "./formRules";
import styles from "./ChangePasswordForm.module.css";

type PasswordField = "current" | "next" | "confirm";
const FIELD_ORDER: readonly PasswordField[] = ["current", "next", "confirm"];
const EMPTY: Record<PasswordField, string> = { current: "", next: "", confirm: "" };

export function ChangePasswordForm() {
  const [values, setValues] = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [changed, setChanged] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors<PasswordField>>({});
  const fields = { current: useRef<HTMLInputElement>(null), next: useRef<HTMLInputElement>(null), confirm: useRef<HTMLInputElement>(null) };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (submitting) return;
    setError(null);
    setChanged(false);

    const problems: FieldErrors<PasswordField> = {};
    if (values.current === "") problems.current = "Enter your current password.";
    const next = newPasswordProblem(values.next, "Enter a new password.");
    if (next) problems.next = next;
    const confirm = confirmationProblem(values.next, values.confirm, "The new passwords do not match.");
    if (confirm) problems.confirm = confirm;
    setFieldErrors(problems);
    const invalid = firstInvalid(FIELD_ORDER, problems);
    if (invalid !== null) {
      fields[invalid].current?.focus();
      return;
    }

    setSubmitting(true);
    try {
      const response = await changePassword({ current_password: values.current, new_password: values.next });
      storeSession(response);
      setValues(EMPTY);
      setChanged(true);
    } catch (err: unknown) {
      setError(describeChangePasswordError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const edit = (field: PasswordField) => (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setValues((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => withoutField(current, field));
  };

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate aria-labelledby="change-password-title">
      <h3 id="change-password-title" className={styles.title}>
        Change password
      </h3>
      <p className={styles.description}>Changing your password signs you out on every other device. This browser stays signed in.</p>

      {error !== null && (
        <Alert tone="danger" announce>
          {error}
        </Alert>
      )}
      {/* Present before it has anything to say, so the confirmation is announced when it appears. */}
      <div role="status" className={styles.status}>
        {changed && <Alert tone="success">Password changed. Your other sessions have been signed out.</Alert>}
      </div>

      <PasswordInput
        ref={fields.current}
        id="current-password"
        name="current_password"
        label="Current password"
        revealLabel="Show current password"
        autoComplete="current-password"
        aria-required="true"
        value={values.current}
        onChange={edit("current")}
        readOnly={submitting}
        error={fieldErrors.current}
      />
      <PasswordInput
        ref={fields.next}
        id="new-password"
        name="new_password"
        label="New password"
        hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
        revealLabel="Show new password"
        autoComplete="new-password"
        aria-required="true"
        value={values.next}
        onChange={edit("next")}
        readOnly={submitting}
        error={fieldErrors.next}
      />
      <PasswordInput
        ref={fields.confirm}
        id="confirm-password"
        name="confirm_password"
        label="Confirm new password"
        revealLabel="Show new password confirmation"
        autoComplete="new-password"
        aria-required="true"
        value={values.confirm}
        onChange={edit("confirm")}
        readOnly={submitting}
        error={fieldErrors.confirm}
      />

      <div>
        <Button type="submit" variant="primary" loading={submitting} leadingIcon={<KeyRound size={16} aria-hidden="true" />}>
          Change password
        </Button>
      </div>
    </form>
  );
}
