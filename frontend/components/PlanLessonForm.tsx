"use client";

import { useActionState } from "react";
import { planNextLesson } from "@/lib/actions";

/** Returning-user button that kicks off the lesson-planning microservice. */
export function PlanLessonForm() {
  const [error, formAction, pending] = useActionState(planNextLesson, null);
  return (
    <form action={formAction} className="wizard__form">
      <button type="submit" className="wizard__submit" disabled={pending}>
        {pending ? "Setting things up..." : "Plan my next lesson →"}
      </button>
      {error ? (
        <p className="wizard__error" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
