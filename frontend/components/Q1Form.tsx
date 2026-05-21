"use client";

import { useActionState } from "react";
import { answerQ1 } from "@/lib/actions";

export function Q1Form() {
  const [state, formAction, pending] = useActionState(answerQ1, null);

  if (state === "declined") {
    return (
      <div className="wizard__gate">
        <p className="wizard__gatetext">
          No rush. Come back whenever you&apos;re ready to begin.
        </p>
        <form action={formAction}>
          <button
            type="submit"
            name="choice"
            value="yes"
            className="wizard__submit"
            disabled={pending}
          >
            Actually, I&apos;m ready &#8594;
          </button>
        </form>
      </div>
    );
  }

  return (
    <form action={formAction} className="wizard__choices">
      <button
        type="submit"
        name="choice"
        value="yes"
        className="wizard__choice"
        disabled={pending}
      >
        Yes
      </button>
      <button
        type="submit"
        name="choice"
        value="no"
        className="wizard__choice"
        disabled={pending}
      >
        No
      </button>
    </form>
  );
}
