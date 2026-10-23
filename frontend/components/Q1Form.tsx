"use client";

import { useActionState } from "react";
import { answerQ1 } from "@/lib/actions";

export function Q1Form() {
  const [state, formAction, pending] = useActionState(answerQ1, null);

  if (state === "declined") {
    return (
      <form action={formAction} className="form">
        <p className="note">
          <strong>No rush.</strong> Your spot is saved. Come back whenever you have ten minutes.
        </p>
        <button type="submit" name="choice" value="yes" className="btn" disabled={pending}>
          Actually, I'm ready
        </button>
      </form>
    );
  }

  return (
    <form action={formAction} className="choices">
      <button type="submit" name="choice" value="yes" className="choice choice--row" disabled={pending}>
        Yes, let's start
      </button>
      <button type="submit" name="choice" value="no" className="choice choice--row" disabled={pending}>
        Not right now
      </button>
    </form>
  );
}
