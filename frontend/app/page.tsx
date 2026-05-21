import { EmailForm } from "@/components/EmailForm";
import { WizardShell } from "@/components/WizardShell";

export default function StartPage() {
  return (
    <WizardShell
      eyebrow="Hey, I'm your teaching assistant"
      question="First, what's your email?"
      intro="Before we begin, let me ask a few quick questions so I can shape lessons around you."
    >
      <EmailForm />
    </WizardShell>
  );
}
