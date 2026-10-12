"use client";

/**
 * Phase 6.2 — Registration page. P3: rebuilt on the design system's fields, button and alert.
 *
 * Posts to /api/v1/auth/register, which creates the account *and* its researcher profile
 * in one transaction and returns a token — so a new account is signed in immediately and
 * needs no separate sign-in step.
 *
 * Only the roles the backend accepts from a self-registering person are offered. ADMIN is
 * granted by an existing administrator and is deliberately not selectable here.
 *
 * Each field's problem is explained next to it when the form is sent (the backend's own rules,
 * `formRules.ts`), and focus goes to the first one; what only the server can tell (an email
 * already in use, too many attempts) appears above the form.
 */

import React, { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { UserPlus } from "lucide-react";
import type { SelfServiceRole } from "../../types/auth";
import { MIN_PASSWORD_LENGTH } from "../../types/auth";
import { useSession } from "../../components/auth/SessionProvider";
import { AuthFieldPair, AuthForm, AuthPage } from "../../components/auth/AuthPage";
import { AuthPending } from "../../components/auth/RequireAuth";
import { describeRegisterError, resolveRedirectTarget } from "../../components/auth/authMessages";
import {
  confirmationProblem,
  emailProblem,
  firstInvalid,
  newPasswordProblem,
  withoutField,
  type FieldErrors,
} from "../../components/auth/formRules";
import { Button } from "../../components/ui/Button/Button";
import { PasswordInput, Select, TextInput } from "../../components/ui/Field/Field";
import { Alert, SkeletonList } from "../../components/ui/State/State";

const ROLE_CHOICES: { value: SelfServiceRole; label: string; hint: string }[] = [
  {
    value: "STUDENT",
    label: "Student researcher",
    hint: "Discover opportunities, apply to postings and find collaborators.",
  },
  {
    value: "FACULTY",
    label: "Faculty",
    hint: "Everything above, plus authoring research postings and reviewing applications.",
  },
];

type RegisterField = "fullName" | "email" | "password" | "confirmPassword";
const FIELD_ORDER: readonly RegisterField[] = ["fullName", "email", "password", "confirmPassword"];
const TITLE = "Create an account";
const DESCRIPTION = "This also creates your researcher profile, so recommendations can start from your stated interests.";

/** Mirrors the backend's own checks so obvious mistakes never cost a round trip. */
function validate(fields: Record<RegisterField, string>): FieldErrors<RegisterField> {
  const problems: FieldErrors<RegisterField> = {};
  if (fields.fullName.trim() === "") problems.fullName = "Enter your full name.";
  const email = emailProblem(fields.email);
  if (email) problems.email = email;
  const password = newPasswordProblem(fields.password);
  if (password) problems.password = password;
  const confirmation = confirmationProblem(fields.password, fields.confirmPassword);
  if (confirmation) problems.confirmPassword = confirmation;
  return problems;
}

function RegisterForm() {
  const { status, register } = useSession();
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next");
  const target = resolveRedirectTarget(next);

  const [values, setValues] = useState<Record<RegisterField, string>>({ fullName: "", email: "", password: "", confirmPassword: "" });
  const [role, setRole] = useState<SelfServiceRole>("STUDENT");
  const [institution, setInstitution] = useState("");
  const [department, setDepartment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors<RegisterField>>({});
  const fields = {
    fullName: useRef<HTMLInputElement>(null),
    email: useRef<HTMLInputElement>(null),
    password: useRef<HTMLInputElement>(null),
    confirmPassword: useRef<HTMLInputElement>(null),
  };

  useEffect(() => {
    if (status === "authenticated") router.replace(target);
  }, [status, target, router]);

  if (status === "authenticated") {
    return <AuthPending label="You're signed in. Opening your page…" />;
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (submitting) return;

    const problems = validate(values);
    setFieldErrors(problems);
    const invalid = firstInvalid(FIELD_ORDER, problems);
    if (invalid !== null) {
      setError(null);
      fields[invalid].current?.focus();
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      await register({
        full_name: values.fullName.trim(),
        email: values.email.trim().toLowerCase(),
        password: values.password,
        role,
        institution_name: institution.trim() || undefined,
        department: department.trim() || undefined,
      });
      router.replace(target);
    } catch (err: unknown) {
      setError(describeRegisterError(err));
      setSubmitting(false);
    }
  };

  /** A field's change handler: the new value, and its message goes while it is corrected. */
  const edit = (field: RegisterField) => (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setValues((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => withoutField(current, field));
  };

  const selectedRole = ROLE_CHOICES.find((choice) => choice.value === role);

  return (
    <AuthPage
      wide
      title={TITLE}
      description={DESCRIPTION}
      alternative={
        <>
          Already have an account? <Link href={next ? `/login?next=${encodeURIComponent(next)}` : "/login"}>Sign in</Link>
        </>
      }
    >
      {error !== null && (
        <Alert tone="danger" announce>
          {error}
        </Alert>
      )}

      <AuthForm onSubmit={handleSubmit}>
        <TextInput
          ref={fields.fullName}
          id="register-name"
          name="full_name"
          label="Full name"
          autoComplete="name"
          aria-required="true"
          maxLength={255}
          value={values.fullName}
          onChange={edit("fullName")}
          readOnly={submitting}
          error={fieldErrors.fullName}
        />

        <TextInput
          ref={fields.email}
          id="register-email"
          name="email"
          type="email"
          label="Email"
          hint="You sign in with this address."
          autoComplete="email"
          autoCapitalize="none"
          spellCheck={false}
          aria-required="true"
          maxLength={255}
          value={values.email}
          onChange={edit("email")}
          readOnly={submitting}
          error={fieldErrors.email}
        />

        <AuthFieldPair>
          <PasswordInput
            ref={fields.password}
            id="register-password"
            name="password"
            label="Password"
            hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
            autoComplete="new-password"
            aria-required="true"
            value={values.password}
            onChange={edit("password")}
            readOnly={submitting}
            error={fieldErrors.password}
          />

          <PasswordInput
            ref={fields.confirmPassword}
            id="register-confirm"
            name="confirm_password"
            label="Confirm password"
            revealLabel="Show password confirmation"
            autoComplete="new-password"
            aria-required="true"
            value={values.confirmPassword}
            onChange={edit("confirmPassword")}
            readOnly={submitting}
            error={fieldErrors.confirmPassword}
          />
        </AuthFieldPair>

        <Select
          id="register-role"
          name="role"
          label="Account type"
          hint={selectedRole?.hint}
          value={role}
          // Kept enabled while the form is sent (a disabled control would drop keyboard focus);
          // the choice simply cannot change then.
          onChange={(e) => {
            if (!submitting) setRole(e.target.value as SelfServiceRole);
          }}
        >
          {ROLE_CHOICES.map((choice) => (
            <option key={choice.value} value={choice.value}>
              {choice.label}
            </option>
          ))}
        </Select>

        <AuthFieldPair>
          <TextInput
            id="register-institution"
            name="institution_name"
            label="Institution (optional)"
            autoComplete="organization"
            maxLength={255}
            value={institution}
            onChange={(e) => setInstitution(e.target.value)}
            readOnly={submitting}
          />

          <TextInput
            id="register-department"
            name="department"
            label="Department (optional)"
            maxLength={255}
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
            readOnly={submitting}
          />
        </AuthFieldPair>

        <Button type="submit" variant="primary" fullWidth loading={submitting} leadingIcon={<UserPlus size={16} aria-hidden="true" />}>
          Create account
        </Button>
      </AuthForm>
    </AuthPage>
  );
}

export default function RegisterPage() {
  return (
    <Suspense
      fallback={
        <AuthPage wide title={TITLE} description={DESCRIPTION}>
          <SkeletonList rows={3} label="Loading the registration form…" />
        </AuthPage>
      }
    >
      <RegisterForm />
    </Suspense>
  );
}
