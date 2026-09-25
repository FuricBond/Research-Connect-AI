"use client";

/**
 * Phase 6.2 — Registration page.
 *
 * Posts to /api/v1/auth/register, which creates the account *and* its researcher profile
 * in one transaction and returns a token — so a new account is signed in immediately and
 * needs no separate sign-in step.
 *
 * Only the roles the backend accepts from a self-registering person are offered. ADMIN is
 * granted by an existing administrator and is deliberately not selectable here.
 */

import React, { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, Loader2, UserPlus } from "lucide-react";
import type { SelfServiceRole } from "../../types/auth";
import { EMAIL_PATTERN, MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH } from "../../types/auth";
import { useSession } from "../../components/auth/SessionProvider";
import { describeRegisterError, resolveRedirectTarget } from "../../components/auth/authMessages";

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

/** Mirrors the backend's own checks so obvious mistakes never cost a round trip. */
function validate(fields: {
  fullName: string;
  email: string;
  password: string;
  confirmPassword: string;
}): string | null {
  if (fields.fullName.trim() === "") return "Please enter your full name.";
  if (!EMAIL_PATTERN.test(fields.email.trim().toLowerCase())) {
    return "Please enter a valid email address.";
  }
  if (fields.password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (fields.password.trim() !== fields.password) {
    return "Password must not start or end with a space.";
  }
  // bcrypt reads only the first 72 bytes, so the backend rejects anything longer
  // outright rather than silently truncating it.
  if (new TextEncoder().encode(fields.password).length > MAX_PASSWORD_BYTES) {
    return `Password must be at most ${MAX_PASSWORD_BYTES} bytes.`;
  }
  if (fields.password !== fields.confirmPassword) return "The two passwords do not match.";
  return null;
}

function RegisterForm() {
  const { status, register } = useSession();
  const router = useRouter();
  const searchParams = useSearchParams();
  const target = resolveRedirectTarget(searchParams.get("next"));

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [role, setRole] = useState<SelfServiceRole>("STUDENT");
  const [institution, setInstitution] = useState("");
  const [department, setDepartment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === "authenticated") router.replace(target);
  }, [status, target, router]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (submitting) return;

    const complaint = validate({ fullName, email, password, confirmPassword });
    if (complaint !== null) {
      setError(complaint);
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      await register({
        full_name: fullName.trim(),
        email: email.trim().toLowerCase(),
        password,
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

  const selectedRole = ROLE_CHOICES.find((choice) => choice.value === role);

  return (
    <div className="auth-page">
      <div className="auth-card auth-card-wide">
        <header className="auth-card-head">
          <h1>Create an account</h1>
          <p className="auth-card-subtitle">
            This also creates your researcher profile, so recommendations can start from
            your stated interests.
          </p>
        </header>

        {error !== null && (
          <div className="auth-error" role="alert">
            <AlertCircle size={15} aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="auth-field">
            <label htmlFor="register-name">Full name</label>
            <input
              id="register-name"
              name="full_name"
              type="text"
              autoComplete="name"
              required
              maxLength={255}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              disabled={submitting}
            />
          </div>

          <div className="auth-field">
            <label htmlFor="register-email">Email</label>
            <input
              id="register-email"
              name="email"
              type="email"
              autoComplete="email"
              required
              maxLength={255}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={submitting}
            />
          </div>

          <div className="auth-form-grid">
            <div className="auth-field">
              <label htmlFor="register-password">
                Password
                <span className="auth-field-hint">At least {MIN_PASSWORD_LENGTH} characters</span>
              </label>
              <input
                id="register-password"
                name="password"
                type="password"
                autoComplete="new-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={submitting}
              />
            </div>

            <div className="auth-field">
              <label htmlFor="register-confirm">Confirm password</label>
              <input
                id="register-confirm"
                name="confirm_password"
                type="password"
                autoComplete="new-password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                disabled={submitting}
              />
            </div>
          </div>

          <div className="auth-field">
            <label htmlFor="register-role">I am a</label>
            <select
              id="register-role"
              name="role"
              value={role}
              onChange={(e) => setRole(e.target.value as SelfServiceRole)}
              disabled={submitting}
            >
              {ROLE_CHOICES.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </select>
            {selectedRole !== undefined && (
              <span className="auth-field-hint">{selectedRole.hint}</span>
            )}
          </div>

          <div className="auth-form-grid">
            <div className="auth-field">
              <label htmlFor="register-institution">
                Institution
                <span className="auth-field-hint">Optional</span>
              </label>
              <input
                id="register-institution"
                name="institution_name"
                type="text"
                autoComplete="organization"
                maxLength={255}
                value={institution}
                onChange={(e) => setInstitution(e.target.value)}
                disabled={submitting}
              />
            </div>

            <div className="auth-field">
              <label htmlFor="register-department">
                Department
                <span className="auth-field-hint">Optional</span>
              </label>
              <input
                id="register-department"
                name="department"
                type="text"
                maxLength={255}
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                disabled={submitting}
              />
            </div>
          </div>

          <button type="submit" className="auth-submit" disabled={submitting}>
            {submitting ? (
              <>
                <Loader2 size={15} className="auth-spinner" aria-hidden="true" />
                Creating account…
              </>
            ) : (
              <>
                <UserPlus size={15} aria-hidden="true" />
                Create account
              </>
            )}
          </button>
        </form>

        <p className="auth-alt">
          Already registered? <Link href="/login" className="auth-link">Sign in</Link>
        </p>
      </div>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={<div className="auth-page" />}>
      <RegisterForm />
    </Suspense>
  );
}
