import type { Objective } from "@/lib/planner";

/** Check icon used for completed objectives (paired with text, never color alone). */
function Check() {
  return (
    <svg viewBox="0 0 12 12" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.5 6.5 L5 9 L9.5 3.5" />
    </svg>
  );
}

/** The lesson objectives as a checklist that ticks live. */
export function Goals({ objectives }: { objectives: Objective[] }) {
  return (
    <ul className="goals">
      {objectives.map((objective) => (
        <li key={objective.id} className="goal" data-done={objective.done}>
          <span className="goal__check">
            <Check />
          </span>
          <span className="goal__text">
            {objective.text}
            <span className="goal__state">{objective.done ? " (done)" : " (to do)"}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
