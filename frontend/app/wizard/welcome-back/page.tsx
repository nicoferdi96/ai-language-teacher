import { PlanLessonForm } from "@/components/PlanLessonForm";
import { WizardShell } from "@/components/WizardShell";
import { requireUserEmail } from "@/lib/session";

/** Returning-user screen: skip the wizard, go straight to a new lesson. */
export default async function WelcomeBackPage() {
  await requireUserEmail();
  return (
    <WizardShell
      eyebrow="Welcome back"
      question="Ready for your next lesson?"
      intro="I still have the answers you gave me last time, so there's nothing to fill in again. Whenever you're ready, I'll shape what comes next around them."
    >
      <PlanLessonForm />
    </WizardShell>
  );
}
