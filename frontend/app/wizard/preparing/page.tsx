import { WizardShell } from "@/components/WizardShell";
import { requireUserEmail } from "@/lib/session";

/** Calm holding screen shown while the microservice builds the next lesson. */
export default async function PreparingPage() {
  await requireUserEmail();
  return (
    <WizardShell
      eyebrow="On it"
      question="I'm putting your next lesson together."
      intro="This takes a few minutes, so there's no need to sit here watching me think. Go refill your coffee, stretch, practice rolling an R. Your lesson will be waiting right here when it's ready."
    />
  );
}
