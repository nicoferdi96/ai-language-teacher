import type { ReactNode } from "react";

type WizardShellProps = {
  step?: number;
  totalSteps?: number;
  eyebrow?: string;
  intro?: string;
  question: string;
  children?: ReactNode;
};

/** Editorial dark frame shared by every wizard screen. */
export function WizardShell({
  step,
  totalSteps,
  eyebrow,
  intro,
  question,
  children,
}: WizardShellProps) {
  return (
    <main className="wizard">
      <header className="wizard__bar">
        <span className="wizard__brand">AI LANGUAGE TEACHER</span>
        {step && totalSteps ? (
          <span className="wizard__counter">
            {String(step).padStart(2, "0")} /{" "}
            {String(totalSteps).padStart(2, "0")}
          </span>
        ) : null}
      </header>
      <section className="wizard__body">
        {eyebrow ? <p className="wizard__eyebrow">{eyebrow}</p> : null}
        <h1 className="wizard__question">{question}</h1>
        {intro ? <p className="wizard__intro">{intro}</p> : null}
        {children}
      </section>
    </main>
  );
}
