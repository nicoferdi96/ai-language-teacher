import type { CSSProperties } from "react";
import { Flag } from "@/components/Flag";
import { Goals } from "@/components/Goals";
import { Icon, type IconName } from "@/components/Icon";
import { Lumi } from "@/components/Lumi";
import { Brand } from "@/components/WizardShell";
import { findTargetLanguage } from "@/lib/languages";
import { getProgress, type Lesson, type PlanUnit } from "@/lib/planner";
import { requireUserEmail } from "@/lib/session";

const KIND: Record<PlanUnit["kind"], { label: string; icon: IconName }> = {
  vocabulary: { label: "Words", icon: "book" },
  grammar: { label: "Grammar", icon: "spark" },
  conversation: { label: "Conversation", icon: "chat" },
};

/** Learner home: today's lesson, the plan path and what was learned last time. */
export default async function HomePage() {
  const userId = await requireUserEmail();
  const progress = await getProgress(userId);
  const plan = progress?.plan ?? null;
  const lessons = progress?.lessons ?? [];
  const next = lessons.find((lesson) => lesson.status === "planned" || lesson.status === "in_progress");
  const last = lessons.find((lesson) => lesson.status === "completed" || lesson.status === "abandoned");
  const language = findTargetLanguage(plan?.target_language);
  const done = plan?.units.filter((unit) => unit.status === "done").length ?? 0;
  const total = plan?.units.length ?? 0;
  const isFirstVisit = !last;

  return (
    <main className="shell">
      <header className="topbar">
        <Brand />
        {plan ? (
          <div className="pill">
            {language ? <Flag code={language.code} /> : null}
            {language?.name ?? plan.target_language}
            <span className="pill__level">{plan.level}</span>
          </div>
        ) : null}
      </header>
      <section className="stage stage--wide">
        {!plan ? (
          <NoPlan />
        ) : (
          <div className="home">
            <div className="home__main">
              <div className="home__greeting">
                <h1>{isFirstVisit ? "Let's say your first words." : "Welcome back. Ready for today?"}</h1>
                <div className="meter" aria-label={`${done} of ${total} plan steps done`}>
                  <span className="meter__track">
                    <span className="meter__fill" style={{ "--to": total ? done / total : 0 } as CSSProperties} />
                  </span>
                  <span className="meter__label">
                    {done} of {total} steps
                  </span>
                </div>
              </div>
              {next ? <Today lesson={next} unit={plan.units.find((u) => u.unit_id === next.unit_id)} /> : <NoLesson />}
              {last ? <LastTime lesson={last} /> : null}
            </div>
            <nav className="path" aria-label="Your learning plan">
              <h2 className="section-title">Your path</h2>
              <p className="hint">{plan.goal_summary}</p>
              <ol className="path__list">
                {plan.units.map((unit, index) => (
                  <li
                    key={unit.unit_id}
                    className="unit"
                    data-status={unit.status}
                    style={{ "--i": index } as CSSProperties}
                  >
                    <span className="unit__node" aria-hidden="true">
                      {unit.status === "done" ? (
                        <Icon name="check" size={20} />
                      ) : unit.status === "in_progress" ? (
                        <Icon name={KIND[unit.kind].icon} size={20} />
                      ) : (
                        unit.position
                      )}
                    </span>
                    <div className="unit__body">
                      <p className="unit__title">
                        {unit.title}
                        <span className="sr-only">
                          {unit.status === "done" ? ", done" : unit.status === "in_progress" ? ", current" : ", coming up"}
                        </span>
                      </p>
                      {unit.status === "in_progress" ? (
                        <>
                          <span className="unit__here">You're here</span>
                          <p className="unit__desc">{unit.description}</p>
                        </>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ol>
            </nav>
          </div>
        )}
      </section>
    </main>
  );
}

/** Today's planned lesson with its goals and the start action. */
function Today({ lesson, unit }: { lesson: Lesson; unit: PlanUnit | undefined }) {
  return (
    <article className="today">
      <div className="today__head">
        <Lumi state="happy" size="md" />
        <div>
          <h2 className="today__title">{lesson.title}</h2>
          <div className="meta">
            <span className="tag tag--sun">
              <Icon name="clock" size={15} />
              About 10 min
            </span>
            {unit ? (
              <span className="tag">
                <Icon name={KIND[unit.kind].icon} size={15} />
                {KIND[unit.kind].label}
              </span>
            ) : null}
            {lesson.status === "in_progress" ? <span className="tag">Picks up where you stopped</span> : null}
          </div>
        </div>
      </div>
      <a href="/lesson" className="btn btn--block btn--lg">
        <Icon name="mic" size={22} />
        Start speaking
      </a>
      <p className="hint hint--icon hint--center">
        <Icon name="headphones" size={18} />
        Headphones help. You'll be asked to allow the microphone.
      </p>
      <div className="today__goals">
        <h3 className="section-title">You'll be able to</h3>
        <Goals objectives={lesson.objectives} />
      </div>
    </article>
  );
}

/** Summary and new words from the most recent finished lesson. */
function LastTime({ lesson }: { lesson: Lesson }) {
  if (!lesson.summary && lesson.new_vocabulary.length === 0) return null;
  return (
    <section className="last" aria-labelledby="last-time">
      <h2 id="last-time" className="section-title">
        Last time
      </h2>
      {lesson.summary ? <p className="note">{lesson.summary}</p> : null}
      {lesson.new_vocabulary.length ? (
        <ul className="words" lang={lesson.target_language}>
          {lesson.new_vocabulary.map((item) => (
            <li key={item.term} className="word">
              {item.term} <span lang="">{item.meaning}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** Shown when every lesson is finished and the next one is not prepared yet. */
function NoLesson() {
  return (
    <article className="today">
      <div className="today__head">
        <Lumi state="happy" size="md" />
        <h2 className="today__title">Nice work. Your next lesson isn't ready yet.</h2>
      </div>
      <a href="/wizard/preparing" className="btn btn--sun btn--block">
        Prepare my next lesson
      </a>
    </article>
  );
}

/** Shown when the planner is unreachable or the learner has no plan. */
function NoPlan() {
  return (
    <div className="empty-state">
      <Lumi state="thinking" size="lg" />
      <h1>Let's build your plan first.</h1>
      <p className="lead">I couldn't find a plan for you yet, or I couldn't reach it right now.</p>
      <a href="/wizard/preparing" className="btn btn--lg">
        Build my plan
      </a>
    </div>
  );
}
