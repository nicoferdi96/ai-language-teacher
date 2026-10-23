import type { ReactNode } from "react";

type WizardShellProps = {
  step?: number;
  totalSteps?: number;
  says?: string;
  saysSub?: string;
  question: string;
  intro?: string;
  wide?: boolean;
  meta?: ReactNode;
  children?: ReactNode;
};

/** Brand mark linking home, shared by every screen. */
export function Brand() {
  return (
    <a href="/" className="brand" aria-label="Lumi home">
      <span className="brand__mark" aria-hidden="true" />
      <span className="brand__text">Lumi</span>
    </a>
  );
}

/** Tutor speech bubble next to the small orb. */
export function Speaker({ says, sub }: { says: string; sub?: string }) {
  return (
    <div className="speaker">
      <div className="orb" aria-hidden="true" />
      <p className="speaker__bubble">
        {says}
        {sub ? <small>{sub}</small> : null}
      </p>
    </div>
  );
}

/** Light, friendly frame shared by onboarding steps and simple screens. */
export function WizardShell({
  step,
  totalSteps,
  says,
  saysSub,
  question,
  intro,
  wide,
  meta,
  children,
}: WizardShellProps) {
  const progress = step && totalSteps ? step / totalSteps : null;
  return (
    <main className="shell">
      <header className="topbar">
        <Brand />
        {progress !== null ? (
          <div
            className="progress"
            role="progressbar"
            aria-label="Onboarding progress"
            aria-valuemin={0}
            aria-valuemax={totalSteps}
            aria-valuenow={step}
          >
            <div className="progress__fill" style={{ transform: `scaleX(${progress})` }} />
          </div>
        ) : (
          meta && <div className="topbar__meta">{meta}</div>
        )}
      </header>
      <section className={wide ? "stage stage--wide" : "stage"}>
        {says ? <Speaker says={says} sub={saysSub} /> : null}
        <div>
          <h1>{question}</h1>
          {intro ? <p className="lead" style={{ marginTop: "0.6rem" }}>{intro}</p> : null}
        </div>
        {children}
      </section>
    </main>
  );
}
