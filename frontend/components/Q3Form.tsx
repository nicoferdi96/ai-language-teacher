"use client";

import { useActionState } from "react";
import { saveLessonDuration } from "@/lib/actions";

export function Q3Form() {
  const [error, formAction, pending] = useActionState(saveLessonDuration, null);
  return (
    <form action={formAction} className="wizard__form">
      <div className="wizard__minutes">
        <input
          type="number"
          name="answer"
          required
          min={1}
          step={1}
          placeholder="30"
          aria-label="Ideal lesson duration in minutes"
          className="wizard__input wizard__input--number"
        />
        <span className="wizard__unit">minutes</span>
      </div>
      {error ? (
        <p className="wizard__error" role="alert">
          {error}
        </p>
      ) : null}
      <button type="submit" className="wizard__submit" disabled={pending}>
        {pending ? "Saving..." : "Finish →"}
      </button>
    </form>
  );
}
