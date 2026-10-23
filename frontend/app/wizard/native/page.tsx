import { NativeForm } from "@/components/NativeForm";
import { WizardShell } from "@/components/WizardShell";
import { getAnswer } from "@/lib/answers";
import { findTargetLanguage } from "@/lib/languages";
import { QUESTION } from "@/lib/questions";
import { requireUserEmail } from "@/lib/session";

export default async function NativePage() {
  const userId = await requireUserEmail();
  const [current, target] = await Promise.all([
    getAnswer(userId, QUESTION.NATIVE_LANGUAGE),
    getAnswer(userId, QUESTION.TARGET_LANGUAGE),
  ]);
  return (
    <WizardShell
      step={3}
      totalSteps={4}
      says="This helps me spot the mistakes your language tends to cause."
      question="What's your native language?"
    >
      <NativeForm current={current} exclude={findTargetLanguage(target)?.name ?? null} />
    </WizardShell>
  );
}
