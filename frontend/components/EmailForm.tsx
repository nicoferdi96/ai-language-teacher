"use client";

import { useActionState } from "react";
import { FormError } from "@/components/FormError";
import { Icon } from "@/components/Icon";
import { startSession } from "@/lib/actions";

export function EmailForm() {
  const [error, formAction, pending] = useActionState(startSession, null);
  return (
    <form action={formAction} className="form">
      <div className="field-group">
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
          aria-describedby={error ? "email-error" : "email-hint"}
          className="field"
        />
      </div>
      <FormError id="email-error" message={error} />
      <button type="submit" className="btn btn--block btn--lg" disabled={pending}>
        {pending ? "One moment…" : "Get started"}
        {pending ? null : <Icon name="arrow" size={20} className="btn__arrow" />}
      </button>
      <p id="email-hint" className="hint">
        Coming back? Use the same email and we'll pick up where you left off.
      </p>
    </form>
  );
}
