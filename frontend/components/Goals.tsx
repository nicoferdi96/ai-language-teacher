import { Icon } from "@/components/Icon";
import type { Step } from "@/lib/planner";

/** The lesson steps as a checklist that ticks live (icon + text, never color alone). */
export function Goals({ steps }: { steps: Step[] }) {
  return (
    <ul className="goals">
      {steps.map((step, index) => (
        <li key={step.position} className="goal" data-done={step.done} style={{ "--i": index } as React.CSSProperties}>
          <span className="goal__check">
            <Icon name="check" size={16} />
          </span>
          <span className="goal__text">
            {step.task}
            <span className="sr-only">{step.done ? " (done)" : " (to do)"}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
