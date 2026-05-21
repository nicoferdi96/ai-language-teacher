import { Q3Form } from "@/components/Q3Form";
import { WizardShell } from "@/components/WizardShell";
import { requireUserEmail } from "@/lib/session";

export default async function Q3Page() {
  await requireUserEmail();
  return (
    <WizardShell
      step={3}
      totalSteps={3}
      question="What's your ideal duration per single lesson?"
    >
      <Q3Form />
    </WizardShell>
  );
}
