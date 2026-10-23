"use client";

import { useActionState } from "react";
import { FormError } from "@/components/FormError";
import { startSession } from "@/lib/actions";

export function EmailForm() {
  const [error, formAction, pending] = useActionState(startSession, null);
  return (
    <form action={formAction} className="form">
      <label className="label" htmlFor="email">
        Your email
      </label>
      <input
        id="email"
        type="email"
        name="email"
        required
        placeholder="you@example.com"
        autoComplete="email"
        aria-invalid={error ? "true" : undefined}
        aria-describedby={error ? "email-error" : undefined}
        className="field"
      />
      <FormError id="email-error" message={error} />
      <button type="submit" className="btn btn--block" disabled={pending}>
        {pending ? "One moment…" : "Let's go"}
      </button>
      <p className="hint">Coming back? Use the same email and we'll pick up where you left off.</p>
    </form>
  );
}
