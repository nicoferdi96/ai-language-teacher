"use client";

import { useActionState } from "react";
import { saveLearningGoal } from "@/lib/actions";

export function Q2Form() {
  const [error, formAction, pending] = useActionState(saveLearningGoal, null);
  return (
    <form action={formAction} className="wizard__form">
      <textarea
        name="answer"
        required
        rows={4}
        placeholder="Tell me how you'd like to learn..."
        aria-label="How you would like to learn Spanish"
        aria-invalid={error ? "true" : undefined}
        aria-describedby={error ? "q2-error" : undefined}
        className="wizard__input wizard__input--area"
      />
      {error ? (
        <p id="q2-error" className="wizard__error" role="alert">
          {error}
        </p>
      ) : null}
      <button type="submit" className="wizard__submit" disabled={pending}>
        {pending ? "Saving..." : "Continue →"}
      </button>
    </form>
  );
}
