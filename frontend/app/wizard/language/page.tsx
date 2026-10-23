import { LanguageForm } from "@/components/LanguageForm";
import { WizardShell } from "@/components/WizardShell";
import { getAnswer } from "@/lib/answers";
import { QUESTION } from "@/lib/questions";
import { requireUserEmail } from "@/lib/session";

export default async function LanguagePage() {
  const userId = await requireUserEmail();
  const current = await getAnswer(userId, QUESTION.TARGET_LANGUAGE);
  return (
    <WizardShell
      step={2}
      back="/wizard/q1"
      totalSteps={4}
      says="Pick one and I'll speak only that language with you."
      question="Which language do you want to speak?"
    >
      <LanguageForm current={current} />
    </WizardShell>
  );
}
