import { WizardShell } from "@/components/WizardShell";
import { requireUserEmail } from "@/lib/session";

/** Final screen, reached once the microservice has built the learner's lesson. */
export default async function DonePage() {
  await requireUserEmail();
  return (
    <WizardShell
      eyebrow="Ready when you are"
      question="Your first lesson is ready."
      intro="I've shaped it around how you like to learn and the time you set aside. Come back whenever you have a moment, and we'll begin."
    />
  );
}
