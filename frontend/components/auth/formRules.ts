/**
 * P3 — the account forms' own checks, one message per field.
 *
 * They mirror `backend/app/schemas/auth.py` (RegisterRequest, ChangePasswordRequest), so an
 * obvious mistake is explained next to its field before a round trip. The backend still
 * decides: anything these miss comes back as a readable message from `authMessages.ts`.
 */

import { EMAIL_PATTERN, MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH } from "../../types/auth";

/** A message per field that needs attention; a field with no entry is fine. */
export type FieldErrors<Field extends string> = Partial<Record<Field, string>>;

/** The messages without one field's (it is being corrected). */
export function withoutField<Field extends string>(errors: FieldErrors<Field>, field: Field): FieldErrors<Field> {
  if (errors[field] === undefined) return errors;
  const rest = { ...errors };
  delete rest[field];
  return rest;
}

/** The first field, in form order, that has a message (where focus goes after a failed submit). */
export function firstInvalid<Field extends string>(order: readonly Field[], errors: FieldErrors<Field>): Field | null {
  return order.find((field) => errors[field] !== undefined) ?? null;
}

export function emailProblem(email: string): string | null {
  const value = email.trim();
  if (value === "") return "Enter your email address.";
  if (!EMAIL_PATTERN.test(value.toLowerCase())) return "Enter an email address like name@university.edu.";
  return null;
}

/**
 * A new password (registration or a change) against the backend's rules: the minimum length in
 * characters (as Python counts them), no surrounding spaces, and bcrypt's 72-byte limit, which
 * the backend enforces rather than silently truncating.
 */
export function newPasswordProblem(password: string, empty = "Enter a password."): string | null {
  if (password === "") return empty;
  if ([...password].length < MIN_PASSWORD_LENGTH) return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  if (password.trim() !== password) return "Password must not start or end with a space.";
  if (new TextEncoder().encode(password).length > MAX_PASSWORD_BYTES) {
    return `Password must be at most ${MAX_PASSWORD_BYTES} bytes. Accented letters and symbols count as more than one.`;
  }
  return null;
}

/** The repeated password: present and identical. */
export function confirmationProblem(password: string, confirmation: string, mismatch = "The two passwords do not match."): string | null {
  if (confirmation === "") return "Enter the password again.";
  if (confirmation !== password) return mismatch;
  return null;
}
