"use client";

import { useActionState } from "react";
import { startSession } from "@/lib/actions";

export function EmailForm() {
  const [error, formAction, pending] = useActionState(startSession, null);
  return (
    <form action={formAction} className="wizard__form">
      <input
        type="email"
        name="email"
        required
        placeholder="you@example.com"
        autoComplete="email"
        aria-label="Email address"
        className="wizard__input"
      />
      {error ? (
        <p className="wizard__error" role="alert">
          {error}
        </p>
      ) : null}
      <button type="submit" className="wizard__submit" disabled={pending}>
        {pending ? "One moment..." : "Begin →"}
      </button>
    </form>
  );
}
