"use client";

import { useEffect } from "react";
import { WizardShell } from "@/components/WizardShell";

export default function Error({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <WizardShell
      says="Sorry about that."
      mood="thinking"
      question="Something went wrong."
      intro="I couldn't reach the server. Your progress is safe."
    >
      <button type="button" className="btn" onClick={reset}>
        Try again
      </button>
    </WizardShell>
  );
}
