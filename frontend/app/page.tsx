import { EmailForm } from "@/components/EmailForm";
import { WizardShell } from "@/components/WizardShell";

export default function StartPage() {
  return (
    <WizardShell
      says="Hi, I'm Lumi, your speaking tutor."
      saysSub="Ten minutes a day, out loud, at your pace."
      question="Let's get you talking."
      intro="Tell me who you are and I'll shape every lesson around you."
    >
      <EmailForm />
    </WizardShell>
  );
}
