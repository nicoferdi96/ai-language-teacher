import { redirect } from "next/navigation";
import { WizardShell } from "@/components/WizardShell";
import { requestLessonPlan } from "@/lib/lessonPlanner";
import { requireUserEmail } from "@/lib/session";

/**
 * Holding route. While this server component awaits the lesson-planning
 * microservice (~30s), Next.js renders loading.tsx in its place. On success the
 * learner moves to the done screen; on failure a calm error with a retry link
 * is shown and the frontend stays usable.
 */
export default async function PreparingPage() {
  const userId = await requireUserEmail();
  const { ok } = await requestLessonPlan(userId);

  if (!ok) {
    return (
      <WizardShell
        eyebrow="One moment"
        question="I couldn't finish your lesson just yet."
        intro="Something interrupted me while putting it together. Give it another try in a moment, and I'll pick up where I left off."
      >
        <div className="wizard__form">
          <a href="/wizard/preparing" className="wizard__submit">
            Try again
          </a>
        </div>
      </WizardShell>
    );
  }

  redirect("/wizard/done");
}
