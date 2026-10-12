"use client";

/**
 * Phase 6.2 — Sign-in page. P3: rebuilt on the design system's fields, button and alert.
 *
 * Posts to /api/v1/auth/login and stores the signed bearer token the backend returns.
 * No user ID is ever typed here: identity comes from credentials, not from a header.
 *
 * The button is never greyed out: a missing entry is explained next to its field when the form
 * is sent, and focus goes to it. While the request runs the fields are read-only (not disabled,
 * so keyboard focus stays where it was) and the button shows that it is busy.
 */

import React, { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { LogIn } from "lucide-react";
import { useSession } from "../../components/auth/SessionProvider";
import { AuthForm, AuthPage } from "../../components/auth/AuthPage";
import { AuthPending } from "../../components/auth/RequireAuth";
import { describeLoginError, resolveRedirectTarget } from "../../components/auth/authMessages";
import { firstInvalid, withoutField, type FieldErrors } from "../../components/auth/formRules";
import { Button } from "../../components/ui/Button/Button";
import { PasswordInput, TextInput } from "../../components/ui/Field/Field";
import { Alert, SkeletonList } from "../../components/ui/State/State";

type LoginField = "email" | "password";
const FIELD_ORDER: readonly LoginField[] = ["email", "password"];
const TITLE = "Sign in";
const DESCRIPTION = "Your recommendations, workspace and applications are tied to your account.";

function LoginForm() {
  const { status, login } = useSession();
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next");
  const target = resolveRedirectTarget(next);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors<LoginField>>({});
  const fields = { email: useRef<HTMLInputElement>(null), password: useRef<HTMLInputElement>(null) };

  // Somebody already signed in has no business on this page.
  useEffect(() => {
    if (status === "authenticated") router.replace(target);
  }, [status, target, router]);

  if (status === "authenticated") {
    // Signed in (just now, or already): the form gives way while the page they asked for opens.
    return <AuthPending label="You're signed in. Opening your page…" />;
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (submitting) return;
    const problems: FieldErrors<LoginField> = {};
    if (email.trim() === "") problems.email = "Enter your email address.";
    if (password === "") problems.password = "Enter your password.";
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
      await login({ email: email.trim().toLowerCase(), password });
      router.replace(target);
    } catch (err: unknown) {
      setError(describeLoginError(err));
      setSubmitting(false);
    }
  };

  const clear = (field: LoginField) => setFieldErrors((current) => withoutField(current, field));

  return (
    <AuthPage
      title={TITLE}
      description={DESCRIPTION}
      alternative={
        <>
          New to ResearchConnect AI?{" "}
          <Link href={next ? `/register?next=${encodeURIComponent(next)}` : "/register"}>Create an account</Link>
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
          ref={fields.email}
          id="login-email"
          name="email"
          type="email"
          label="Email"
          autoComplete="email"
          autoCapitalize="none"
          spellCheck={false}
          aria-required="true"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            clear("email");
          }}
          readOnly={submitting}
          error={fieldErrors.email}
        />

        <PasswordInput
          ref={fields.password}
          id="login-password"
          name="password"
          label="Password"
          autoComplete="current-password"
          aria-required="true"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            clear("password");
          }}
          readOnly={submitting}
          error={fieldErrors.password}
        />

        <Button type="submit" variant="primary" fullWidth loading={submitting} leadingIcon={<LogIn size={16} aria-hidden="true" />}>
          Sign in
        </Button>
      </AuthForm>
    </AuthPage>
  );
}

export default function LoginPage() {
  // useSearchParams needs a boundary for this route to prerender. Until the form is ready the
  // card already shows its title, so the form appears beneath it instead of shifting it.
  return (
    <Suspense
      fallback={
        <AuthPage title={TITLE} description={DESCRIPTION}>
          <SkeletonList rows={2} label="Loading the sign-in form…" />
        </AuthPage>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
