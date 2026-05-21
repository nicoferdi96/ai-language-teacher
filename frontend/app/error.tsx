"use client";

import { useEffect } from "react";

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
    <main className="wizard">
      <section className="wizard__body">
        <h1 className="wizard__question">Something went wrong.</h1>
        <p className="wizard__intro">
          We couldn&apos;t reach the server. Please try again.
        </p>
        <button
          type="button"
          className="wizard__submit"
          style={{ marginTop: "1.5rem" }}
          onClick={reset}
        >
          Retry
        </button>
      </section>
    </main>
  );
}
