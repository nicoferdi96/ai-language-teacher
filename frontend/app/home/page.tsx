import { Goals } from "@/components/Goals";
import { Brand } from "@/components/WizardShell";
import { findTargetLanguage } from "@/lib/languages";
import { getProgress, type Lesson, type PlanUnit } from "@/lib/planner";
import { requireUserEmail } from "@/lib/session";

const KIND_LABEL: Record<PlanUnit["kind"], string> = {
  vocabulary: "Words",
  grammar: "Grammar",
  conversation: "Conversation",
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
  const isFirstVisit = !last;

  return (
    <main className="shell">
      <header className="topbar">
        <Brand />
        {plan ? (
          <div className="topbar__meta">
            {language?.flag} {language?.name} · {plan.level}
          </div>
        ) : null}
      </header>
      <section className="stage stage--wide">
        {!plan ? (
          <NoPlan />
        ) : (
          <div className="home">
            <div className="form" style={{ gap: "1.5rem" }}>
              <div>
                <p className="eyebrow">
                  {isFirstVisit ? "Your first lesson" : `${done} of ${plan.units.length} steps done`}
                </p>
                <h1 style={{ marginTop: "0.35rem" }}>
                  {isFirstVisit ? "Let's say your first words." : "Welcome back. Ready for today?"}
                </h1>
              </div>
              {next ? <Today lesson={next} unit={plan.units.find((u) => u.unit_id === next.unit_id)} /> : <NoLesson />}
              {last ? <LastTime lesson={last} /> : null}
            </div>
            <nav className="path" aria-label="Your learning plan">
              <p className="panel__title" style={{ margin: 0 }}>Your path</p>
              <p className="hint">{plan.goal_summary}</p>
              <ol className="path__list">
                {plan.units.map((unit) => (
                  <li key={unit.unit_id} className="unit" data-status={unit.status}>
                    <span className="unit__node" aria-hidden="true">
                      {unit.status === "done" ? "✓" : unit.position}
                    </span>
                    <div>
                      <p className="unit__title">
                        {unit.title}
                        <span className="goal__state">
                          {unit.status === "done" ? ", done" : unit.status === "in_progress" ? ", current" : ", coming up"}
                        </span>
                      </p>
                      {unit.status === "in_progress" ? <p className="unit__desc">{unit.description}</p> : null}
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
        <div className="orb" aria-hidden="true" />
        <div>
          <h2 className="today__title">{lesson.title}</h2>
          <div className="meta" style={{ marginTop: "0.4rem" }}>
            <span className="tag tag--sun">About 10 min</span>
            {unit ? <span className="tag">{KIND_LABEL[unit.kind]}</span> : null}
            {lesson.status === "in_progress" ? <span className="tag">Picks up where you stopped</span> : null}
          </div>
        </div>
      </div>
      <div>
        <p className="panel__title">You'll be able to</p>
        <Goals objectives={lesson.objectives} />
      </div>
      <a href="/lesson" className="btn btn--block">
        Start speaking
      </a>
      <p className="hint">Use headphones if you can. You'll be asked to allow the microphone.</p>
    </article>
  );
}

/** Summary and new words from the most recent finished lesson. */
function LastTime({ lesson }: { lesson: Lesson }) {
  if (!lesson.summary && lesson.new_vocabulary.length === 0) return null;
  return (
    <section className="form" aria-label="Last time">
      <p className="panel__title" style={{ margin: 0 }}>Last time</p>
      {lesson.summary ? <p className="note">{lesson.summary}</p> : null}
      {lesson.new_vocabulary.length ? (
        <div className="words">
          {lesson.new_vocabulary.map((item) => (
            <span key={item.term} className="word">
              {item.term} <span>· {item.meaning}</span>
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

/** Shown when every lesson is finished and the next one is not prepared yet. */
function NoLesson() {
  return (
    <article className="today">
      <h2 className="today__title">Nice work. Your next lesson isn't ready yet.</h2>
      <a href="/wizard/preparing" className="btn btn--sun">
        Prepare my next lesson
      </a>
    </article>
  );
}

/** Shown when the planner is unreachable or the learner has no plan. */
function NoPlan() {
  return (
    <div className="form">
      <h1>Let's build your plan first.</h1>
      <p className="lead">I couldn't find a plan for you yet, or I couldn't reach it right now.</p>
      <a href="/wizard/preparing" className="btn">
        Build my plan
      </a>
    </div>
  );
}
