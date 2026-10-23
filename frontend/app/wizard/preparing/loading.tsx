import type { CSSProperties } from "react";
import { Icon } from "@/components/Icon";
import { WizardShell } from "@/components/WizardShell";

/** Stages narrated while the planner reviews progress and writes the lesson. */
const STAGES = [
  "Checking where we left off",
  "Picking the next step in your plan",
  "Writing today's ten minutes",
] as const;

/**
 * Suspense fallback for /wizard/preparing: each stage appears in turn and
 * settles with a check. Pure CSS; reduced motion shows every stage at once.
 */
export default function PreparingLoading() {
  return (
    <WizardShell
      says="Give me a few seconds."
      mood="thinking"
      question="Getting your lesson ready…"
      intro="I'm looking at your plan and what you practised last time."
    >
      <ol className="prepare" aria-label="Preparing your lesson">
        {STAGES.map((stage, index) => (
          <li key={stage} className="prepare__stage" style={{ "--at": `${index * 4}s` } as CSSProperties}>
            <span className="prepare__marker" aria-hidden="true">
              <Icon name="check" size={16} />
            </span>
            {stage}
          </li>
        ))}
      </ol>
    </WizardShell>
  );
}
