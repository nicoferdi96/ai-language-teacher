import { redirect } from "next/navigation";
import { WizardShell } from "@/components/WizardShell";
import { requestLessonPlan } from "@/lib/planner";
import { requireUserEmail } from "@/lib/session";

/**
 * Holding route. While this server component awaits the planner (which builds
 * the plan on first visit and prepares the next lesson every login), Next.js
 * renders loading.tsx. Success goes home; failure shows a calm retry.
 */
export default async function PreparingPage() {
  const userId = await requireUserEmail();
  const { ok } = await requestLessonPlan(userId);

  if (!ok) {
    return (
      <WizardShell
        says="Hmm, that didn't work on my side."
        question="I couldn't prepare your lesson just yet."
        intro="Your answers are saved. Give it another try in a moment."
      >
        <a href="/wizard/preparing" className="btn">
          Try again
        </a>
      </WizardShell>
    );
  }

  redirect("/home");
}
