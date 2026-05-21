import { Q2Form } from "@/components/Q2Form";
import { WizardShell } from "@/components/WizardShell";
import { requireUserEmail } from "@/lib/session";

export default async function Q2Page() {
  await requireUserEmail();
  return (
    <WizardShell
      step={2}
      totalSteps={3}
      question="How would you like to learn Spanish?"
    >
      <Q2Form />
    </WizardShell>
  );
}
