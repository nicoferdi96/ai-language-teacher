import { Q1Form } from "@/components/Q1Form";
import { WizardShell } from "@/components/WizardShell";
import { requireUserEmail } from "@/lib/session";

export default async function Q1Page() {
  await requireUserEmail();
  return (
    <WizardShell step={1} totalSteps={3} question="Ready to begin?">
      <Q1Form />
    </WizardShell>
  );
}
