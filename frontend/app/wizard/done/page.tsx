import { WizardShell } from "@/components/WizardShell";
import { requireUserEmail } from "@/lib/session";

export default async function DonePage() {
  await requireUserEmail();
  return (
    <WizardShell
      eyebrow="That's everything"
      question="You're all set."
      intro="I'll use your answers to build a learning plan that adapts to you. Talk soon."
    />
  );
}
