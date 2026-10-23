import type { CSSProperties, ReactNode } from "react";
import { Icon } from "@/components/Icon";
import { Lumi, type LumiState } from "@/components/Lumi";

type WizardShellProps = {
  step?: number;
  totalSteps?: number;
  back?: string;
  says?: string;
  saysSub?: string;
  mood?: LumiState;
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

/** Tutor speech bubble next to Lumi. */
export function Speaker({ says, sub, mood = "idle" }: { says: string; sub?: string; mood?: LumiState }) {
  return (
    <div className="speaker">
      <Lumi state={mood} size="md" />
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
  back,
  says,
  saysSub,
  mood,
  question,
  intro,
  wide,
  meta,
  children,
}: WizardShellProps) {
  const progress = step && totalSteps ? step / totalSteps : null;
  const previous = step && totalSteps ? (step - 1) / totalSteps : 0;
  return (
    <main className="shell">
      <header className="topbar">
        {back ? (
          <a href={back} className="back" aria-label="Back to the previous question">
            <Icon name="back" size={26} />
          </a>
        ) : (
          <Brand />
        )}
        {progress !== null ? (
          <div
            className="progress"
            role="progressbar"
            aria-label="Onboarding progress"
            aria-valuemin={0}
            aria-valuemax={totalSteps}
            aria-valuenow={step}
          >
            <div
              className="progress__fill"
              style={{ "--from": previous, "--to": progress } as CSSProperties}
            />
          </div>
        ) : (
          meta && <div className="topbar__meta">{meta}</div>
        )}
      </header>
      <section className={wide ? "stage stage--wide" : "stage"}>
        {says ? <Speaker says={says} sub={saysSub} mood={mood} /> : null}
        <div className="stage__head">
          <h1>{question}</h1>
          {intro ? <p className="lead">{intro}</p> : null}
        </div>
        {children}
      </section>
    </main>
  );
}
