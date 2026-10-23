import type { CSSProperties } from "react";
import { WizardShell } from "@/components/WizardShell";

/** Stages narrated while the lesson-planning microservice runs (~30s). */
const STAGES = [
  "Reading how you like to learn",
  "Choosing today's focus",
  "Writing your lesson",
  "Setting the pace",
] as const;

/** Seconds each narrated stage holds before the next one takes over. */
const STAGE_WINDOW_S = 7.5;

/**
 * Suspense fallback for /wizard/preparing. While the page's server component
 * awaits the lesson-planning microservice, this renders a calm, narrated
 * progress view: stages settle one by one as a slow hairline advances. Pure
 * CSS, no client JS. prefers-reduced-motion is honored by the global rule in
 * globals.css, which freezes every stage on its resolved frame.
 */
export default function PreparingLoading() {
  return (
    <WizardShell
      eyebrow="On it"
      question="I'm putting your first lesson together."
      intro="This takes about half a minute. Stay here, or step away and stretch. Your lesson will be waiting when it's ready."
    >
      <ol className="prepare" aria-label="Building your lesson">
        {STAGES.map((stage, index) => {
          const isFinal = index === STAGES.length - 1;
          return (
            <li
              key={stage}
              className="prepare__stage"
              data-final={isFinal ? "" : undefined}
              style={{ "--at": `${index * STAGE_WINDOW_S}s` } as CSSProperties}
            >
              <span className="prepare__marker" aria-hidden="true">
                <svg
                  className="prepare__check"
                  viewBox="0 0 12 12"
                  aria-hidden="true"
                >
                  <path d="M2.5 6.5 L5 9 L9.5 3.5" />
                </svg>
              </span>
              <span className="prepare__label">{stage}</span>
            </li>
          );
        })}
      </ol>
      <div className="prepare__track" aria-hidden="true">
        <span className="prepare__fill" />
      </div>
    </WizardShell>
  );
}
