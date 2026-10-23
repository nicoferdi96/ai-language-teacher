import { Q2Form } from "@/components/Q2Form";
import { WizardShell } from "@/components/WizardShell";
import { getAnswer } from "@/lib/answers";
import { findTargetLanguage } from "@/lib/languages";
import { QUESTION } from "@/lib/questions";
import { requireUserEmail } from "@/lib/session";

export default async function Q2Page() {
  const userId = await requireUserEmail();
  const name = findTargetLanguage(await getAnswer(userId, QUESTION.TARGET_LANGUAGE))?.name ?? "your new language";
  return (
    <WizardShell
      step={4}
      totalSteps={4}
      says="Last one. There's no wrong answer."
      question={`How would you like to learn ${name}?`}
    >
      <Q2Form languageName={name} />
    </WizardShell>
  );
}
