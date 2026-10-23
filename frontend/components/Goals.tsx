import { Icon } from "@/components/Icon";
import type { Objective } from "@/lib/planner";

/** The lesson objectives as a checklist that ticks live (icon + text, never color alone). */
export function Goals({ objectives }: { objectives: Objective[] }) {
  return (
    <ul className="goals">
      {objectives.map((objective, index) => (
        <li key={objective.id} className="goal" data-done={objective.done} style={{ "--i": index } as React.CSSProperties}>
          <span className="goal__check">
            <Icon name="check" size={16} />
          </span>
          <span className="goal__text">
            {objective.text}
            <span className="sr-only">{objective.done ? " (done)" : " (to do)"}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
