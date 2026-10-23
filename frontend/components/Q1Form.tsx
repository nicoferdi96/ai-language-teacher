"use client";

import { useActionState } from "react";
import { Icon } from "@/components/Icon";
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
        <span className="choice__icon choice__icon--sun">
          <Icon name="play" size={20} />
        </span>
        <span>
          <span className="choice__name">Yes, let's start</span>
          <span className="choice__sub">Takes about a minute</span>
        </span>
      </button>
      <button type="submit" name="choice" value="no" className="choice choice--row" disabled={pending}>
        <span className="choice__icon">
          <Icon name="moon" size={20} />
        </span>
        <span>
          <span className="choice__name">Not right now</span>
          <span className="choice__sub">I'll save your spot</span>
        </span>
      </button>
    </form>
  );
}
