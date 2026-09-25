"use client";

/**
 * Phase 6.2 — Sign-in page.
 *
 * Posts to /api/v1/auth/login and stores the signed bearer token the backend returns.
 * No user ID is ever typed here: identity comes from credentials, not from a header.
 */

import React, { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, Loader2, LogIn } from "lucide-react";
import { useSession } from "../../components/auth/SessionProvider";
import { describeLoginError, resolveRedirectTarget } from "../../components/auth/authMessages";

function LoginForm() {
  const { status, login } = useSession();
  const router = useRouter();
  const searchParams = useSearchParams();
  const target = resolveRedirectTarget(searchParams.get("next"));

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Somebody already signed in has no business on this page.
  useEffect(() => {
    if (status === "authenticated") router.replace(target);
  }, [status, target, router]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (submitting) return;
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

  return (
    <div className="auth-page">
      <div className="auth-card">
        <header className="auth-card-head">
          <h1>Sign in</h1>
          <p className="auth-card-subtitle">
            Your recommendations, workspace and applications are tied to your account.
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
            <label htmlFor="login-email">Email</label>
            <input
              id="login-email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={submitting}
            />
          </div>

          <div className="auth-field">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
            />
          </div>

          <button
            type="submit"
            className="auth-submit"
            disabled={submitting || email.trim() === "" || password === ""}
          >
            {submitting ? (
              <>
                <Loader2 size={15} className="auth-spinner" aria-hidden="true" />
                Signing in…
              </>
            ) : (
              <>
                <LogIn size={15} aria-hidden="true" />
                Sign in
              </>
            )}
          </button>
        </form>

        <p className="auth-alt">
          No account yet? <Link href="/register" className="auth-link">Create one</Link>
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  // useSearchParams needs a boundary for this route to prerender.
  return (
    <Suspense fallback={<div className="auth-page" />}>
      <LoginForm />
    </Suspense>
  );
}
